#!/usr/bin/env python3
"""SessionEnd hook — transcript를 파싱해 worklog에 직접 기록."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from _common import parse_transcript, resolve_worklog_dir, write_worklog_entry


def main() -> None:
    data = json.loads(sys.stdin.read() or "{}")
    session_id = data.get("session_id", "unknown")
    transcript_path = data.get("transcript_path", "")
    cwd = data.get("cwd", os.getcwd())

    worklog_dir = resolve_worklog_dir(cwd)
    if worklog_dir is None:
        sys.exit(0)

    now = datetime.now()
    worklog = worklog_dir / f"worklog-{now.strftime('%Y%m%d')}.md"
    files, summary = parse_transcript(transcript_path) if transcript_path else ([], "")
    write_worklog_entry(worklog, session_id, "SessionEnd", files, summary, now)


if __name__ == "__main__":
    main()
