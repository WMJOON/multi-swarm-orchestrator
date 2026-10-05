#!/usr/bin/env python3
"""wm_link.py — 연관 저장소 work-memory 설정·점검 (mso-work-memory-link). 사용법은 SKILL.md."""
from __future__ import annotations

import argparse
import difflib
import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


def _find_wm_scripts() -> Path:
    here = Path(__file__).resolve()
    for c in (here.parents[2] / "mso-work-memory" / "scripts", Path.home() / ".claude" / "skills" / "mso-work-memory" / "scripts"):
        if (c / "wm_repos.py").is_file():
            return c
    sys.exit("mso-work-memory/scripts/wm_repos.py 를 찾지 못했습니다")


WM_SCRIPTS = _find_wm_scripts()
sys.path.insert(0, str(WM_SCRIPTS))
import wm_repos  # noqa: E402

SKILL_DIR = WM_SCRIPTS.parent
HOOK_FILES = [("hooks", "commit-work-memory.sh"), ("hooks", "work-memory-check.sh"), ("scripts", "wm_repos.py")]
HEADER = "# 연관 저장소 work-memory 등록부 (mso-work-memory, wm_repos.py)\n"


def _root(a) -> Path:
    return wm_repos.project_root(getattr(a, "root", None))


def _load(root: Path) -> dict:
    p = root / wm_repos.REGISTRY
    if p.is_file():
        try:
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            sys.exit(f"등록부를 읽을 수 없습니다: {p}")
    return {"discover_gitmodules": True, "linked_repos": []}


def _save(root: Path, cfg: dict) -> None:
    p = root / wm_repos.REGISTRY
    p.parent.mkdir(parents=True, exist_ok=True)
    keep = ""
    if p.is_file():  # 맨 위 주석 줄은 보존한다(항목 사이 주석은 보존되지 않음)
        for ln in p.read_text(encoding="utf-8").splitlines(keepends=True):
            if ln.startswith("#") or not ln.strip():
                keep += ln
            else:
                break
    p.write_text((keep or HEADER) + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _git_ok(repo: Path) -> bool:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", "HEAD^{commit}"], capture_output=True).returncode == 0 \
        and subprocess.run(["git", "-C", str(repo), "cat-file", "-e", "HEAD"], capture_output=True).returncode == 0


def _scripts_dir(root: Path, explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit).expanduser().resolve()
    for d in (".claude/scripts", ".codex/scripts"):
        if (root / d / "commit-work-memory.sh").is_file():
            return root / d
    return None


def cmd_status(a) -> int:
    root = _root(a)
    print(f"루트: {root}\n등록부: {root / wm_repos.REGISTRY} ({'있음' if (root / wm_repos.REGISTRY).is_file() else '없음, 자동 발견만'})\n")
    print(f"{'이름':28}{'autocommit':12}{'출처':11}{'git':6}{'wm 변경':8}경로")
    for r in wm_repos.resolve_repos(root):
        repo = r["repo"]
        ok = _git_ok(repo)
        rel = os.path.relpath(r["workmem"], repo)
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", rel], capture_output=True, text=True).stdout.count("\n") if ok else "?"
        print(f"{r['name']:28}{str(r['autocommit']).lower():12}{r['source']:11}{'ok' if ok else 'BAD':6}{str(dirty):8}{repo}")
    sd = _scripts_dir(root, None)
    print()
    if sd is None:
        print("훅 사본: 프로젝트에서 .claude/.codex scripts 를 찾지 못했습니다")
    else:
        for sub, fn in HOOK_FILES:
            src, dst = SKILL_DIR / sub / fn, sd / fn
            state = "없음" if not dst.is_file() else ("최신" if filecmp.cmp(src, dst, shallow=False) else "구판/다름")
            print(f"훅 사본 {fn:26}{state}")
    return 0


def cmd_add(a) -> int:
    root = _root(a); cfg = _load(root)
    items = [i for i in (cfg.get("linked_repos") or []) if i.get("name") != a.name]
    p = Path(a.path).expanduser()
    if not (((p if p.is_absolute() else root / p) / "agent-context/work-memory/schema.yaml").is_file()):
        sys.exit(f"work-memory(schema.yaml)가 없는 경로입니다: {a.path}")
    items.append({"name": a.name, "path": a.path, "autocommit": bool(a.autocommit)})
    cfg["linked_repos"] = items; cfg.setdefault("discover_gitmodules", True)
    _save(root, cfg); print(f"등록: {a.name} -> {a.path} (autocommit {str(bool(a.autocommit)).lower()})"); return 0


def cmd_remove(a) -> int:
    root = _root(a); cfg = _load(root)
    n = len(cfg.get("linked_repos") or [])
    cfg["linked_repos"] = [i for i in (cfg.get("linked_repos") or []) if i.get("name") != a.name]
    if len(cfg["linked_repos"]) == n:
        print(f"등록부에 없는 이름입니다: {a.name} (자동 발견된 서브모듈은 off 로 둡니다)"); return 2
    _save(root, cfg); print(f"제거: {a.name}"); return 0


def cmd_autocommit(a) -> int:
    root = _root(a); cfg = _load(root); on = a.state == "on"
    for i in cfg.get("linked_repos") or []:
        if i.get("name") == a.name:
            i["autocommit"] = on; _save(root, cfg); print(f"{a.name}: autocommit {a.state}"); return 0
    for r in wm_repos.resolve_repos(root):
        if r["name"] == a.name:   # 발견만 된 서브모듈: 같은 path 로 항목을 만든다(등록부 항목이 이긴다)
            cfg.setdefault("linked_repos", []).append({"name": a.name, "path": os.path.relpath(r["repo"], root) if str(r["repo"]).startswith(str(root)) else str(r["repo"]), "autocommit": on})
            _save(root, cfg); print(f"{a.name}: 항목을 만들고 autocommit {a.state}"); return 0
    print(f"알 수 없는 이름입니다: {a.name}"); return 2


def cmd_sync(a) -> int:
    root = _root(a); sd = _scripts_dir(root, a.scripts_dir)
    if sd is None:
        print("scripts 디렉토리를 찾지 못했습니다(--scripts-dir 로 지정)"); return 2
    changed = 0
    for sub, fn in HOOK_FILES:
        src, dst = SKILL_DIR / sub / fn, sd / fn
        if dst.is_file() and filecmp.cmp(src, dst, shallow=False):
            print(f"= {fn} (최신)"); continue
        changed += 1
        old = dst.read_text(encoding="utf-8").splitlines() if dst.is_file() else []
        print(f"~ {fn}" + (" (신규)" if not dst.is_file() else ""))
        for ln in list(difflib.unified_diff(old, src.read_text(encoding="utf-8").splitlines(), "현재", "스킬", lineterm="", n=0))[:40]:
            print("   " + ln)
        if a.apply:
            sd.mkdir(parents=True, exist_ok=True); shutil.copy(src, dst); dst.chmod(0o755)
    print("\n" + ("교체 완료" if a.apply and changed else "dry-run: 변경 없음" if not changed else "dry-run입니다. 적용하려면 --apply (.claude 훅 변경은 사용자 승인 필요)"))
    return 0


def cmd_verify(a) -> int:
    root = _root(a); bad = 0
    for r in wm_repos.resolve_repos(root):
        ok = _git_ok(r["repo"])
        if not ok: bad += 1
        print(f"{'ok ' if ok else 'BAD'} git HEAD  {r['name']}" + ("" if ok else "  (HEAD 객체 손상: autocommit 을 끄고 저장소를 먼저 복구하세요)"))
    cfg = _load(root)
    for i in cfg.get("linked_repos") or []:
        p = Path(str(i.get("path", ""))).expanduser(); p = p if p.is_absolute() else root / p
        if not (p / "agent-context/work-memory/schema.yaml").is_file():
            bad += 1; print(f"BAD 경로    {i.get('name')}: work-memory 가 없습니다 ({p})")
    for sub, fn in HOOK_FILES[:2]:
        rc = subprocess.run(["bash", "-n", str(SKILL_DIR / sub / fn)]).returncode
        if rc: bad += 1
        print(f"{'ok ' if rc == 0 else 'BAD'} bash -n  {fn}")
    print("결과: " + ("이상 없음" if bad == 0 else f"{bad}건 확인 필요")); return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n, f in (("status", cmd_status), ("verify", cmd_verify)):
        s = sub.add_parser(n); s.add_argument("--root"); s.set_defaults(func=f)
    s = sub.add_parser("add"); s.add_argument("name"); s.add_argument("path"); s.add_argument("--autocommit", action="store_true"); s.add_argument("--root"); s.set_defaults(func=cmd_add)
    s = sub.add_parser("remove"); s.add_argument("name"); s.add_argument("--root"); s.set_defaults(func=cmd_remove)
    s = sub.add_parser("autocommit"); s.add_argument("name"); s.add_argument("state", choices=["on", "off"]); s.add_argument("--root"); s.set_defaults(func=cmd_autocommit)
    s = sub.add_parser("sync-hooks"); s.add_argument("--root"); s.add_argument("--scripts-dir"); s.add_argument("--apply", action="store_true"); s.set_defaults(func=cmd_sync)
    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
