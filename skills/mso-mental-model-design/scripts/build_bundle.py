#!/usr/bin/env python3
"""Build a minimal mental_model_bundle from workflow topology."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SKILL_ROOT / "schemas" / "mental_model_bundle.schema.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build mental_model_bundle.json")
    parser.add_argument("--topology", required=True, help="Path to workflow_topology_spec.json")
    parser.add_argument("--output", default="outputs/mental_model_bundle.json")
    parser.add_argument("--domain", default="General")
    return parser.parse_args()


def load_json(path: str) -> Dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(topology: Dict, domain: str) -> Dict:
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
        "run_id": topology.get("run_id", f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"),
        "domain": domain,
        "bundle_ref": f"bundle-{datetime.now().strftime('%Y%m%d%H%M%S')}",
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
            "created_at": datetime.now().isoformat(),
            "source_topology": topology.get("topology_type", "-"),
        },
    }


def main() -> int:
    args = parse_args()
    topology = load_json(args.topology)
    bundle = build(topology, args.domain)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
