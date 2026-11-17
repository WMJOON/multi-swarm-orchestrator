"""승격 전 독립 리뷰가 지적한 실제 저장소 상태(iCloud 복제본, .jsonl/.nt 혼재, 구버전 훅 사본)에서의 동작 (v0.16.0)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import wm_store  # noqa: E402

NODE = SCRIPTS / "wm_node.py"
CTX = SCRIPTS / "wm_context.py"
MIG = SCRIPTS / "wm_migrate_store.py"
OLD = "2026-06-01T00:00:00Z"


def ud(eid, desc, **over):
    e = {"id": eid, "type": "user-decision", "description": desc, "content": "본문", "tags": ["t"], "created_at": OLD,
         "relations": [], "metadata": {"scope": ["repository"], "rationale": "r"}}
    e.update(over)
    return e


def node(root, *args):
    return subprocess.run([sys.executable, str(NODE), *args], capture_output=True, text=True,
                          env={**os.environ, "WORKMEM_DIR": str(root)})


def with_icloud_copy(root, fmt="nt"):
    """원본(.nt)과, 같은 id 에 다른 내용을 담은 iCloud 충돌 복제본 `user-decision 2.<fmt>`."""
    orig = root / "track-record" / "user-decision.nt"
    wm_store.append_entry(orig, ud("UD-000000000001", "원본 설명"))
    if fmt == "nt":
        wm_store.append_entry(root / "track-record" / "user-decision 2.nt", ud("UD-000000000001", "복제본 설명"))
    else:
        (root / "track-record" / "user-decision 2.jsonl").write_text(
            json.dumps(ud("UD-000000000001", "복제본 설명"), ensure_ascii=False) + "\n", encoding="utf-8")
    return orig


# ── 1. iCloud 충돌 복제본 ──

@pytest.mark.parametrize("fmt", ["nt", "jsonl"])
def test_readers_prefer_the_original_over_a_conflict_copy(tmp_path, fmt):
    root = tmp_path / "wm"
    with_icloud_copy(root, fmt)
    pack = json.loads(subprocess.run([sys.executable, str(CTX), "query", "설명", "--tags", "t", "--json"], capture_output=True, text=True,
                                     env={**os.environ, "WORKMEM_DIR": str(root)}).stdout)
    assert [e["description"] for e in pack["entries"]] == ["원본 설명"]      # 정렬상 앞서는 "user-decision 2.*" 가 이기면 안 된다


@pytest.mark.parametrize("fmt", ["nt", "jsonl"])
@pytest.mark.parametrize("command", [("map-node", "UD-000000000001", "--node", "n1"),
                                     ("edit", "UD-000000000001", "--description", "새 설명"),
                                     ("relate", "UD-000000000001", "refines", "UD-000000000002")])
def test_write_commands_refuse_when_the_id_exists_in_more_than_one_file(tmp_path, fmt, command):
    root = tmp_path / "wm"
    orig = with_icloud_copy(root, fmt)
    before = orig.read_text(encoding="utf-8")
    copy = next(p for p in (root / "track-record").iterdir() if " 2." in p.name)
    copy_before = copy.read_text(encoding="utf-8")
    r = node(root, *command)
    assert r.returncode != 0 and "여러 파일" in (r.stderr + r.stdout)
    assert orig.read_text(encoding="utf-8") == before and copy.read_text(encoding="utf-8") == copy_before   # 어느 쪽도 고치지 않는다


def test_edit_refuses_a_record_with_conflicting_single_valued_fields(tmp_path):
    root = tmp_path / "wm"
    path = root / "track-record" / "user-decision.nt"
    wm_store.append_entry(path, ud("UD-000000000001", "요약"))
    extra = wm_store.serialize_triple(wm_store.entry_iri("UD-000000000001"), wm_store.WM + "description", wm_store.L("병합으로 생긴 다른 요약"))
    with open(path, "a", encoding="utf-8") as f:
        f.write(extra + "\n")
    before = path.read_text(encoding="utf-8")
    r = node(root, "edit", "UD-000000000001", "--description", "고침")
    assert r.returncode != 0 and "DUP-FIELD" in (r.stderr + r.stdout)
    assert path.read_text(encoding="utf-8") == before                         # 충돌 값을 조용히 버리지 않는다


def test_wm_query_excludes_conflict_copies_and_warns(tmp_path):
    import wm_query
    root = tmp_path / "wm"
    with_icloud_copy(root, "nt")
    r = subprocess.run([sys.executable, str(SCRIPTS / "wm_query.py"), "run", "--sparql",
                        f"PREFIX wm:<{wm_store.WM}> SELECT ?d WHERE {{ ?e wm:description ?d }}", "--format", "tsv"],
                       capture_output=True, text=True, env={**os.environ, "WORKMEM_DIR": str(root)})
    assert r.returncode == 0
    assert r.stdout.splitlines()[1:] == ["원본 설명"]                          # 복제본의 값이 합쳐져 나오면 안 된다
    assert "충돌 복제본" in r.stderr and "user-decision 2.nt" in r.stderr


def test_is_conflict_copy_detection():
    for name in ("a 2.jsonl", "a 3.nt", "a 12", "a 2.nt"):
        assert wm_store.is_conflict_copy(Path(name)), name
    for name in ("user-decision.nt", "agent-decision.jsonl", "v2.nt", "AU-20260101-120000.jsonl"):
        assert not wm_store.is_conflict_copy(Path(name)), name


# ── 2. .jsonl 과 .nt 가 섞인 상태에서의 이행 ──

def legacy_jsonl(root, entries):
    path = root / "track-record" / "user-decision.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")
    return path


def test_migration_merges_into_an_existing_nt_when_ids_do_not_overlap(tmp_path):
    """승격 후 새 기록이 한 건이라도 생기면 그 타입의 .nt 가 생긴다 — 그래도 옛 .jsonl 을 이행할 수 있어야 한다."""
    root = tmp_path / "wm"
    nt = root / "track-record" / "user-decision.nt"
    wm_store.append_entry(nt, ud("UD-019a3c5e4f21", "새로 쓴 기록", created_at="2026-11-20T00:00:00Z",
                                metadata={"scope": ["repository"], "rationale": "r"}))
    src = legacy_jsonl(root, [dict(ud("UD-0001", "옛 기록 1"), title="옛 기록 1", text="x"),
                              dict(ud("UD-0002", "옛 기록 2"), title="옛 기록 2", text="y")])
    r = subprocess.run([sys.executable, str(MIG), "--apply", "--root", str(root)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert not src.exists()
    entries, problems = wm_store.load_nt_entries(nt)
    assert problems == [] and [e["id"] for e in entries] == ["UD-0001", "UD-0002", "UD-019a3c5e4f21"]   # 옛 기록을 앞에 둔다


def test_migration_refuses_only_when_ids_overlap(tmp_path):
    root = tmp_path / "wm"
    nt = root / "track-record" / "user-decision.nt"
    wm_store.append_entry(nt, ud("UD-0001", "이미 .nt 에 있음"))
    src = legacy_jsonl(root, [dict(ud("UD-0001", "겹침"), title="겹침", text="x")])
    before = nt.read_text(encoding="utf-8")
    r = subprocess.run([sys.executable, str(MIG), "--apply", "--root", str(root)], capture_output=True, text=True)
    assert r.returncode == 1 and "UD-0001" in r.stdout and "겹" in r.stdout
    assert src.exists() and nt.read_text(encoding="utf-8") == before


# ── 3. 구버전 훅 사본 ──

def test_write_commands_warn_when_the_projects_hook_copy_is_stale(tmp_path):
    project = tmp_path / "proj"
    scripts = project / ".claude" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "wm_context.py").write_text("# v0.15 사본 — wm_store.py 가 없다\n", encoding="utf-8")
    root = project / "agent-context" / "work-memory"
    r = node(root, "new", "user-decision", "--description", "d", "--meta", "rationale=r", "--scope", "repository")
    assert r.returncode == 0, r.stderr
    assert "훅 사본" in r.stderr and "init.py --hook" in r.stderr
    (scripts / "wm_store.py").write_text("# 최신 사본\n", encoding="utf-8")
    ok = node(root, "new", "user-decision", "--description", "d2", "--meta", "rationale=r", "--scope", "repository")
    assert "훅 사본" not in ok.stderr


# ── 4. relation 대상이 entry id 인지 외부 참조인지 ──

@pytest.mark.parametrize("target,is_entry", [
    ("UD-0001", True), ("UD-019a3c5e4f21", True), ("AU-20260101-120000", True), ("RN-0001", True),
    ("WL-20260601-133456", True), ("WL-2026-06-01", True),                      # 실제 기록의 worklog id 형식
    ("PR-123", False), ("ADR-7", False), ("GH-42", False), ("#12", False), ("docs/spec.md", False), ("v0.7.0", False),
])
def test_relation_target_is_an_entry_only_for_real_entry_ids(target, is_entry):
    e = ud("UD-000000000001", "d", relations=[{"type": "references", "target": target}])
    iris = [o[1] for s, p, o in wm_store.entry_to_triples(e) if p == wm_store.WM + "references"]
    assert iris[0].startswith(wm_store.ID_NS + ("memory/" if is_entry else "external/"))
    got = wm_store.triples_to_entries(wm_store.entry_to_triples(e))[0]
    assert got["relations"] == [{"type": "references", "target": target}]      # 어느 쪽이든 원문이 되돌아온다
