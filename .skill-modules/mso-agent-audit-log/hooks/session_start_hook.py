#!/usr/bin/env python3
"""SessionStart hook — 최근 worklog 3개의 마지막 항목을 compact 요약으로 주입.

런타임 자동 감지:
  - stdin에 model 필드가 있으면 Codex → {"systemMessage": "..."}
  - 그 외 Claude Code → {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from _common import resolve_worklog_dir

_HEADER_RE = re.compile(r"\n(?=## )")


def extract_last_entry(worklog: Path) -> str:
    """## 헤더로 분리된 마지막 블록의 핵심 줄만 반환 (최대 5줄)."""
    try:
        text = worklog.read_text(errors="replace")
        blocks = _HEADER_RE.split(text.strip())
        last = blocks[-1].strip() if blocks else ""
        lines = [l for l in last.splitlines() if l.strip()][:5]
        return "\n".join(lines)
    except Exception:
        return ""


def build_context(worklog_dir: Path) -> str:
    logs = sorted(worklog_dir.glob("worklog-*.md"), reverse=True)[:3]
    if not logs:
        return ""

    parts = []
    for log in logs:
        date = log.stem.replace("worklog-", "")
        entry = extract_last_entry(log)
        if entry:
            parts.append(f"[{date}]\n{entry}")

    if not parts:
        return ""
    return "이전 세션 요약 (최근 3개):\n\n" + "\n\n".join(parts)


def main() -> None:
    raw = sys.stdin.read() or "{}"
    data = json.loads(raw)
    cwd = data.get("cwd", os.getcwd())
    is_codex = bool(data.get("model"))

    worklog_dir = resolve_worklog_dir(cwd)
    if worklog_dir is None:
        sys.exit(0)

    context = build_context(worklog_dir)
    if not context:
        sys.exit(0)

    if is_codex:
        print(json.dumps({"systemMessage": context}))
    else:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        }))


if __name__ == "__main__":
    main()
