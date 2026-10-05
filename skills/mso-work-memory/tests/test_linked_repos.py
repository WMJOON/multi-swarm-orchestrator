"""연관 저장소(linked repos) 지원: wm_repos 해석, wm_node --repo/--repo-name, commit 훅 확장."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
HOOKS = SKILL / "hooks"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
import wm_repos  # noqa: E402


def run(*args, cwd, env=None, check=True):
    return subprocess.run(args, cwd=cwd, env=env, check=check, text=True, capture_output=True)


def init_git(p: Path):
    run("git", "init", "-q", cwd=p)
    run("git", "config", "user.email", "t@example.invalid", cwd=p)
    run("git", "config", "user.name", "T", cwd=p)


def make_repo(path: Path, ids=("IN-0001",)) -> Path:
    """work-memory(schema.yaml 포함)가 있는 독립 git 저장소."""
    wm = path / "agent-context" / "work-memory"
    (wm / "track-record").mkdir(parents=True)
    (wm / "schema.yaml").write_text((SKILL / "references" / "schema.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (wm / "track-record" / "issue-note.jsonl").write_text("".join(json.dumps({"id": i}) + "\n" for i in ids), encoding="utf-8")
    init_git(path)
    run("git", "add", "-A", cwd=path)
    run("git", "commit", "-qm", "init", cwd=path)
    return wm


def make_project(tmp: Path, autocommit: bool):
    root = tmp / "root"; root.mkdir()
    init_git(root)
    sub = root / "sub"; sub_wm = make_repo(sub)               # .gitmodules 로 발견될 하위 저장소
    ext = tmp / "external"; ext_wm = make_repo(ext)           # 루트 밖 별도 경로 저장소
    (root / ".gitmodules").write_text('[submodule "sub"]\n\tpath = sub\n\turl = x\n', encoding="utf-8")
    reg = root / "agent-context" / "work-memory"; reg.mkdir(parents=True)
    (reg / "linked-repos.yaml").write_text(
        f"linked_repos:\n  - name: ext\n    path: {ext}\n    autocommit: {str(autocommit).lower()}\n", encoding="utf-8")
    return root, sub_wm, ext_wm


def test_resolve_discovers_gitmodules_and_registry(tmp_path):
    root, sub_wm, ext_wm = make_project(tmp_path, autocommit=True)
    rows = {r["name"]: r for r in wm_repos.resolve_repos(root)}
    assert set(rows) == {"sub", "ext"}
    assert rows["sub"]["autocommit"] is False and rows["sub"]["source"] == "gitmodules"
    assert rows["ext"]["autocommit"] is True and rows["ext"]["workmem"] == ext_wm.resolve()


def test_registry_entry_overrides_discovered_submodule(tmp_path):
    root, sub_wm, _ = make_project(tmp_path, autocommit=False)
    reg = root / "agent-context" / "work-memory" / "linked-repos.yaml"
    reg.write_text(f"linked_repos:\n  - name: sub\n    path: sub\n    autocommit: true\n", encoding="utf-8")
    rows = {r["name"]: r for r in wm_repos.resolve_repos(root)}
    assert rows["sub"]["autocommit"] is True and rows["sub"]["source"] == "registry"


def test_missing_registry_path_is_skipped(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    (root / "agent-context" / "work-memory").mkdir(parents=True)
    (root / "agent-context" / "work-memory" / "linked-repos.yaml").write_text("linked_repos:\n  - name: gone\n    path: /nonexistent/xyz\n", encoding="utf-8")
    assert wm_repos.resolve_repos(root) == []


def wm_node(*args, cwd, env=None):
    return run(sys.executable, str(SCRIPTS / "wm_node.py"), *args, cwd=cwd, env={**os.environ, **(env or {})})


def test_wm_node_repo_flag_writes_to_target_repo(tmp_path):
    root, sub_wm, ext_wm = make_project(tmp_path, autocommit=False)
    wm_node("new", "issue-note", "--title", "t1", "--repo", str(ext_wm.parent.parent), cwd=root)
    lines = (ext_wm / "track-record" / "issue-note.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[-1])["id"] == "IN-0002"
    assert not (root / "agent-context" / "work-memory" / "track-record").exists()   # 루트에는 쓰지 않는다


def test_wm_node_repo_name_flag_any_position(tmp_path):
    root, sub_wm, ext_wm = make_project(tmp_path, autocommit=False)
    wm_node("--repo-name", "ext", "new", "issue-note", "--title", "t2", cwd=root, env={"CLAUDE_PROJECT_DIR": str(root)})
    assert len((ext_wm / "track-record" / "issue-note.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_wm_node_unknown_repo_name_fails(tmp_path):
    root, *_ = make_project(tmp_path, autocommit=False)
    r = subprocess.run([sys.executable, str(SCRIPTS / "wm_node.py"), "stats", "--repo-name", "nope"], cwd=root,
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)}, text=True, capture_output=True)
    assert r.returncode != 0 and "nope" in (r.stderr + r.stdout)


def commit_hook(root: Path):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    env.pop("WORKMEM_DIR", None)
    return run("bash", str(HOOKS / "commit-work-memory.sh"), cwd=root, env=env)


def last_msg(repo: Path) -> str:
    return run("git", "log", "-1", "--format=%s", cwd=repo).stdout.strip()


def test_commit_hook_commits_autocommit_linked_repo_only(tmp_path):
    root, sub_wm, ext_wm = make_project(tmp_path, autocommit=True)
    for wm in (sub_wm, ext_wm):
        f = wm / "track-record" / "issue-note.jsonl"; f.write_text(f.read_text(encoding="utf-8") + '{"id":"IN-0002"}\n', encoding="utf-8")
    other = ext_wm.parent.parent / "README.md"; other.write_text("not work-memory\n", encoding="utf-8")
    commit_hook(root)
    assert last_msg(ext_wm.parent.parent).startswith("chore(work-memory)")           # autocommit: true
    assert last_msg(sub_wm.parent.parent) == "init"                                  # 발견만 된 하위는 건드리지 않음
    assert "README.md" in run("git", "status", "--porcelain", cwd=ext_wm.parent.parent).stdout   # work-memory 밖 변경은 커밋 안 함


def test_commit_hook_linked_disabled_by_env(tmp_path):
    root, sub_wm, ext_wm = make_project(tmp_path, autocommit=True)
    f = ext_wm / "track-record" / "issue-note.jsonl"; f.write_text(f.read_text(encoding="utf-8") + '{"id":"IN-0002"}\n', encoding="utf-8")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "MSO_WM_LINKED": "0"}
    run("bash", str(HOOKS / "commit-work-memory.sh"), cwd=root, env=env)
    assert last_msg(ext_wm.parent.parent) == "init"


def test_check_hook_nudges_for_linked_repo_with_newer_work(tmp_path):
    root, sub_wm, ext_wm = make_project(tmp_path, autocommit=False)
    (ext_wm.parent.parent / "newwork.txt").write_text("x\n", encoding="utf-8")
    newest = ext_wm / "track-record" / "issue-note.jsonl"
    os.utime(newest, (1, 1))   # 기록이 작업보다 오래됨
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}; env.pop("WORKMEM_DIR", None)
    r = subprocess.run(["bash", str(HOOKS / "work-memory-check.sh")], cwd=root, env=env, input='{"hook_event_name":"SessionStart"}', text=True, capture_output=True)
    assert "연관 저장소" in r.stdout and "ext" in r.stdout
