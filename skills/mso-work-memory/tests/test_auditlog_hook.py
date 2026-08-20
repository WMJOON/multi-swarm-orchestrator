"""Claude/Codex PostToolUse auditlog 입력 호환 테스트."""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "auditlog.py"


def _run(workmem: Path, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "WORKMEM_DIR": str(workmem)},
    )


def test_codex_apply_patch_is_recorded(tmp_path):
    workmem = tmp_path / "work-memory"
    workmem.mkdir()
    command = "*** Begin Patch\n*** Update File: demo.txt"
    result = _run(workmem, {
        "session_id": "codex-session",
        "tool_name": "apply_patch",
        "tool_input": {"command": command},
    })
    assert result.returncode == 0

    entries = list((workmem / "auditlog").glob("AU-*.jsonl"))
    assert len(entries) == 1
    entry = json.loads(entries[0].read_text(encoding="utf-8").strip())
    assert entry["metadata"]["tool"] == "apply_patch"
    assert entry["metadata"]["session_id"] == "codex-session"
    assert entry["text"].startswith("*** Begin Patch")


def test_untracked_codex_tool_is_ignored(tmp_path):
    workmem = tmp_path / "work-memory"
    workmem.mkdir()
    result = _run(workmem, {"tool_name": "Read", "tool_input": {"path": "demo.txt"}})
    assert result.returncode == 0
    assert not (workmem / "auditlog").exists()
