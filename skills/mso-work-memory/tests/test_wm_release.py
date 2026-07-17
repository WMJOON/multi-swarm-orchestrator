import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "wm_release.py"
HOOK = Path(__file__).resolve().parent.parent / "hooks" / "release-context.sh"


def _append(root: Path, rel_dir: str, type_name: str, entry: dict):
    target = root / rel_dir / f"{type_name}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _rn(id_, version, released_at, kind="release", relations=None):
    return {
        "id": id_, "type": "release-note", "title": f"release {version}",
        "text": "...", "tags": ["release"], "created_at": released_at,
        "relations": relations or [],
        "metadata": {"version": version, "released_at": released_at, "kind": kind, "scope": "project"},
    }


def _run(workmem: Path, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True,
        env={**os.environ, "WORKMEM_DIR": str(workmem)},
    )


def _seed_release_history(workmem: Path):
    """v1.0.0 → v1.1.0(교훈 무효화) → v1.1.0 롤백."""
    _append(workmem, "track-record", "user-decision", {
        "id": "UD-0001", "type": "user-decision", "title": "timeout 30s",
        "text": "...", "tags": ["t"], "created_at": "2026-07-01T00:00:00Z",
        "relations": [
            {"type": "verified-in", "target": "RN-0001"},
            {"type": "invalidated-by", "target": "RN-0002"},
        ],
        "metadata": {"rationale": "..."},
    })
    _append(workmem, "release-record", "release-note", _rn("RN-0001", "1.0.0", "2026-07-05T00:00:00Z"))
    _append(workmem, "release-record", "release-note", _rn("RN-0002", "1.1.0", "2026-07-10T00:00:00Z"))


def test_current_is_latest_release(tmp_path):
    workmem = tmp_path / "work-memory"
    _seed_release_history(workmem)
    result = _run(workmem, "current", "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["id"] == "RN-0002"


def test_rollback_shifts_current_and_suspends_invalidation(tmp_path):
    workmem = tmp_path / "work-memory"
    _seed_release_history(workmem)
    _append(workmem, "release-record", "release-note",
            _rn("RN-0003", "1.1.0-rollback", "2026-07-12T00:00:00Z", kind="rollback",
                relations=[{"type": "rolls-back", "target": "RN-0002"}]))

    current = json.loads(_run(workmem, "current", "--json").stdout)
    assert current["id"] == "RN-0001"  # 롤백된 RN-0002 는 current 후보에서 제외

    edges = json.loads(_run(workmem, "validity", "--json").stdout)
    inv = next(e for e in edges if e["relation"] == "invalidated-by")
    assert inv["status"] == "suspended"  # 재유효 후보로 파생

    context = _run(workmem, "context").stdout
    assert "1.0.0" in context
    assert "재유효 후보" in context


def test_active_invalidation_appears_in_context(tmp_path):
    workmem = tmp_path / "work-memory"
    _seed_release_history(workmem)
    context = _run(workmem, "context").stdout
    assert "1.1.0" in context
    assert "UD-0001" in context
    assert "더 이상 유효하지 않은" in context


def test_context_silent_without_release_notes(tmp_path):
    workmem = tmp_path / "work-memory"
    _append(workmem, "track-record", "issue-note", {
        "id": "IN-0001", "type": "issue-note", "title": "t", "text": "...",
        "tags": ["t"], "created_at": "2026-07-01T00:00:00Z", "relations": [], "metadata": {},
    })
    result = _run(workmem, "context")
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_emits_on_session_start_only(tmp_path):
    workmem = tmp_path / "work-memory"
    _seed_release_history(workmem)
    env = {**os.environ, "WORKMEM_DIR": str(workmem), "CLAUDE_PROJECT_DIR": str(tmp_path)}

    started = subprocess.run(
        ["bash", str(HOOK)], input='{"hook_event_name":"SessionStart"}',
        capture_output=True, text=True, env=env,
    )
    assert started.returncode == 0
    assert "[work-memory release]" in started.stdout

    stopped = subprocess.run(
        ["bash", str(HOOK)], input='{"hook_event_name":"Stop"}',
        capture_output=True, text=True, env=env,
    )
    assert stopped.returncode == 0
    assert stopped.stdout == ""
