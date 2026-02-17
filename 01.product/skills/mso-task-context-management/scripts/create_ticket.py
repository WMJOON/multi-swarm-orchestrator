#!/usr/bin/env python3
"""Create a ticket in task-context/tickets."""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path


def normalize_title(title: str) -> str:
    base = re.sub(r"[^A-Za-z0-9가-힣 _-]", "", title).strip().replace(" ", "-")
    base = re.sub(r"[-_]{2,}", "-", base)
    return base[:60] if base else "ticket"


def _default_due_by() -> str:
    return (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")


def next_ticket_id(path: Path) -> int:
    nums = []
    for f in path.glob("TKT-*.md"):
        m = re.match(r"TKT-(\d+)", f.stem)
        if m:
            nums.append(int(m.group(1)))
    return max(nums, default=0) + 1


def main() -> int:
    p = argparse.ArgumentParser(description="Create ticket")
    p.add_argument("title")
    p.add_argument("--path", default="task-context")
    p.add_argument("--status", default="todo", choices=["todo", "in_progress", "blocked", "done", "cancelled"])
    p.add_argument("--priority", default="medium", choices=["low", "medium", "high", "critical"])
    p.add_argument("--owner", default="")
    p.add_argument("--due-by", default="")
    p.add_argument("--tags", nargs="*", default=[])
    p.add_argument("--deps", nargs="*", default=[])
    args = p.parse_args()

    root = Path(args.path)
    tickets = root / "tickets"
    tickets.mkdir(parents=True, exist_ok=True)

    ticket_id = f"TKT-{next_ticket_id(tickets):04d}"
    slug = normalize_title(args.title)
    filename = f"{ticket_id}-{slug}.md"
    path = tickets / filename
    if path.exists():
        return 1

    due_by = args.due_by.strip() if args.due_by is not None else ""
    if not due_by:
        due_by = _default_due_by()

    deps = [d.strip() for d in args.deps if d.strip()]
    path.write_text(
        "---\n"
        f"id: {ticket_id}\n"
        f"task_context_id: {ticket_id}\n"
        f"status: {args.status}\n"
        f"priority: {args.priority}\n"
        f"owner: {args.owner}\n"
        f"due_by: {due_by}\n"
        f"dependencies: {deps}\n"
        f"tags: {args.tags}\n"
        f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
        "updated: null\n"
        "---\n\n"
        f"# {args.title}\n",
        encoding="utf-8",
    )

    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
