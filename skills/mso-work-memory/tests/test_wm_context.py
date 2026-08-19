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
           relations=None, metadata=None, created_at: str = "2026-06-01T00:00:00Z") -> dict:
    return {
        "id": entry_id,
        "type": type_name,
        "title": title,
        "text": text,
        "tags": tags or [],
        "created_at": created_at,
        "relations": relations or [],
        "metadata": metadata or {},
    }


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
    assert by_id["IN-0001"]["title"] == "main root wins"
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

    pack = _run_json(workmem, "query", "fix", "--tags", "target-tag", "--top-k", "1")
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
        "id", "type", "title", "text", "tags", "metadata",
        "relations", "source_path", "score",
    }
    assert len(entry["text"]) == 100
    assert pack["selector"]["max_entry_chars"] == 100


def test_plain_output_block(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "insight-record", "principle",
            _entry("PR-0001", "principle", "A principle", text="body line", tags=["t1"]))

    result = _run(workmem, "query", "principle", "--tags", "t1")
    assert result.returncode == 0
    assert result.stdout.startswith("[work-memory context:")
    assert "PR-0001 [principle] A principle" in result.stdout
    assert "body line" in result.stdout
