#!/usr/bin/env python3
"""Build mental model bundle for runtime workspace."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

PACK_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PACK_ROOT / "config.yaml"

if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from mso_runtime.runtime_workspace import (  # noqa: E402
    resolve_runtime_paths,
    sanitize_case_slug,
    update_manifest_phase,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build mental_model_bundle.json")
    parser.add_argument("--topology", default="", help="Path to workflow_topology_spec.json")
    parser.add_argument("--output", default="", help="Optional output path override")
    parser.add_argument("--domain", default="General")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to orchestrator config")
    parser.add_argument("--run-id", default="", help="Run ID override")
    parser.add_argument("--skill-key", default="msowd", help="Skill key for run-id generation")
    parser.add_argument("--case-slug", default="", help="Case slug for run-id generation")
    parser.add_argument("--observer-id", default="", help="Observer ID override")
    return parser.parse_args()


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(topology: Dict, domain: str, run_id: str) -> Dict:
    nodes = topology.get("nodes") or []
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("topology.nodes must be a non-empty list")

    local_charts: List[Dict[str, object]] = []
    node_chart_map: Dict[str, List[str]] = {}

    for idx, node in enumerate(nodes, start=1):
        node_id = node.get("id", f"T{idx}")
        chart_id = f"chart_{node_id}"
        local_charts.append(
            {
                "id": chart_id,
                "name": f"Chart for {node_id}",
                "type": "validation",
                "owner": "mental-model-design",
            }
        )
        node_chart_map[node_id] = [chart_id]

    return {
        "run_id": run_id,
        "domain": domain,
        "bundle_ref": f"bundle-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "core_axioms": ["traceable output first", "small state transitions"],
        "local_charts": local_charts,
        "module_index": ["module.bundle-contract", "module.loading-policy", "module.routing-kpi"],
        "node_chart_map": node_chart_map,
        "execution_checkpoints": {
            "stage": "preflight",
            "criteria": ["node coverage", "chart coverage", "checkpoint readiness"],
        },
        "loading_policy": "on_demand",
        "output_contract": {
            "format": "execution_plan_ready",
            "min_fields": ["bundle_ref", "node_chart_map", "local_charts"],
        },
        "metadata": {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "source_topology": topology.get("topology_type", "-"),
        },
    }


def main() -> int:
    args = parse_args()

    case_slug = sanitize_case_slug(args.case_slug or "bundle")
    paths = resolve_runtime_paths(
        config_path=args.config,
        run_id=args.run_id.strip() or None,
        skill_key=args.skill_key,
        case_slug=case_slug,
        observer_id=args.observer_id.strip() or None,
        create=True,
    )

    topology_path = Path(args.topology).expanduser().resolve() if args.topology else Path(paths["topology_path"])
    out = Path(args.output).expanduser().resolve() if args.output else Path(paths["bundle_path"])

    try:
        update_manifest_phase(paths, "20", "active")
        topology = load_json(topology_path)
        run_id = str(topology.get("run_id") or paths["run_id"])
        bundle = build(topology, args.domain, run_id)

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        update_manifest_phase(paths, "20", "completed")
    except Exception:
        update_manifest_phase(paths, "20", "failed")
        raise

    print(f"WROTE {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
