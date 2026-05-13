#!/usr/bin/env python3
"""
inject_hooks.py — mso-agent-audit-log 세션 훅을 프로젝트에 주입한다.

--target claude  : .claude/settings.json에 SessionStart·PreCompact·SessionEnd 훅 등록
--target codex   : .codex/hooks.json에 SessionStart 훅 등록
--target all     : 두 타겟 모두 처리 (기본값)

멱등성: 이미 동일 설정이 있으면 건너뛴다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HOOK_BASE = "~/.skill-modules/mso-skills/mso-agent-audit-log/hooks"

CLAUDE_HOOKS = [
    ("SessionStart", "session_start_hook.py"),
    ("PreCompact",   "pre_compact_hook.py"),
    ("SessionEnd",   "session_end_hook.py"),
]

CODEX_HOOKS = [
    ("SessionStart", "session_start_hook.py"),
]


def _cmd(worklog_dir: str, script: str) -> str:
    return f'WORKLOG_DIR="{worklog_dir}" python3 "{HOOK_BASE}/{script}"'


def _register_events(
    hook_map: dict, hook_list: list[tuple[str, str]], worklog_dir: str
) -> list[str]:
    """hook_map에 이벤트 훅을 등록하고 추가된 이벤트 이름 목록을 반환한다."""
    added = []
    for event, script in hook_list:
        command = _cmd(worklog_dir, script)
        bucket = hook_map.setdefault(event, [{"hooks": []}])
        if command not in [h.get("command") for h in bucket[0]["hooks"]]:
            bucket[0]["hooks"].append({"type": "command", "command": command, "timeout": 10})
            added.append(event)
    return added


# ── Claude Code ────────────────────────────────────────────────────────────────

def inject_claude(settings_path: Path, worklog_dir: str, dry_run: bool = False) -> None:
    data = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    added = _register_events(data.setdefault("hooks", {}), CLAUDE_HOOKS, worklog_dir)

    if not added:
        print("[claude] audit-log hooks already present — skipped")
        return

    if dry_run:
        print(f"[dry-run][claude] would inject: {', '.join(added)}")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"[claude] injected: {', '.join(added)} → {settings_path}")


# ── Codex ──────────────────────────────────────────────────────────────────────

def inject_codex(project_root: Path, worklog_dir: str, dry_run: bool = False) -> None:
    hooks_path = project_root / ".codex" / "hooks.json"
    data = json.loads(hooks_path.read_text()) if hooks_path.exists() else {}
    added = _register_events(data, CODEX_HOOKS, worklog_dir)

    if not added:
        print("[codex] audit-log hooks already present — skipped")
        return

    if dry_run:
        print(f"[dry-run][codex] would inject: {', '.join(added)}")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    hooks_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"[codex] injected: {', '.join(added)} → {hooks_path}")


# ── unified entry (setup.py에서 호출) ─────────────────────────────────────────

def inject(settings_path: Path, worklog_dir: str, dry_run: bool = False,
           target: str = "all") -> None:
    if target in ("claude", "all"):
        inject_claude(settings_path, worklog_dir, dry_run=dry_run)
    if target in ("codex", "all"):
        inject_codex(settings_path.parent.parent, worklog_dir, dry_run=dry_run)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="inject mso-agent-audit-log hooks into project"
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--worklog-dir")
    parser.add_argument(
        "--target", choices=["claude", "codex", "all"], default="all",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    worklog_dir = args.worklog_dir or str(project_root / "00.agent_log" / "logs")

    inject(
        project_root / ".claude" / "settings.json",
        worklog_dir,
        dry_run=args.dry_run,
        target=args.target,
    )


if __name__ == "__main__":
    main()
