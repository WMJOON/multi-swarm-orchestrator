#!/usr/bin/env python3
"""
wm_repos.py — 연관 저장소(linked repos)의 work-memory 위치를 해석한다.

프로젝트 루트의 work-memory 말고, 하위(서브모듈)나 별도 경로의 MSO 저장소 work-memory 에도
기록·커밋할 수 있게 하는 등록부 해석기. 표준 라이브러리 + PyYAML 만 쓴다.

등록부: <project root>/agent-context/work-memory/linked-repos.yaml (선택)

    discover_gitmodules: true        # 기본 true. .gitmodules 서브모듈 중 work-memory 가 있는 곳을 자동 발견
    linked_repos:
      - name: mso-orchestrator       # --repo-name 으로 부르는 이름
        path: ~/path/to/another-repo   # 절대, ~, 또는 프로젝트 루트 기준 상대
        workmem: agent-context/work-memory   # 선택, 기본값
        autocommit: true             # Stop 훅이 이 저장소의 work-memory 를 자동 커밋 (기본 false)

자동 발견된 서브모듈은 autocommit=false 다. 켜려면 같은 path 로 항목을 두고 autocommit: true 를 준다
(path 가 같으면 등록부 항목이 발견 항목을 덮어쓴다).

사용법:
  wm_repos.py list [--root R] [--tsv] [--autocommit]   # 해석된 저장소 목록
  wm_repos.py resolve <name> [--root R]                # 이름 → work-memory 절대경로
"""
from __future__ import annotations

import argparse
import configparser
import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

REGISTRY = "agent-context/work-memory/linked-repos.yaml"
DEFAULT_WM = "agent-context/work-memory"


def project_root(explicit: str | None = None) -> Path:
    for v in (explicit, os.environ.get("CLAUDE_PROJECT_DIR"), os.environ.get("CODEX_PROJECT_DIR"), os.environ.get("PROJECT_DIR")):
        if v:
            return Path(v).expanduser().resolve()
    return Path.cwd().resolve()


def _has_wm(repo: Path, wm_rel: str) -> bool:
    return (repo / wm_rel / "schema.yaml").is_file()


def _gitmodule_paths(root: Path) -> list[str]:
    gm = root / ".gitmodules"
    if not gm.is_file():
        return []
    cp = configparser.RawConfigParser()
    try:
        cp.read(gm, encoding="utf-8")
    except Exception:
        return []
    return [cp.get(s, "path") for s in cp.sections() if cp.has_option(s, "path")]


def resolve_repos(root: Path) -> list[dict]:
    """[{name, repo, workmem, autocommit, source}] — repo/workmem 은 절대경로. 중복 repo 는 등록부 항목이 이긴다."""
    found: dict[str, dict] = {}
    cfg: dict = {}
    reg = root / REGISTRY
    if reg.is_file() and yaml is not None:
        try:
            cfg = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
        except Exception:
            cfg = {}
    if cfg.get("discover_gitmodules", True):
        for p in _gitmodule_paths(root):
            repo = (root / p).resolve()
            if _has_wm(repo, DEFAULT_WM):
                found[str(repo)] = {"name": Path(p).name, "repo": repo, "workmem": repo / DEFAULT_WM, "autocommit": False, "source": "gitmodules"}
    for item in cfg.get("linked_repos") or []:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        raw = Path(str(item["path"])).expanduser()
        repo = (raw if raw.is_absolute() else root / raw).resolve()
        wm_rel = str(item.get("workmem") or DEFAULT_WM)
        if not _has_wm(repo, wm_rel):
            continue  # 없는 경로는 조용히 건너뛴다(훅은 실패하면 안 된다)
        found[str(repo)] = {"name": str(item.get("name") or repo.name), "repo": repo, "workmem": repo / wm_rel, "autocommit": bool(item.get("autocommit", False)), "source": "registry"}
    return sorted(found.values(), key=lambda r: r["name"])


def find_workmem(root: Path, name: str) -> Path | None:
    for r in resolve_repos(root):
        if r["name"] == name:
            return r["workmem"]
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="linked work-memory repos")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--root")
    p_list.add_argument("--tsv", action="store_true", help="name<TAB>workmem<TAB>autocommit (훅용)")
    p_list.add_argument("--autocommit", action="store_true", help="autocommit=true 항목만")
    p_res = sub.add_parser("resolve")
    p_res.add_argument("name")
    p_res.add_argument("--root")
    a = ap.parse_args(argv)
    root = project_root(a.root)
    if a.cmd == "resolve":
        w = find_workmem(root, a.name)
        if w is None:
            print(f"등록된 연관 저장소가 없습니다: {a.name}", file=sys.stderr)
            return 2
        print(w)
        return 0
    rows = [r for r in resolve_repos(root) if r["autocommit"] or not a.autocommit]
    if a.tsv:
        for r in rows:
            print(f"{r['name']}\t{r['workmem']}\t{str(r['autocommit']).lower()}")
    else:
        print(json.dumps([{**r, "repo": str(r["repo"]), "workmem": str(r["workmem"])} for r in rows], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
