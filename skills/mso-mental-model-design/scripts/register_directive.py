#!/usr/bin/env python3
"""Register a new directive MD file into the vertex registry."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_SCRIPTS))
from bind_directives import _parse_frontmatter  # noqa: E402

REQUIRED_KEYS = {"id", "type", "name", "domain", "taxonomy_path"}
VALID_TYPES = {"framework", "instruction", "prompt"}


def validate_frontmatter(fm: dict) -> list[str]:
    errors = []
    missing = REQUIRED_KEYS - set(fm.keys())
    if missing:
        errors.append(f"missing keys: {missing}")
    if fm.get("type") and fm["type"] not in VALID_TYPES:
        errors.append(f"invalid type: {fm['type']} (expected {VALID_TYPES})")
    tp = fm.get("taxonomy_path")
    if tp and (not isinstance(tp, list) or len(tp) < 1 or len(tp) > 3):
        errors.append(f"taxonomy_path must be 1-3 elements, got {tp}")
    if tp and isinstance(tp, list) and fm.get("domain") and tp[0] != fm["domain"]:
        errors.append(f"taxonomy_path[0] ({tp[0]}) must match domain ({fm['domain']})")
    return errors


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Register directive to vertex registry")
    p.add_argument("--file", required=True, help="Path to directive MD file")
    p.add_argument("--registry", required=True, help="Path to vertex_registry directory")
    p.add_argument("--dry-run", action="store_true", help="Validate only, don't copy")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    src = Path(args.file).expanduser().resolve()
    reg = Path(args.registry).expanduser().resolve()

    if not src.exists():
        print(f"ERROR: file not found: {src}", file=sys.stderr)
        return 1

    fm = _parse_frontmatter(src)
    if not fm:
        print(f"ERROR: no valid frontmatter in {src}", file=sys.stderr)
        return 1

    errors = validate_frontmatter(fm)
    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        return 1

    domain = fm["domain"]
    dest_dir = reg / domain
    dest = dest_dir / src.name

    if args.dry_run:
        print(f"DRY-RUN: would copy {src} → {dest}")
        print(f"  frontmatter: {json.dumps(fm, ensure_ascii=False, default=str)}")
        return 0

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    print(f"REGISTERED {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
