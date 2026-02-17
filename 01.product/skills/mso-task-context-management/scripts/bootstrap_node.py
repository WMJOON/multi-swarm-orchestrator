#!/usr/bin/env python3
"""Bootstrap task-context workspace."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="task-context")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    root = Path(args.path)
    tickets = root / "tickets"
    archive = root / "archive"
    if root.exists() and not args.force:
        print(f"ALREADY_EXISTS: {root}")
        return 0

    tickets.mkdir(parents=True, exist_ok=True)
    (root / "RULE.md").write_text("# Task Context Rule\n", encoding="utf-8")
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "README.md").write_text("# Archive\n", encoding="utf-8")
    print(f"BOOTSTRAPPED: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
