"""wm_migrate_fields.py — title/text → description/content 이행 (v0.16.0, SPEC D3)."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "wm_migrate_fields.py"


def _run(*args: str):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def _entry(eid, title, text, **extra):
    return {"id": eid, "type": "user-decision", "title": title, "text": text, "tags": ["a"],
            "created_at": "2026-06-01T00:00:00Z", "relations": [{"type": "refines", "target": "UD-0000"}],
            "metadata": {"module": "m"}, **extra}


def _seed(root: Path, entries, name="user-decision.jsonl", rel="track-record") -> Path:
    path = root / rel / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")
    return path


def _lines(path: Path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_dry_run_changes_nothing(tmp_path):
    root = tmp_path / "wm"
    path = _seed(root, [_entry("UD-0001", "제목", "본문")])
    before = path.read_text(encoding="utf-8")
    result = _run("--root", str(root))
    assert result.returncode == 0 and "DRY-RUN" in result.stdout
    assert path.read_text(encoding="utf-8") == before
    assert not (root / ".migration-archive").exists()


def test_apply_converts_preserves_fields_and_archives_original(tmp_path):
    root = tmp_path / "wm"
    path = _seed(root, [_entry("UD-0001", "제목", "본문")])
    original = path.read_text(encoding="utf-8")
    assert _run("--apply", "--root", str(root)).returncode == 0
    entry = _lines(path)[0]
    assert entry["description"] == "제목" and entry["content"] == "본문"
    assert "title" not in entry and "text" not in entry
    # 다른 필드와 키 순서 보존 (description/content 는 title/text 자리에 들어간다)
    assert list(entry.keys()) == ["id", "type", "description", "content", "tags", "created_at", "relations", "metadata"]
    assert entry["relations"] == [{"type": "refines", "target": "UD-0000"}]
    assert entry["metadata"] == {"component": "m"}                 # 옛 module → component, needs_review 는 붙지 않는다
    archived = list((root / ".migration-archive").rglob("user-decision.jsonl"))
    assert len(archived) == 1 and archived[0].read_text(encoding="utf-8") == original


def test_apply_is_idempotent(tmp_path):
    root = tmp_path / "wm"
    path = _seed(root, [_entry("UD-0001", "제목", "본문"), _entry("UD-0002", "t" * 250, "TODO: 본문")])
    _run("--apply", "--root", str(root))
    first = path.read_text(encoding="utf-8")
    result = _run("--apply", "--root", str(root))
    assert result.returncode == 0
    assert path.read_text(encoding="utf-8") == first
    assert "이행 0" in result.stdout
    assert len(list((root / ".migration-archive").iterdir())) == 1  # 두 번째 실행은 백업도 만들지 않는다


def test_needs_review_for_truncated_description_and_todo_content(tmp_path):
    root = tmp_path / "wm"
    path = _seed(root, [_entry("UD-0001", "가" * 250, "본문"), _entry("UD-0002", "제목", "TODO: 본문 (markdown 가능)"),
                        _entry("UD-0003", "제목", "정상 본문")])
    _run("--apply", "--root", str(root))
    by_id = {e["id"]: e for e in _lines(path)}
    assert len(by_id["UD-0001"]["description"]) == 200 and by_id["UD-0001"]["description"].endswith("…")
    assert by_id["UD-0001"]["metadata"]["needs_review"] is True
    assert by_id["UD-0001"]["metadata"]["component"] == "m"        # 기존 metadata 는 보존(module → component)
    assert by_id["UD-0002"]["metadata"]["needs_review"] is True
    assert "needs_review" not in by_id["UD-0003"]["metadata"]


def test_icloud_duplicates_and_runtime_logs_are_skipped(tmp_path):
    root = tmp_path / "wm"
    _seed(root, [_entry("UD-0001", "제목", "본문")])
    dup = _seed(root, [_entry("UD-0001", "제목", "본문")], name="user-decision 2.jsonl")
    log = _seed(root, [{"id": "AU-1", "type": "auditlog", "title": "t", "text": "x"}], name="AU-1.jsonl", rel="auditlog")
    dup_before, log_before = dup.read_text(encoding="utf-8"), log.read_text(encoding="utf-8")
    _run("--apply", "--root", str(root))
    assert dup.read_text(encoding="utf-8") == dup_before            # 복제본은 건드리지 않는다(DUP-ID 방지)
    assert log.read_text(encoding="utf-8") == log_before            # 런타임 로그는 필드명을 바꾸지 않는다


def test_unparsable_lines_are_preserved_and_reported(tmp_path):
    root = tmp_path / "wm"
    path = root / "track-record" / "user-decision.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_entry("UD-0001", "제목", "본문"), ensure_ascii=False) + "\n{깨진 줄\n[1,2]\n", encoding="utf-8")
    result = _run("--apply", "--root", str(root))
    assert result.returncode == 1                                    # 파싱 불가 줄이 있으면 알린다
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[1] == "{깨진 줄" and lines[2] == "[1,2]"           # 원문 보존


def test_multiple_roots_and_release_record(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _seed(a, [_entry("UD-0001", "제목", "본문")])
    rn = {"id": "RN-0001", "type": "release-note", "title": "v1", "text": "notes", "tags": [],
          "created_at": "2026-06-01T00:00:00Z", "relations": [], "metadata": {"version": "1.0.0"}}
    _seed(b, [rn], name="release-note.jsonl", rel="release-record")
    result = _run("--apply", "--json", "--root", str(a), "--root", str(b))
    summary = json.loads(result.stdout)
    assert summary["totals"]["migrated"] == 2
    assert _lines(b / "release-record" / "release-note.jsonl")[0]["description"] == "v1"


def test_migrated_data_validates_and_projects(tmp_path):
    root = tmp_path / "wm"
    _seed(root, [_entry("UD-0001", "제목", "본문")])
    _run("--apply", "--root", str(root))
    wm_node = SCRIPT.parent / "wm_node.py"
    import os
    result = subprocess.run([sys.executable, str(wm_node), "validate", str(root)], capture_output=True, text=True,
                            env={**os.environ, "WORKMEM_DIR": str(root)})
    assert result.returncode == 0, result.stdout


def test_metadata_step_module_to_component_and_free_text_scope_to_scope_note(tmp_path):
    root = tmp_path / "wm"
    old = _entry("UD-0001", "제목", "본문")
    old["metadata"] = {"module": "mso-work-memory", "scope": "authoring-workflow", "rationale": "r"}
    ok_scope = _entry("UD-0002", "제목", "본문")
    ok_scope["metadata"] = {"scope": "workflow", "module": "x"}                  # 통제 어휘 scope 는 그대로
    path = _seed(root, [old, ok_scope])
    result = _run("--apply", "--json", "--root", str(root))
    summary = json.loads(result.stdout)
    by_id = {e["id"]: e for e in _lines(path)}
    md = by_id["UD-0001"]["metadata"]
    assert md == {"component": "mso-work-memory", "scope_note": "authoring-workflow", "rationale": "r", "needs_review": True}
    assert "scope" not in md and "module" not in md                            # 통제 어휘 scope 는 사람이 골라야 하므로 비운다
    assert by_id["UD-0002"]["metadata"] == {"scope": "workflow", "component": "x"}
    assert summary["totals"]["needs_review"] == 1                              # module→component 만으로는 needs_review 가 아니다
    rerun = _run("--apply", "--root", str(root))
    assert "이행 0" in rerun.stdout                                             # 멱등


def test_metadata_step_leaves_new_records_module_alone(tmp_path):
    """새 기록(created_at >= enforce_from)의 module 은 index module id 라 component 로 바꾸지 않는다."""
    root = tmp_path / "wm"
    new = _entry("UD-0001", "제목", "본문", created_at="2026-11-20T00:00:00Z")
    new["metadata"] = {"module": "docs", "scope": "repository"}
    path = _seed(root, [new])
    _run("--apply", "--root", str(root))
    assert _lines(path)[0]["metadata"] == {"module": "docs", "scope": "repository"}


def test_metadata_step_scope_list_keeps_valid_values_and_notes_invalid(tmp_path):
    root = tmp_path / "wm"
    e = _entry("UD-0001", "제목", "본문")
    e["metadata"] = {"scope": ["workflow", "mso 스킬 전반"], "rationale": "r"}
    path = _seed(root, [e])
    _run("--apply", "--root", str(root))
    md = _lines(path)[0]["metadata"]
    assert md["scope"] == ["workflow"]                                             # 통제 어휘에 맞는 값은 남긴다
    assert md["scope_note"] == "mso 스킬 전반" and md["needs_review"] is True
