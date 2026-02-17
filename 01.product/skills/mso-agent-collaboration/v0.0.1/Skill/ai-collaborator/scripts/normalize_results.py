#!/usr/bin/env python3
"""
Normalize AI Collaborator results into a JSON list.

Accepts:
- v0.3 `--format json` output: a list of result objects
- v0.2 `--format json` output: a map keyed by task id

Usage:
  python3 scripts/normalize_results.py results.json > results.normalized.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def normalize(obj: Any) -> List[Dict[str, Any]]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        if obj.get("type") in {"status", "tokens"}:
            return [obj]
        return [v for v in obj.values() if isinstance(v, dict)]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize collaborator JSON results into a list")
    parser.add_argument("file", nargs="?", help="Input JSON file (default: stdin)")
    args = parser.parse_args()

    raw = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    obj = json.loads(raw)
    out = normalize(obj)
    sys.stdout.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

