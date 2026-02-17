#!/usr/bin/env python3
"""Validate task-context node and dependencies."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--path", default="task-context")
    args = p.parse_args()
    root = Path(args.path)
    tickets = root / "tickets"
    if not tickets.exists():
        print("ERR: tickets directory missing")
        return 1

    issues = []
    files = {f.stem: f for f in tickets.glob("*.md")}
    for path in files.values():
        lines = path.read_text(encoding="utf-8").splitlines()
        front = {}
        in_front = False
        for ln in lines:
            if ln == "---":
                if not in_front:
                    in_front = True
                    continue
                break
            if in_front and ":" in ln:
                k, v = ln.split(":", 1)
                front[k.strip()] = v.strip()

        deps = front.get("dependencies", "[]")
        if isinstance(deps, str) and deps.startswith("[") and deps.endswith("]"):
            dep_items = [x.strip().strip("\"'") for x in deps[1:-1].split(",") if x.strip()]
        else:
            dep_items = []
        for dep in dep_items:
            if dep and dep not in files:
                issues.append(f"{path.name} dependency missing: {dep}")

    if issues:
        print("VALIDATION_FAIL")
        for i in issues:
            print(i)
        return 1

    print("VALIDATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
