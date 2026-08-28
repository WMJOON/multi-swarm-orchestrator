"""Antigravity camelCase <-> 기존 snake_case 훅 계약 어댑터 테스트."""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
ADAPTER = HOOKS_DIR / "adapter_antigravity.py"
AUDITLOG = HOOKS_DIR / "auditlog.py"
STOP_CHECK = HOOKS_DIR / "stop-check.sh"
WORKFLOW_CTX = HOOKS_DIR / "workflow-context-hook.py"


def _run(mode: str, script: Path, payload: dict, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ADAPTER), mode, "--", str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **(extra_env or {})},
    )


def test_posttooluse_translates_run_command_and_returns_empty_object(tmp_path):
    workmem = tmp_path / "agent-context" / "work-memory"
    workmem.mkdir(parents=True)
    payload = {
        "conversationId": "conv-1",
        "workspacePaths": [str(tmp_path)],
        "toolCall": {"name": "run_command", "args": {"command": "echo hi"}},
        "stepIdx": 0,
    }
    result = _run("posttooluse", AUDITLOG, payload)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}

    entries = list((workmem / "auditlog").glob("AU-*.jsonl"))
    assert len(entries) == 1
    entry = json.loads(entries[0].read_text(encoding="utf-8").strip())
    assert entry["metadata"]["tool"] == "Bash"  # run_command -> Bash 매핑
    assert entry["metadata"]["session_id"] == "conv-1"
    assert entry["text"] == "echo hi"


def test_posttooluse_untracked_tool_is_ignored(tmp_path):
    workmem = tmp_path / "agent-context" / "work-memory"
    workmem.mkdir(parents=True)
    payload = {
        "conversationId": "conv-1",
        "workspacePaths": [str(tmp_path)],
        "toolCall": {"name": "view_file", "args": {"path": "demo.txt"}},
    }
    result = _run("posttooluse", AUDITLOG, payload)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}
    assert not (workmem / "auditlog").exists()


def test_stop_wraps_reason_and_strips_ansi(tmp_path):
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    payload = {
        "conversationId": "conv-1",
        "workspacePaths": [str(tmp_path)],
        "executionNum": 0,
        "terminationReason": "idle",
    }
    result = _run("stop", STOP_CHECK, payload, extra_env={"PROJECT_DIR": str(tmp_path)})
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["decision"] == "continue"
    assert "\x1b[" not in out["reason"]
    assert "MSO session boundary check" in out["reason"]

    # Second immediate call is throttled by stop-check.sh's own state marker.
    result2 = _run("stop", STOP_CHECK, payload, extra_env={"PROJECT_DIR": str(tmp_path)})
    assert json.loads(result2.stdout) == {"decision": ""}


def test_session_mode_gated_on_invocation_zero(tmp_path):
    (tmp_path / "agent-context" / "work-memory").mkdir(parents=True)
    payload_first = {"conversationId": "c", "workspacePaths": [str(tmp_path)], "invocationNum": 0}
    payload_later = {"conversationId": "c", "workspacePaths": [str(tmp_path)], "invocationNum": 5}

    # No cursor/context available -> quiet {} either way, but the gate itself
    # must short-circuit non-zero invocations without invoking the script.
    result_later = _run("session", WORKFLOW_CTX, payload_later)
    assert json.loads(result_later.stdout) == {}

    result_first = _run("session", WORKFLOW_CTX, payload_first)
    assert json.loads(result_first.stdout) == {}


def test_turn_mode_wraps_nonempty_stdout_as_ephemeral_message(tmp_path):
    fake_hook = tmp_path / "noisy_hook.py"
    fake_hook.write_text("print('hello from hook')\n", encoding="utf-8")
    payload = {"conversationId": "c", "workspacePaths": [str(tmp_path)]}
    result = _run("turn", fake_hook, payload)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"injectSteps": [{"ephemeralMessage": "hello from hook"}]}
