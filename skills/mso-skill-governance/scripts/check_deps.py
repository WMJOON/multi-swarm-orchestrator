#!/usr/bin/env python3
"""Check runtime dependencies for multi-swarm-orchestrator v0.0.1.

This script is environment-tolerant:
- `ai-collaborator` is optional.
- Missing dependency does not block core pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class DependencyResult:
    name: str
    configured: bool
    resolved_path: str | None
    reason: str
    status: str  # ok | warning | error


try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


def parse_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    if yaml is None:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            # Fallback: very small, safe parser for simple key/value yaml-like text.
            pass
        out: Dict[str, Any] = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"\'')
            if value.startswith("[") and value.endswith("]"):
                arr = [item.strip().strip('"\'') for item in value[1:-1].split(",") if item.strip()]
                out[key] = arr
            elif value.lower() in ("true", "false"):
                out[key] = value.lower() == "true"
            elif value.isdigit():
                out[key] = int(value)
            else:
                out[key] = value
        return out

    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg if isinstance(cfg, dict) else {}


def detect_path_for_ai(root: Path, dep_cfg: Dict[str, Any]) -> str | None:
    resolve_order = dep_cfg.get("resolve_order") or []
    if not isinstance(resolve_order, list):
        return None

    for item in resolve_order:
        if not isinstance(item, dict):
            continue
        if "env" in item:
            raw = os.environ.get(str(item["env"]).strip())
            if raw:
                candidate = Path(raw).expanduser()
                if candidate.exists():
                    return str(candidate)

        if "relative" in item:
            candidate = (root / str(item["relative"]).strip()).resolve()
            if candidate.exists():
                return str(candidate)

    return None


def check_ai_collaborator(dep_cfg: Dict[str, Any]) -> DependencyResult:
    path = detect_path_for_ai(ROOT, dep_cfg)
    if not path:
        return DependencyResult(
            name="ai-collaborator",
            configured=False,
            resolved_path=None,
            reason="not found via env/relative resolve",
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
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    cfg_path = (ROOT / args.config).resolve()
    cfg = parse_config(cfg_path)
    deps = cfg.get("external_dependencies")
    if not isinstance(deps, dict):
        print("ERR: missing external_dependencies in config", file=__import__("sys").stderr)
        return 2

    dep_cfg = deps.get("ai-collaborator")
    if not isinstance(dep_cfg, dict):
        print("ERR: ai-collaborator dependency config missing", file=__import__("sys").stderr)
        return 2

    result = check_ai_collaborator(dep_cfg)

    if args.json:
        print(json.dumps(result.__dict__))
    else:
        print(f"Dependency check: {result.name}")
        print(f"  configured: {result.configured}")
        print(f"  status: {result.status}")
        print(f"  path: {result.resolved_path or '-'}")
        print(f"  reason: {result.reason}")

        if not result.configured:
            fallback = dep_cfg.get("fallback") if isinstance(dep_cfg, dict) else None
            if isinstance(fallback, str):
                print("\nFallback guidance:")
                print(fallback)

    # ai-collaborator is optional by design
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
