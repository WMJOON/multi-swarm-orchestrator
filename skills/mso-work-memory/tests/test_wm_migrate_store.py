"""wm_migrate_store.py — 큐레이션 JSONL → N-Triples(.nt) 이행 (v0.16.0)."""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import wm_store  # noqa: E402

MIG = SCRIPTS / "wm_migrate_store.py"
NODE = SCRIPTS / "wm_node.py"
CTX = SCRIPTS / "wm_context.py"


def run(*args, **env):
    return subprocess.run([sys.executable, str(MIG), *args], capture_output=True, text=True, env={**os.environ, **env})


def seed(root: Path, rel: str, rows):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def legacy_ud(eid, **over):
    e = {"id": eid, "type": "user-decision", "title": "옛 제목", "text": "옛 본문\n\"인용\"", "tags": ["a"],
         "created_at": "2026-06-01T00:00:00Z", "source_path": "agent-context/work-memory/track-record/user-decision.jsonl",
         "author": "user", "relations": [{"type": "refines", "target": "UD-0000"}, {"type": "references", "target": "docs/x y.md"}],
         "metadata": {"module": "mso-work-memory", "scope": "authoring-workflow", "rationale": "r", "weird": {"k": 1}}}
    e.update(over)
    return e


def test_dry_run_changes_nothing_then_apply_migrates_and_archives(tmp_path):
    root = tmp_path / "wm"
    src = seed(root, "track-record/user-decision.jsonl", [legacy_ud("UD-0001"), legacy_ud("UD-0002", title="둘째")])
    before = src.read_text(encoding="utf-8")
    dry = run("--root", str(root))
    assert dry.returncode == 0 and "DRY-RUN" in dry.stdout and "2건" in dry.stdout
    assert src.read_text(encoding="utf-8") == before and not (root / "track-record" / "user-decision.nt").exists()

    applied = run("--apply", "--root", str(root))
    assert applied.returncode == 0, applied.stdout
    nt = root / "track-record" / "user-decision.nt"
    assert nt.is_file() and not src.exists()                                  # 원본은 트리 밖으로
    archived = list((root / ".migration-archive").rglob("user-decision.jsonl"))
    assert len(archived) == 1 and archived[0].read_text(encoding="utf-8") == before

    entries, problems = wm_store.load_nt_entries(nt)
    assert problems == [] and [e["id"] for e in entries] == ["UD-0001", "UD-0002"]
    e = entries[0]
    assert e["description"] == "옛 제목" and e["content"] == "옛 본문\n\"인용\"" and "source_path" not in e   # 필드 이행 + 저장 형식
    assert e["metadata"]["component"] == "mso-work-memory" and "module" not in e["metadata"]                  # module → component
    assert e["metadata"]["scope_note"] == "authoring-workflow" and "scope" not in e["metadata"]               # 자유 서술 scope → scope_note
    assert e["metadata"]["needs_review"] is True                                                              # scope 는 사람이 골라야 한다
    assert e["metadata"]["weird"] == {"k": 1}                                                                 # 명세 밖 키 보존
    assert {"type": "references", "target": "docs/x y.md"} in e["relations"]                                  # 외부 참조 원문 보존
    # 이행 뒤 도구들이 그대로 동작한다
    assert subprocess.run([sys.executable, str(NODE), "validate", str(root)], capture_output=True, text=True,
                          env={**os.environ, "WORKMEM_DIR": str(root)}).returncode == 0


def test_apply_is_idempotent(tmp_path):
    root = tmp_path / "wm"
    seed(root, "track-record/user-decision.jsonl", [legacy_ud("UD-0001")])
    run("--apply", "--root", str(root))
    nt_before = (root / "track-record" / "user-decision.nt").read_text(encoding="utf-8")
    again = run("--apply", "--json", "--root", str(root))
    assert again.returncode == 0 and json.loads(again.stdout)["totals"]["files"] == 0
    assert (root / "track-record" / "user-decision.nt").read_text(encoding="utf-8") == nt_before
    assert len(list((root / ".migration-archive").iterdir())) == 1


def test_nt_already_present_is_merged_when_ids_do_not_overlap(tmp_path):
    """승격 후 새 기록이 .nt 를 먼저 만들어도 옛 .jsonl 은 이행된다(옛 기록을 앞에). id 가 겹칠 때의 거부는 test_wm_robustness 가 다룬다."""
    root = tmp_path / "wm"
    src = seed(root, "track-record/user-decision.jsonl", [legacy_ud("UD-0001")])
    wm_store.append_entry(root / "track-record" / "user-decision.nt", {
        "id": "UD-0009", "type": "user-decision", "description": "d", "content": "c", "tags": [], "created_at": "2026-12-01T00:00:00Z",
        "relations": [], "metadata": {"scope": ["repository"], "rationale": "r"}})
    r = run("--apply", "--root", str(root))
    assert r.returncode == 0, r.stdout
    assert not src.exists()
    assert [e["id"] for e in wm_store.load_nt_entries(root / "track-record" / "user-decision.nt")[0]] == ["UD-0001", "UD-0009"]


def test_icloud_duplicates_runtime_logs_and_dot_dirs_are_skipped_and_duplicate_ids_warn(tmp_path):
    root = tmp_path / "wm"
    seed(root, "track-record/user-decision.jsonl", [legacy_ud("UD-0001"), legacy_ud("UD-0001", title="중복")])
    dup = seed(root, "track-record/user-decision 2.jsonl", [legacy_ud("UD-0001")])
    log = seed(root, "auditlog/AU-1.jsonl", [{"id": "AU-1", "type": "auditlog", "title": "t", "text": "x"}])
    hidden = seed(root, "track-record/.migration-archive/old.jsonl", [legacy_ud("UD-7777")])
    r = run("--apply", "--root", str(root))
    assert "중복 id UD-0001" in r.stdout
    entries, _ = wm_store.load_nt_entries(root / "track-record" / "user-decision.nt")
    assert [e["id"] for e in entries] == ["UD-0001"] and entries[0]["description"] == "옛 제목"   # 처음 본 것
    assert dup.exists() and log.exists() and hidden.exists()                  # 복제본·런타임 로그·dot-dir 은 건드리지 않는다


def test_unparsable_lines_block_that_file_and_keep_the_original(tmp_path):
    root = tmp_path / "wm"
    path = root / "track-record" / "user-decision.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(legacy_ud("UD-0001"), ensure_ascii=False) + "\n{깨진 줄\n", encoding="utf-8")
    r = run("--apply", "--root", str(root))
    assert r.returncode == 1 and "JSON 파싱 불가" in r.stdout
    assert path.exists() and not (root / "track-record" / "user-decision.nt").exists()     # 일부만 이행하지 않는다


def test_every_entry_round_trips_after_migration_for_all_curated_types(tmp_path):
    root = tmp_path / "wm"
    base = {"tags": ["t"], "created_at": "2026-06-01T00:00:00Z", "relations": [], "author": "agent"}
    seed(root, "track-record/issue-note.jsonl", [dict(base, id="IN-0001", type="issue-note", title="t", text="x",
         metadata={"severity": "major", "status": "open", "reporter": "user", "module": "m"})])
    seed(root, "track-record/agent-decision.jsonl", [dict(base, id="AD-0001", type="agent-decision", title="t", text="x",
         metadata={"rationale": "r", "confidence": "medium (push 전)", "alternatives": "A 안 / B 안"})])
    seed(root, "track-record/alternatives-record.jsonl", [dict(base, id="AR-0001", type="alternatives-record", title="t", text="x",
         metadata={"provided_by": "agent", "options": [{"n": 1, "name": "A"}, {"n": 2, "name": "B"}], "recommended": 2})])
    seed(root, "release-record/release-note.jsonl", [dict(base, id="RN-0001", type="release-note", title="t", text="x",
         metadata={"version": "0.9.0", "kind": "release", "scope": "project"})])
    seed(root, "insight-record/principle.jsonl", [dict(base, id="PR-0001", type="principle", title="t", text="x",
         metadata={"statement": "s", "status": "accepted", "scope": "global"})])
    r = run("--apply", "--root", str(root))
    assert r.returncode == 0, r.stdout
    got = {e["id"]: e for _e in [None] for e in
           [x for p in root.rglob("*.nt") for x in wm_store.load_nt_entries(p)[0]]}
    assert got["AD-0001"]["metadata"]["confidence"] == "medium (push 전)"                  # 어휘 밖 원문 보존
    assert got["AD-0001"]["metadata"]["alternatives"] == ["A 안 / B 안"]
    assert got["AR-0001"]["metadata"]["options"] == [{"n": 1, "name": "A"}, {"n": 2, "name": "B"}]
    assert got["AR-0001"]["metadata"]["recommended"] == 2
    assert got["RN-0001"]["metadata"]["scope"] == ["repository"]                           # 옛 별칭 project → repository
    assert got["PR-0001"]["metadata"]["scope"] == ["global"]
    assert got["IN-0001"]["metadata"]["component"] == "m"
    tt = subprocess.run([sys.executable, str(SCRIPTS / "wm_to_ttl.py"), "validate", str(root)], capture_output=True, text=True)
    assert tt.returncode == 0, tt.stdout + tt.stderr
