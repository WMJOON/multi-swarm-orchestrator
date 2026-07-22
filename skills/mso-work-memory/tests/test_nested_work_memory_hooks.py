"""Nested Git repository support for MSO work-memory hooks."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


HOOKS = Path(__file__).resolve().parents[1] / "hooks"


def run(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, env=env, check=True, text=True, capture_output=True)


def init_git(path: Path) -> None:
    run("git", "init", "-q", cwd=path)
    run("git", "config", "user.email", "test@example.invalid", cwd=path)
    run("git", "config", "user.name", "MSO Test", cwd=path)


def test_commit_hook_commits_to_nested_work_memory_repository(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    init_git(project)
    (project / "README.md").write_text("root\n", encoding="utf-8")
    run("git", "add", "README.md", cwd=project)
    run("git", "commit", "-qm", "root", cwd=project)

    nested = project / "agent-context"
    nested.mkdir()
    init_git(nested)
    workmem = nested / "work-memory"
    workmem.mkdir()
    note = workmem / "issue-note.jsonl"
    note.write_text('{"id":"IN-0001"}\n', encoding="utf-8")
    run("git", "add", "work-memory", cwd=nested)
    run("git", "commit", "-qm", "initial work-memory", cwd=nested)

    note.write_text('{"id":"IN-0001"}\n{"id":"IN-0002"}\n', encoding="utf-8")
    env = {**os.environ, "PROJECT_DIR": str(project), "WORKMEM_DIR": str(workmem)}
    subprocess.run(["bash", str(HOOKS / "commit-work-memory.sh")], cwd=project, env=env, check=True, text=True, capture_output=True)

    assert run("git", "status", "--short", "--", "work-memory", cwd=nested).stdout == ""
    assert "chore(work-memory): auto log trail [hook]" in run("git", "log", "-1", "--format=%s", cwd=nested).stdout
    assert "auto log trail" not in run("git", "log", "-1", "--format=%s", cwd=project).stdout


def test_check_hook_accepts_nested_work_memory_repository(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    init_git(project)

    nested = project / "agent-context"
    nested.mkdir()
    init_git(nested)
    workmem = nested / "work-memory"
    (workmem / "track-record").mkdir(parents=True)
    (workmem / "insight-record").mkdir()
    (workmem / "schema.yaml").write_text("version: '1'\n", encoding="utf-8")
    run("git", "add", "work-memory", cwd=nested)
    run("git", "commit", "-qm", "initial work-memory", cwd=nested)

    env = {**os.environ, "PROJECT_DIR": str(project), "WORKMEM_DIR": str(workmem), "WM_WORTHY_PATHS": "workflow index"}
    result = subprocess.run(["bash", str(HOOKS / "work-memory-check.sh")], cwd=project, env=env, input='{"hook_event_name":"SessionStart"}', check=True, text=True, capture_output=True)
    assert result.returncode == 0
