#!/usr/bin/env python3
"""Check runtime dependencies for multi-swarm-orchestrator.

Verifies that required skill scripts and modules are present.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class DependencyResult:
    name: str
    configured: bool
    resolved_path: str | None
    reason: str
    status: str  # ok | warning | error


def check_mso_agent_collaboration() -> DependencyResult:
    """Verify mso-agent-collaboration dispatch script is present."""
    skill_dir = ROOT / "skills" / "mso-agent-collaboration"
    dispatch_script = skill_dir / "scripts" / "dispatch.py"

    if not skill_dir.exists():
        return DependencyResult(
            name="mso-agent-collaboration",
            configured=False,
            resolved_path=None,
            reason="skill directory not found",
            status="error",
        )

    if not dispatch_script.exists():
        return DependencyResult(
            name="mso-agent-collaboration",
            configured=False,
            resolved_path=str(skill_dir),
            reason="dispatch.py script missing",
            status="error",
        )

    return DependencyResult(
        name="mso-agent-collaboration",
        configured=True,
        resolved_path=str(skill_dir),
        reason="available",
        status="ok",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check runtime dependencies.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    results: List[DependencyResult] = [
        check_mso_agent_collaboration(),
    ]

    has_error = False
    for result in results:
        if result.status == "error":
            has_error = True
        if args.json:
            print(json.dumps(result.__dict__))
        else:
            print(f"Dependency check: {result.name}")
            print(f"  configured: {result.configured}")
            print(f"  status: {result.status}")
            print(f"  path: {result.resolved_path or '-'}")
            print(f"  reason: {result.reason}")

    return 1 if has_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
