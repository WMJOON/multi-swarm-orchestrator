#!/usr/bin/env python3
"""Update ticket status with transition guard."""

from __future__ import annotations

import argparse
from pathlib import Path

ALLOWED = {
    "todo": {"in_progress", "blocked", "cancelled", "todo"},
    "in_progress": {"done", "blocked", "todo", "in_progress"},
    "blocked": {"in_progress", "cancelled", "todo", "blocked"},
    "done": {"done"},
    "cancelled": {"cancelled"},
}


def read_status(content: str) -> str | None:
    for line in content.splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    return None


def replace_status(content: str, status: str) -> str:
    out = []
    replaced = False
    for line in content.splitlines():
        if not replaced and line.startswith("status:"):
            out.append(f"status: {status}")
            replaced = True
        elif line.startswith("state:"):
            # Remove legacy state field if present
            continue
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if not content.endswith("\n") else "")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("ticket")
    p.add_argument("--status", required=True, choices=["todo", "in_progress", "blocked", "done", "cancelled"])
    args = p.parse_args()

    path = Path(args.ticket)
    text = path.read_text(encoding="utf-8")
    current = read_status(text)
    if current is None:
        print("ERR: status not found", file=__import__('sys').stderr)
        return 1

    if args.status not in ALLOWED.get(current, set()):
        print(f"ERR: invalid transition {current} -> {args.status}", file=__import__('sys').stderr)
        return 1

    new_text = replace_status(text, args.status)
    path.write_text(new_text, encoding="utf-8")

    print(f"UPDATED: {path.name} {current} -> {args.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
