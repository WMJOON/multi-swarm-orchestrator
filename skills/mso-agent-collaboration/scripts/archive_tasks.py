#!/usr/bin/env python3
"""Close done/cancelled tickets: log to ticket_closure_log.md, then delete."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from datetime import datetime, timezone


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter key-value pairs (flat, string values only)."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    result: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


LOG_HEADER = """# Ticket Closure Log

## Closed Tickets

| id | status_at_close | owner | tags | closed_at |
| -- | --------------- | ----- | ---- | --------- |
"""


def _ensure_log(log_path: Path) -> None:
    """Create log file with header if it doesn't exist."""
    if not log_path.exists():
        log_path.write_text(LOG_HEADER, encoding="utf-8")


def _append_row(log_path: Path, fm: dict[str, str], now: str) -> None:
    tid = fm.get("id", "?")
    status = fm.get("status", "?")
    owner = fm.get("owner", "?")
    tags = fm.get("tags", "")
    log_path.open("a", encoding="utf-8").write(
        f"| {tid} | {status} | {owner} | {tags} | {now} |\n"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Close done/cancelled tickets (log + delete)")
    p.add_argument("--path", default="task-context", help="task-context root")
    args = p.parse_args()

    root = Path(args.path)
    tickets = root / "tickets"
    log_path = root / "ticket_closure_log.md"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not tickets.is_dir():
        print("NO_TICKETS_DIR")
        return 0

    _ensure_log(log_path)

    closed = 0
    for t in sorted(tickets.glob("*.md")):
        text = t.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        status = fm.get("status")
        if status not in ("done", "cancelled"):
            continue

        # Log the closure
        _append_row(log_path, fm, now)

        # Delete ticket + companion json
        stem = t.stem
        companion = tickets / f"{stem}.agent-collaboration.json"
        t.unlink()
        if companion.exists():
            companion.unlink()
        closed += 1
        print(f"CLOSED: {t.name} (status={status})")

    if closed:
        print(f"Total closed: {closed}")
    else:
        print("NO_CLOSABLE_TICKETS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
