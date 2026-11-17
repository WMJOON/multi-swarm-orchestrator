"""wm_context.py 테스트 — 런타임 context-pack 검색 (lexical)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "wm_context.py"

# test_compile_workflow.py 의 mini ABox 와 동일 구조 (cross-skill parity 픽스처)
TTL = """\
@prefix wf: <https://mso.dev/ontology/workflow#> .

<https://mso.dev/ontology/workflow#project/demo> a wf:Project ;
    wf:label "Demo Workflow" .

<https://mso.dev/ontology/workflow#phase/discovery> a wf:Phase ;
    wf:label "Discovery" ;
    wf:hasNode <https://mso.dev/ontology/workflow#node/discovery-s-001>,
        <https://mso.dev/ontology/workflow#node/discovery-v-001> .

<https://mso.dev/ontology/workflow#node/discovery-s-001> a wf:Node, wf:Step ;
    wf:label "Collect inputs" ;
    wf:instruction "Collect input files" ;
    wf:status "active" .

<https://mso.dev/ontology/workflow#node/discovery-v-001> a wf:Node, wf:Validation ;
    wf:label "Validate inputs" ;
    wf:harness "pytest" ;
    wf:passCriteria "tests pass" .
"""


def _append(root: Path, rel_dir: str, type_name: str, entry: dict) -> None:
    path = root / rel_dir / f"{type_name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _entry(entry_id: str, type_name: str, title: str, text: str = "", tags=None,
           relations=None, metadata=None, created_at: str = "2026-06-01T00:00:00Z", node=None) -> dict:
    """schema v1.4.0 entry. 인자명은 옛 이름(title/text)을 유지하지만 description/content 로 기록한다."""
    entry = {
        "id": entry_id,
        "type": type_name,
        "description": title,
        "content": text,
        "tags": tags or [],
        "created_at": created_at,
        "relations": relations or [],
        "metadata": metadata or {},
    }
    if node:
        entry["node"] = node
    return entry


def _legacy_entry(entry_id: str, type_name: str, title: str, text: str = "", tags=None) -> dict:
    """schema v1.3.x entry (title/text) — 읽기 폴백 검증용."""
    return {"id": entry_id, "type": type_name, "title": title, "text": text,
            "tags": tags or [], "created_at": "2026-06-01T00:00:00Z", "relations": [], "metadata": {}}


def _run(workmem: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "WORKMEM_DIR": str(workmem)},
    )


def _run_json(workmem: Path, *args: str) -> dict:
    result = _run(workmem, *args, "--json")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_query_mode_ranks_tag_matched_entry_first(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "track-record", "issue-note",
            _entry("IN-0001", "issue-note", "Timeout in compile step",
                   text="compile step timed out", tags=["compile-step"]))
    _append(workmem, "track-record", "issue-note",
            _entry("IN-0002", "issue-note", "Unrelated docs typo",
                   text="fixed a typo", tags=["docs"]))

    pack = _run_json(workmem, "query", "compile timeout", "--tags", "compile-step")
    ids = [e["id"] for e in pack["entries"]]
    assert ids[0] == "IN-0001"
    scores = {e["id"]: e["score"] for e in pack["entries"]}
    assert scores["IN-0001"] > scores.get("IN-0002", 0)


def test_korean_query_contributes_token_overlap(tmp_path):
    """한글이 토큰화되지 않으면 한국어 질의의 토큰 기여가 0 이 된다 (IN-0002).

    같은 타입끼리 비교한다 — 토큰 매치는 1점이라 타입 우선순위(12~30) 격차는
    넘지 못한다. 타입을 가로지르는 랭킹은 --tags(18×) 로 잡는다.
    """
    workmem = tmp_path / "work-memory"
    _append(workmem, "track-record", "issue-note",
            _entry("IN-0001", "issue-note", "훅 전달 의미론 정리",
                   text="컨텍스트 주입 경로를 정리했다"))
    _append(workmem, "track-record", "issue-note",
            _entry("IN-0002", "issue-note", "무관한 항목",
                   text="nothing to do with the query"))

    pack = _run_json(workmem, "query", "컨텍스트 주입 의미론")
    scores = {e["id"]: e["score"] for e in pack["entries"]}
    assert scores["IN-0001"] > scores["IN-0002"]
    assert [e["id"] for e in pack["entries"]][0] == "IN-0001"


def test_tokenizer_min_lengths(tmp_path):
    """한글 2자·ASCII 3자 경계 — 1자 한글은 잡음이라 제외한다."""
    workmem = tmp_path / "work-memory"
    _append(workmem, "track-record", "issue-note",
            _entry("IN-0001", "issue-note", "결정", text="훅"))
    _append(workmem, "track-record", "issue-note",
            _entry("IN-0002", "issue-note", "무관", text="무관한 내용"))

    # "결정"(2자) 은 매치, "훅"(1자) 은 토큰이 아니다
    pack = _run_json(workmem, "query", "결정")
    scores = {e["id"]: e["score"] for e in pack["entries"]}
    assert scores["IN-0001"] > scores["IN-0002"]

    pack_single = _run_json(workmem, "query", "훅")
    single_scores = {e["id"]: e["score"] for e in pack_single["entries"]}
    assert single_scores["IN-0001"] == single_scores["IN-0002"]


def test_node_mode_with_ttl_builds_selector_from_node_fields(tmp_path):
    pytest.importorskip("rdflib")
    workmem = tmp_path / "work-memory"
    ttl = tmp_path / "workflow.abox.ttl"
    ttl.write_text(TTL, encoding="utf-8")
    _append(workmem, "insight-record", "principle",
            _entry("PR-0001", "principle", "Input collection must be explicit",
                   text="Collect inputs before validation.",
                   tags=["discovery", "discovery-s-001", "step"]))

    pack = _run_json(workmem, "node", "--node", "discovery-s-001", "--ttl", str(ttl))
    selector = pack["selector"]
    assert "Collect input files" in selector["query"]  # wf:instruction
    assert "Collect inputs" in selector["query"]       # wf:label
    assert "discovery" in selector["tags"]             # phase_id
    assert "discovery-s-001" in selector["tags"]
    assert "step" in selector["tags"]
    assert pack["node_id"] == "discovery-s-001"
    assert "PR-0001" in {e["id"] for e in pack["entries"]}


def test_node_mode_without_ttl_uses_id_seed(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "insight-record", "principle",
            _entry("PR-0001", "principle", "Node principle",
                   tags=["discovery-s-001"]))
    _append(workmem, "insight-record", "principle",
            _entry("PR-0002", "principle", "Other node principle",
                   tags=["other-node"]))

    pack = _run_json(workmem, "node", "--node", "discovery-s-001", "--top-k", "1")
    assert [e["id"] for e in pack["entries"]] == ["PR-0001"]


def test_ttl_node_not_found_errors(tmp_path):
    pytest.importorskip("rdflib")
    workmem = tmp_path / "work-memory"
    ttl = tmp_path / "workflow.abox.ttl"
    ttl.write_text(TTL, encoding="utf-8")

    result = _run(workmem, "node", "--node", "no-such-node", "--ttl", str(ttl))
    assert result.returncode != 0
    assert "discovery-s-001" in result.stderr  # 가용 node 목록 안내


def test_extra_root_merge_and_first_seen_dedup(tmp_path):
    main_root = tmp_path / "main" / "work-memory"
    extra_root = tmp_path / "extra" / "work-memory"
    _append(main_root, "track-record", "issue-note",
            _entry("IN-0001", "issue-note", "main root wins", tags=["shared"]))
    _append(extra_root, "track-record", "issue-note",
            _entry("IN-0001", "issue-note", "extra root shadowed", tags=["shared"]))
    _append(extra_root, "track-record", "issue-note",
            _entry("IN-0100", "issue-note", "extra only", tags=["shared"]))

    pack = _run_json(main_root, "query", "shared", "--tags", "shared",
                     "--extra-root", str(extra_root))
    by_id = {e["id"]: e for e in pack["entries"]}
    assert by_id["IN-0001"]["description"] == "main root wins"
    assert "IN-0100" in by_id


def test_include_types_filter(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "insight-record", "principle",
            _entry("PR-0001", "principle", "A principle", tags=["scope"]))
    _append(workmem, "track-record", "issue-note",
            _entry("IN-0001", "issue-note", "An issue", tags=["scope"]))
    _append(workmem, "worklog", "WL-2026-06-01",
            _entry("WL-20260601-000000", "worklog", "A worklog", tags=["scope"]))

    pack = _run_json(workmem, "query", "scope", "--tags", "scope",
                     "--include-types", "principle")
    assert {e["type"] for e in pack["entries"]} == {"principle"}

    pack_all = _run_json(workmem, "query", "scope", "--tags", "scope",
                         "--include-types", "all")
    assert "worklog" in {e["type"] for e in pack_all["entries"]}


def test_hard_filters_exclude_wrong_scope(tmp_path):
    workmem = tmp_path / "work-memory"
    # 스코프 밖 entry 가 소프트 스코어로는 더 높게 나오도록 구성
    _append(workmem, "insight-record", "principle",
            _entry("PR-0001", "principle", "wrong scope but high score",
                   text="workflow compile compile compile",
                   tags=["workflow-b", "compile"],
                   relations=[{"type": "references", "target": "IN-0001"}]))
    _append(workmem, "track-record", "issue-note",
            _entry("IN-0001", "issue-note", "wrong scope neighbor", tags=["workflow-b"]))
    _append(workmem, "track-record", "issue-note",
            _entry("IN-0002", "issue-note", "right scope", text="workflow compile",
                   tags=["workflow-a", "compile"], metadata={"module": "mod-a"}))

    pack = _run_json(workmem, "query", "workflow compile", "--tags", "compile",
                     "--filter-tag", "workflow-a")
    ids = {e["id"] for e in pack["entries"]}
    assert ids == {"IN-0002"}  # 확장이 필터된 이웃을 되살리지 않음

    pack_mod = _run_json(workmem, "query", "workflow compile",
                         "--filter-module", "mod-a")
    assert {e["id"] for e in pack_mod["entries"]} == {"IN-0002"}


def test_relation_expansion_pulls_neighbor(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "track-record", "trouble-shooting",
            _entry("TS-0001", "trouble-shooting", "fix applied", tags=["target-tag"],
                   relations=[{"type": "caused-by", "target": "IN-0001"}]))
    _append(workmem, "track-record", "issue-note",
            _entry("IN-0001", "issue-note", "root cause"))

    # v0.16.0: top_k 는 관계 확장 *후* 에 적용된다 — 확장 이웃은 남는 자리에만 들어간다.
    pack = _run_json(workmem, "query", "fix", "--tags", "target-tag", "--top-k", "1")
    assert {e["id"] for e in pack["entries"]} == {"TS-0001"}

    pack = _run_json(workmem, "query", "fix", "--tags", "target-tag", "--top-k", "2")
    assert {e["id"] for e in pack["entries"]} == {"TS-0001", "IN-0001"}

    pack_d0 = _run_json(workmem, "query", "fix", "--tags", "target-tag",
                        "--top-k", "1", "--relation-depth", "0")
    assert {e["id"] for e in pack_d0["entries"]} == {"TS-0001"}


def test_empty_root_plain_silent_json_valid(tmp_path):
    workmem = tmp_path / "does-not-exist"

    result = _run(workmem, "query", "anything")
    assert result.returncode == 0
    assert result.stdout == ""

    pack = _run_json(workmem, "query", "anything")
    assert pack["entries"] == []
    assert pack["node_id"] is None


def test_json_pack_shape_and_truncation(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "insight-record", "principle",
            _entry("PR-0001", "principle", "long text", text="x" * 500, tags=["t1"]))

    pack = _run_json(workmem, "query", "long text", "--tags", "t1",
                     "--max-entry-chars", "100")
    assert set(pack.keys()) == {"node_id", "selector", "entries"}
    entry = pack["entries"][0]
    assert set(entry.keys()) == {
        "id", "type", "description", "content", "node", "validity", "tags", "metadata",
        "relations", "source_path", "score",
    }
    assert len(entry["content"]) == 100
    assert pack["selector"]["max_entry_chars"] == 100


def test_plain_output_block(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "insight-record", "principle",
            _entry("PR-0001", "principle", "A principle", text="body line", tags=["t1"]))

    result = _run(workmem, "query", "principle", "--tags", "t1")
    assert result.returncode == 0
    assert result.stdout.startswith("[work-memory context:")
    assert "PR-0001 [principle] A principle" in result.stdout
    # 기본은 요약 목록 — 본문은 펼칠 때만 나온다.
    assert "body line" not in result.stdout
    full = _run(workmem, "query", "principle", "--tags", "t1", "--full")
    assert "body line" in full.stdout


# ── v0.16.0: 점진적 주입 ──

def test_legacy_title_text_fall_back_to_description_content(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "track-record", "issue-note",
            _legacy_entry("IN-0001", "issue-note", "옛 제목", text="옛 본문", tags=["legacy"]))
    pack = _run_json(workmem, "query", "옛", "--tags", "legacy")
    entry = pack["entries"][0]
    assert entry["description"] == "옛 제목"
    assert entry["content"] == "옛 본문"


def test_node_fallback_none_injects_only_mapped_entries(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "track-record", "user-decision",
            _entry("UD-0001", "user-decision", "mapped decision", node=["discovery-s-001"]))
    _append(workmem, "track-record", "user-decision",
            _entry("UD-0002", "user-decision", "unmapped decision"))

    pack = _run_json(workmem, "node", "--node", "discovery-s-001", "--fallback", "none")
    assert [e["id"] for e in pack["entries"]] == ["UD-0001"]
    assert pack["entries"][0]["node"] == ["discovery-s-001"]

    # 매핑이 없는 node 는 침묵한다(점수로 채우지 않는다).
    result = _run(workmem, "node", "--node", "other-node", "--fallback", "none")
    assert result.returncode == 0 and result.stdout == ""

    # 기본값 score 는 기존 CLI 동작을 유지한다.
    pack = _run_json(workmem, "node", "--node", "other-node")
    assert {e["id"] for e in pack["entries"]} == {"UD-0001", "UD-0002"}


def test_superseded_and_invalidated_entries_are_excluded(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "track-record", "user-decision",
            _entry("UD-0001", "user-decision", "old rule", tags=["rule"]))
    _append(workmem, "track-record", "user-decision",
            _entry("UD-0002", "user-decision", "new rule", tags=["rule"],
                   relations=[{"type": "supersedes", "target": "UD-0001"}]))
    _append(workmem, "track-record", "user-decision",
            _entry("UD-0003", "user-decision", "invalidated rule", tags=["rule"],
                   relations=[{"type": "invalidated-by", "target": "RN-0001"}]))
    _append(workmem, "release-record", "release-note",
            _entry("RN-0001", "release-note", "release", metadata={"version": "1.0.0"}))

    pack = _run_json(workmem, "query", "rule", "--tags", "rule")
    assert {e["id"] for e in pack["entries"]} == {"UD-0002"}
    pack = _run_json(workmem, "query", "rule", "--tags", "rule", "--include-inactive")
    assert {e["id"] for e in pack["entries"]} >= {"UD-0001", "UD-0002", "UD-0003"}


def test_rolled_back_invalidation_is_suspended_not_excluded(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "track-record", "user-decision",
            _entry("UD-0001", "user-decision", "rule", tags=["rule"],
                   relations=[{"type": "invalidated-by", "target": "RN-0001"}]))
    _append(workmem, "release-record", "release-note",
            _entry("RN-0001", "release-note", "bad release", metadata={"version": "1.0.0"}))
    _append(workmem, "release-record", "release-note",
            _entry("RN-0002", "release-note", "rollback", metadata={"version": "1.0.1", "kind": "rollback"},
                   relations=[{"type": "rolls-back", "target": "RN-0001"}]))

    pack = _run_json(workmem, "query", "rule", "--tags", "rule")
    by_id = {e["id"]: e for e in pack["entries"]}
    assert by_id["UD-0001"]["validity"] == "suspended"  # 재유효 후보 — 제외하지 않는다


def test_summary_budget_truncates_with_more_marker(tmp_path):
    workmem = tmp_path / "work-memory"
    for i in range(1, 6):
        _append(workmem, "track-record", "user-decision",
                _entry(f"UD-000{i}", "user-decision", "d" * 80, tags=["bud"]))
    result = _run(workmem, "query", "x", "--tags", "bud", "--top-k", "5", "--max-chars", "300")
    assert result.returncode == 0
    assert "more" in result.stdout and "show <id>" in result.stdout
    assert result.stdout.count("── UD-") < 5
    body = "\n".join(l for l in result.stdout.splitlines() if "본문 펼치기" not in l)  # 펼치기 안내는 예산 밖
    assert len(body) < 420


def test_seen_file_prevents_duplicate_injection(tmp_path):
    workmem = tmp_path / "work-memory"
    seen = tmp_path / "seen.json"
    _append(workmem, "track-record", "user-decision",
            _entry("UD-0001", "user-decision", "first", tags=["dup"]))
    first = _run(workmem, "query", "first", "--tags", "dup", "--seen-file", str(seen))
    assert "UD-0001" in first.stdout
    second = _run(workmem, "query", "first", "--tags", "dup", "--seen-file", str(seen))
    assert second.stdout == ""  # 같은 세션에서 이미 낸 id 는 다시 내지 않는다


def test_show_expands_one_entry_with_content_and_validity(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "track-record", "user-decision",
            _entry("UD-0001", "user-decision", "a summary", text="full body text"))
    result = _run(workmem, "show", "UD-0001")
    assert result.returncode == 0
    assert "UD-0001" in result.stdout and "(active)" in result.stdout
    assert "a summary" in result.stdout and "full body text" in result.stdout
    assert _run(workmem, "show", "UD-9999").returncode == 1


def test_validity_rules_match_wm_release(tmp_path):
    """wm_context(copy-form 복제)와 wm_release 의 derive_validity 는 같은 결과를 내야 한다."""
    import importlib.util
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    scripts = SCRIPT.parent
    ctx = load("wm_context_parity", scripts / "wm_context.py")
    rel = load("wm_release_parity", scripts / "wm_release.py")
    entries = [
        {"id": "UD-0001", "type": "user-decision", "relations": [{"type": "invalidated-by", "target": "RN-0001"}]},
        {"id": "UD-0002", "type": "user-decision", "relations": [{"type": "supersedes", "target": "UD-0003"}]},
        {"id": "UD-0003", "type": "user-decision", "relations": []},
        {"id": "UD-0004", "type": "user-decision", "relations": [{"type": "invalidated-by", "target": "RN-0002"}]},
        {"id": "RN-0001", "type": "release-note", "relations": []},
        {"id": "RN-0002", "type": "release-note", "relations": []},
        {"id": "RN-0003", "type": "release-note", "relations": [{"type": "rolls-back", "target": "RN-0002"}]},
    ]
    a = {k: v["validity"] for k, v in ctx.derive_validity(entries).items()}
    b = {k: v["validity"] for k, v in rel.derive_validity(entries).items()}
    assert a == b
    assert a["UD-0001"] == "invalidated" and a["UD-0003"] == "superseded" and a["UD-0004"] == "suspended"


def test_output_footer_has_runnable_expand_command(tmp_path):
    """요약만 나가므로 본문을 펼칠 실행 가능한 명령이 출력에 있어야 한다(없으면 점진적 주입이 일어나지 않는다)."""
    import shlex
    workmem = tmp_path / "work-memory"
    _append(workmem, "track-record", "user-decision",
            _entry("UD-0001", "user-decision", "summary", text="full body text", tags=["exp"]))
    result = _run(workmem, "query", "summary", "--tags", "exp")
    footer = [l for l in result.stdout.splitlines() if "본문 펼치기" in l]
    assert footer, result.stdout
    cmd = footer[0].split("본문 펼치기:", 1)[1].rstrip(")").strip()
    expanded = subprocess.run(shlex.split(cmd.replace("<id>", "UD-0001")), capture_output=True, text=True)
    assert expanded.returncode == 0, expanded.stderr
    assert "full body text" in expanded.stdout


def test_seen_entries_expire_after_ttl(tmp_path):
    """압축 등으로 앞서 주입한 내용이 사라졌을 수 있으므로, seen 은 TTL 후 다시 낸다."""
    import time
    workmem = tmp_path / "work-memory"
    seen = tmp_path / "seen.json"
    _append(workmem, "track-record", "user-decision",
            _entry("UD-0001", "user-decision", "first", tags=["ttl"]))
    assert "UD-0001" in _run(workmem, "query", "first", "--tags", "ttl", "--seen-file", str(seen)).stdout
    assert _run(workmem, "query", "first", "--tags", "ttl", "--seen-file", str(seen)).stdout == ""
    # 낸 시각을 과거로 돌리면 다시 나온다
    seen.write_text(json.dumps({"UD-0001": time.time() - 3600}), encoding="utf-8")
    assert "UD-0001" in _run(workmem, "query", "first", "--tags", "ttl", "--seen-file", str(seen)).stdout
    # --seen-ttl 0 은 중복 방지를 끈다
    assert "UD-0001" in _run(workmem, "query", "first", "--tags", "ttl", "--seen-file", str(seen), "--seen-ttl", "0").stdout
    assert "UD-0001" in _run(workmem, "query", "first", "--tags", "ttl", "--seen-file", str(seen), "--seen-ttl", "0").stdout
