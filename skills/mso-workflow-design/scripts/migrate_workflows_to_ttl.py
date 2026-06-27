#!/usr/bin/env python3
"""Migrate legacy workflow YAML files to TTL ABox SSOT files.

TTL is the workflow source of truth. YAML is accepted only as a legacy import
format. This helper compiles each selected YAML file to a sibling
``*.abox.ttl`` file so future workflow work can continue in TTL.

Usage:
  python migrate_workflows_to_ttl.py agent-context/workflow
  python migrate_workflows_to_ttl.py agent-context/workflow --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR))
import wf_to_ttl  # noqa: E402


DEFAULT_PATTERNS = ("*workflow*.yaml", "*workflow*.yml")


def _iter_yaml(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    if root.is_file():
        return [root]
    seen: set[Path] = set()
    out: list[Path] = []
    for pattern in patterns:
        for path in root.rglob(pattern):
            if path.name.startswith(".") or path in seen:
                continue
            seen.add(path)
            out.append(path)
    return sorted(out)


def _ttl_path(yaml_path: Path) -> Path:
    suffixes = "".join(yaml_path.suffixes)
    if suffixes.endswith(".yaml") or suffixes.endswith(".yml"):
        return yaml_path.with_suffix("").with_suffix(".abox.ttl")
    return yaml_path.with_suffix(".abox.ttl")


def _serialize(yaml_path: Path) -> str:
    graph, _ = wf_to_ttl.build_graph(yaml_path.resolve())
    return graph.serialize(format="turtle")


def migrate(root: Path, patterns: tuple[str, ...], check: bool = False) -> int:
    yaml_paths = _iter_yaml(root, patterns)
    if not yaml_paths:
        print(f"[WARN] workflow YAML 없음: {root}", file=sys.stderr)
        return 0

    changed: list[Path] = []
    for yaml_path in yaml_paths:
        ttl_path = _ttl_path(yaml_path)
        ttl_text = _serialize(yaml_path)
        current = ttl_path.read_text(encoding="utf-8") if ttl_path.exists() else None
        if current != ttl_text:
            changed.append(ttl_path)
            if not check:
                ttl_path.write_text(ttl_text, encoding="utf-8")
                print(f"WRITE {ttl_path}")
        else:
            print(f"OK    {ttl_path}")

    if check and changed:
        print("[ERROR] TTL 정본이 legacy YAML migration 결과와 다릅니다:", file=sys.stderr)
        for path in changed:
            print(f"  {path}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_workflows_to_ttl",
        description="Import legacy workflow YAML files into TTL ABox SSOT files.",
    )
    parser.add_argument("root", help="workflow YAML 파일 또는 workflow 디렉토리")
    parser.add_argument(
        "--pattern",
        action="append",
        default=None,
        help="추가 glob 패턴. 기본값: *workflow*.yaml, *workflow*.yml",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="쓰기 없이 기존 *.abox.ttl 과 비교한다. drift 가 있으면 exit 1.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[ERROR] 경로 없음: {root}", file=sys.stderr)
        return 2
    patterns = tuple(args.pattern) if args.pattern else DEFAULT_PATTERNS
    return migrate(root, patterns, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
