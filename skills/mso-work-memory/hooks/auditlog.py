#!/usr/bin/env python3
"""
PostToolUse hook — 일별 auditlog 파일에 도구 호출 기록.

Claude Code PostToolUse JSON 을 stdin 으로 받아
WORKMEM_DIR/auditlog/AU-YYYY-MM-DD.jsonl 에 한 줄 append 한다.
추적 대상: Bash, Edit, MultiEdit, Write
"""
import datetime
import json
import os
import sys
from pathlib import Path

TRACKED_TOOLS = {"Bash", "Edit", "MultiEdit", "Write"}


def _summarize(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Bash":
        return str(tool_input.get("command", ""))[:200]
    if tool_name in ("Edit", "MultiEdit"):
        return str(tool_input.get("file_path", ""))[:200]
    if tool_name == "Write":
        return str(tool_input.get("file_path", ""))[:200]
    return str(tool_input)[:200]


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    tool_name = data.get("tool_name", "")
    if tool_name not in TRACKED_TOOLS:
        return

    workmem = Path(os.environ.get("WORKMEM_DIR", "./agent-context/work-memory")).resolve()
    if not workmem.exists():
        return

    auditlog_dir = workmem / "auditlog"
    auditlog_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc)
    file_path = auditlog_dir / f"AU-{now.strftime('%Y-%m-%d')}.jsonl"

    summary = _summarize(tool_name, data.get("tool_input", {}))
    entry = {
        "id": f"AU-{now.strftime('%Y%m%d-%H%M%S')}",
        "type": "auditlog",
        "title": f"{tool_name}: {summary[:80]}",
        "text": summary,
        "tags": ["auditlog", tool_name.lower()],
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "author": "agent",
        "metadata": {
            "tool": tool_name,
            "session_id": data.get("session_id", ""),
        },
    }

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
