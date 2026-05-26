#!/usr/bin/env python3
"""
Stop hook — 일별 worklog 파일에 세션 종료 기록.

Claude Code Stop JSON 을 stdin 으로 받아
WORKMEM_DIR/worklog/WL-YYYY-MM-DD.jsonl 에 한 줄 append 한다.
같은 날 여러 세션 종료는 같은 파일에 누적된다.
"""
import datetime
import json
import os
import sys
from pathlib import Path


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    workmem = Path(os.environ.get("WORKMEM_DIR", "./agent-context/work-memory")).resolve()
    if not workmem.exists():
        return

    worklog_dir = workmem / "worklog"
    worklog_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc)
    file_path = worklog_dir / f"WL-{now.strftime('%Y-%m-%d')}.jsonl"

    session_id = data.get("session_id", "")
    entry = {
        "id": f"WL-{now.strftime('%Y%m%d-%H%M%S')}",
        "type": "worklog",
        "title": f"세션 종료 — {now.strftime('%Y-%m-%d %H:%M')} UTC",
        "text": f"session_id={session_id}",
        "tags": ["worklog"],
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "author": "agent",
        "metadata": {
            "session_id": session_id,
            "event": "Stop",
        },
    }

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
