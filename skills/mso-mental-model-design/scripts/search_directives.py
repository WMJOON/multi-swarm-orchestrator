#!/usr/bin/env python3
"""Search vertex registry for matching directives."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Reuse parser and matcher from bind_directives
SKILL_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_SCRIPTS))
from bind_directives import _load_registry, _match_score  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Search directives in vertex registry")
    p.add_argument("--registry", required=True, help="Path to vertex_registry directory")
    p.add_argument("--vertex-type", default="agent", help="Vertex type filter")
    p.add_argument("--motif", default="chain", help="Motif filter")
    p.add_argument("--domain", default="general", help="Domain filter")
    p.add_argument("--top-k", type=int, default=5, help="Max results")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    reg = Path(args.registry).expanduser().resolve()
    if not reg.is_dir():
        print(f"ERROR: registry not found: {reg}", file=sys.stderr)
        return 1

    directives = _load_registry(reg)
    scored = []
    for d in directives:
        s = _match_score(d, args.vertex_type, args.motif, args.domain)
        scored.append({"score": s, **{k: v for k, v in d.items() if k != "_path"}, "path": d.get("_path", "")})
    scored.sort(key=lambda x: -x["score"])
    results = scored[: args.top_k]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"  [{r['score']:.3f}] {r.get('id','')} — {r.get('name','')} ({r.get('type','')}) @ {r.get('path','')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
