#!/usr/bin/env python3
"""Shared utilities for mso-agent-audit-log hooks."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

SUMMARY_MAX = 200
_WRITE_TOOL_NAMES = ("Write", "Edit")


def resolve_worklog_dir(cwd: str) -> Path | None:
    env_dir = os.environ.get("WORKLOG_DIR", "")
    if env_dir:
        return Path(env_dir)
    candidate = Path(cwd) / "00.agent_log" / "logs"
    return candidate if candidate.is_dir() else None


def parse_transcript(path: str) -> tuple[list[str], str]:
    """Return (sorted files_affected, last_assistant_summary) from transcript JSONL."""
    files: set[str] = set()
    last_summary = ""
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = entry.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type", "")
                        if btype == "tool_use" and block.get("name") in _WRITE_TOOL_NAMES:
                            fp = block.get("input", {}).get("file_path", "")
                            if fp:
                                files.add(fp)
                        elif btype == "text" and entry.get("role") == "assistant":
                            text = block.get("text", "").strip()
                            if text:
                                last_summary = text
                elif isinstance(content, str) and entry.get("role") == "assistant":
                    if content.strip():
                        last_summary = content.strip()
    except Exception:
        pass
    return sorted(files), last_summary[:SUMMARY_MAX].replace("\n", " ")


def write_worklog_entry(
    worklog: Path,
    session_id: str,
    event: str,
    files: list[str],
    summary: str,
    now: datetime,
) -> None:
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"\n## {timestamp} — {event}",
        f"- session: `{session_id}`",
        f"- files: {', '.join(f'`{f}`' for f in files) if files else '(없음)'}",
    ]
    if summary:
        lines.append(f"- summary: {summary}")
    lines.append("")
    worklog.parent.mkdir(parents=True, exist_ok=True)
    with worklog.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
