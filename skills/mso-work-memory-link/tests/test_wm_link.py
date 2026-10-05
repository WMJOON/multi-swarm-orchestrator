"""wm_link.py: 등록·autocommit·sync-hooks(dry-run 기본)·verify."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parents[1]
LINK = SKILL / "scripts" / "wm_link.py"
WM_SKILL = SKILL.parent / "mso-work-memory"


def sh(*a, cwd, check=True):
    return subprocess.run(a, cwd=cwd, check=check, text=True, capture_output=True)


def repo(path: Path) -> Path:
    wm = path / "agent-context" / "work-memory"; wm.mkdir(parents=True)
    (wm / "schema.yaml").write_text((WM_SKILL / "references" / "schema.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    sh("git", "init", "-q", cwd=path); sh("git", "config", "user.email", "t@x.invalid", cwd=path); sh("git", "config", "user.name", "T", cwd=path)
    sh("git", "add", "-A", cwd=path); sh("git", "commit", "-qm", "init", cwd=path)
    return path


def project(tmp: Path) -> Path:
    root = tmp / "root"; root.mkdir(); sh("git", "init", "-q", cwd=root)
    repo(root / "sub")
    (root / ".gitmodules").write_text('[submodule "sub"]\n\tpath = sub\n\turl = x\n', encoding="utf-8")
    return root


def link(root, *a, check=True):
    return subprocess.run([sys.executable, str(LINK), *a, "--root", str(root)] if a[0] != "sync-hooks" else [sys.executable, str(LINK), *a, "--root", str(root)],
                          text=True, capture_output=True, check=check, env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)})


def cfg(root):
    return yaml.safe_load((root / "agent-context/work-memory/linked-repos.yaml").read_text(encoding="utf-8"))


def test_add_external_and_toggle_autocommit(tmp_path):
    root = project(tmp_path); ext = repo(tmp_path / "ext")
    link(root, "add", "ext", str(ext), "--autocommit")
    assert {"name": "ext", "path": str(ext), "autocommit": True} in cfg(root)["linked_repos"]
    link(root, "autocommit", "ext", "off")
    assert [i for i in cfg(root)["linked_repos"] if i["name"] == "ext"][0]["autocommit"] is False


def test_autocommit_on_for_discovered_submodule_creates_entry(tmp_path):
    root = project(tmp_path)
    link(root, "autocommit", "sub", "on")
    assert [i for i in cfg(root)["linked_repos"] if i["name"] == "sub"][0]["autocommit"] is True
    assert "sub" in link(root, "status").stdout


def test_add_rejects_path_without_work_memory(tmp_path):
    root = project(tmp_path); (tmp_path / "plain").mkdir()
    r = link(root, "add", "x", str(tmp_path / "plain"), check=False)
    assert r.returncode != 0


def test_remove_unknown_name_returns_2(tmp_path):
    root = project(tmp_path)
    assert link(root, "remove", "nope", check=False).returncode == 2


def test_sync_hooks_is_dry_run_by_default_and_apply_replaces(tmp_path):
    root = project(tmp_path); sd = root / ".claude" / "scripts"; sd.mkdir(parents=True)
    for fn in ("commit-work-memory.sh", "work-memory-check.sh"):
        (sd / fn).write_text("#!/bin/bash\necho old\n", encoding="utf-8")
    out = link(root, "sync-hooks").stdout
    assert "dry-run" in out and (sd / "commit-work-memory.sh").read_text(encoding="utf-8").endswith("echo old\n")
    link(root, "sync-hooks", "--apply")
    assert "linked" in (sd / "commit-work-memory.sh").read_text(encoding="utf-8").lower() or "wm_repos" in (sd / "commit-work-memory.sh").read_text(encoding="utf-8")
    assert (sd / "wm_repos.py").is_file()
    assert "최신" in link(root, "status").stdout


def test_verify_flags_missing_registry_path(tmp_path):
    root = project(tmp_path)
    (root / "agent-context/work-memory").mkdir(parents=True)
    (root / "agent-context/work-memory/linked-repos.yaml").write_text("linked_repos:\n  - name: gone\n    path: /nonexistent/zzz\n", encoding="utf-8")
    r = link(root, "verify", check=False)
    assert r.returncode == 1 and "gone" in r.stdout
