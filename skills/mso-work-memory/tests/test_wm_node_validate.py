"""wm_node.py validate 의 필수 필드 검사 — new 산출물 왕복 보장 (IN-0004)."""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "wm_node.py"


def _run(workmem: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "WORKMEM_DIR": str(workmem)},
    )


def _write(workmem: Path, entry: dict) -> None:
    path = workmem / "track-record" / "issue-note.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _base(**over) -> dict:
    entry = {
        "id": "IN-0001",
        "type": "issue-note",
        "title": "t",
        "text": "body",
        "tags": [],
        "created_at": "2026-06-01T00:00:00Z",
        "relations": [],
        "metadata": {},
    }
    entry.update(over)
    return entry


def test_new_output_passes_validate_without_tags(tmp_path):
    """new 가 만든 entry 는 --tags 없이도 자기 validate 를 통과해야 한다 (왕복 불변)."""
    workmem = tmp_path / "work-memory"
    created = _run(workmem, "new", "issue-note", "--title", "no tags")
    assert created.returncode == 0, created.stderr

    result = _run(workmem, "validate", str(workmem))
    assert result.returncode == 0, result.stdout
    assert "모든 entry 가 스키마를 준수합니다" in result.stdout


def test_new_hints_when_tags_missing(tmp_path):
    workmem = tmp_path / "work-memory"
    result = _run(workmem, "new", "issue-note", "--title", "no tags")
    assert "tags 없음" in result.stderr


def test_empty_tags_is_valid_but_non_list_is_not(tmp_path):
    workmem = tmp_path / "work-memory"
    _write(workmem, _base(id="IN-0001", tags=[]))
    assert _run(workmem, "validate", str(workmem)).returncode == 0

    _write(workmem, _base(id="IN-0002", tags="not-a-list"))
    result = _run(workmem, "validate", str(workmem))
    assert result.returncode != 0
    assert "tags 는 list 여야 함" in result.stdout


def test_missing_tags_key_is_reported(tmp_path):
    workmem = tmp_path / "work-memory"
    entry = _base()
    del entry["tags"]
    _write(workmem, entry)

    result = _run(workmem, "validate", str(workmem))
    assert result.returncode != 0
    assert "tags 는 list 여야 함" in result.stdout


def test_scalar_required_fields_still_reject_empty(tmp_path):
    """list 완화가 스칼라 필드 탐지력을 약화시키면 안 된다."""
    workmem = tmp_path / "work-memory"
    _write(workmem, _base(id="IN-0001", title=""))
    _write(workmem, _base(id="IN-0002", text=""))
    _write(workmem, _base(id="IN-0003", created_at=""))

    result = _run(workmem, "validate", str(workmem))
    assert result.returncode != 0
    out = result.stdout
    assert "[MISSING] issue-note.jsonl:1: title" in out
    assert "[MISSING] issue-note.jsonl:2: text" in out
    assert "[MISSING] issue-note.jsonl:3: created_at" in out
