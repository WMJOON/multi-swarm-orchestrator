#!/usr/bin/env python3
"""Check runtime dependencies for multi-swarm-orchestrator v0.0.2.

This script is environment-tolerant:
- `ai-collaborator` is optional.
- Missing dependency does not block core pipeline.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class DependencyResult:
    name: str
    configured: bool
    resolved_path: str | None
    reason: str
    status: str  # ok | warning | error


def detect_path_for_ai(root: Path) -> str | None:
    embedded = root / "skills" / "mso-agent-collaboration"
    embedded_marker = embedded / "v0.0.1" / "Skill" / "ai-collaborator" / "scripts" / "collaborate.py"
    if embedded_marker.exists():
        return str(embedded.resolve())
    return None


def check_ai_collaborator() -> DependencyResult:
    path = detect_path_for_ai(ROOT)
    if not path:
        return DependencyResult(
            name="ai-collaborator",
            configured=False,
            resolved_path=None,
            reason="embedded ai-collaborator runtime not found",
            status="warning",
        )

    candidate = Path(path)
    script = candidate / "v0.0.1" / "Skill" / "ai-collaborator" / "scripts" / "collaborate.py"
    if not script.exists():
        return DependencyResult(
            name="ai-collaborator",
            configured=False,
            resolved_path=str(candidate),
            reason="resolve success but collaborate.py missing (expected v0.0.1/Skill/ai-collaborator/scripts/collaborate.py)",
            status="warning",
        )

    try:
        proc = subprocess.run(
            ["python3", str(script), "status", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode != 0:
            return DependencyResult(
                name="ai-collaborator",
                configured=False,
                resolved_path=str(candidate),
                reason=(proc.stderr or proc.stdout or "healthcheck failed").strip()[:180],
                status="warning",
            )
    except Exception as exc:
        return DependencyResult(
            name="ai-collaborator",
            configured=False,
            resolved_path=str(candidate),
            reason=f"healthcheck invocation error: {exc}",
            status="warning",
        )

    return DependencyResult(
        name="ai-collaborator",
        configured=True,
        resolved_path=str(candidate),
        reason="available and healthy",
        status="ok",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check runtime dependencies.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    result = check_ai_collaborator()

    if args.json:
        print(json.dumps(result.__dict__))
    else:
        print(f"Dependency check: {result.name}")
        print(f"  configured: {result.configured}")
        print(f"  status: {result.status}")
        print(f"  path: {result.resolved_path or '-'}")
        print(f"  reason: {result.reason}")

    # ai-collaborator is optional by design
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
