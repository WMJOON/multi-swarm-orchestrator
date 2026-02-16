#!/usr/bin/env python3
"""Build execution_plan.json from topology + mental model bundle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SKILL_ROOT / "schemas" / "execution_plan.schema.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build execution_plan.json")
    p.add_argument("--topology", required=True)
    p.add_argument("--bundle", required=True)
    p.add_argument("--output", default="outputs/execution_plan.json")
    return p.parse_args()


def load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def infer_mode(theta: str) -> str:
    if theta == "wide":
        return "dontAsk"
    if theta == "moderate":
        return "default"
    return "plan"


def build(topology: dict, bundle: dict) -> dict:
    nodes = topology.get("nodes") or []
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("topology.nodes is empty")

    topo_node_ids = [str(n.get("id")) for n in nodes if n.get("id")]
    chart_map = bundle.get("node_chart_map") or {}
    if not isinstance(chart_map, dict):
        chart_map = {}

    node_chart_map = {}
    task_to_chart_map = {}
    node_mode_policy = {}
    model_policy = {}

    for node in nodes:
        node_id = str(node.get("id"))
        theta = str(node.get("theta_gt_band", "moderate"))
        charts = chart_map.get(node_id)
        if not charts:
            # fallback: generate deterministic chart reference from bundle local chart list
            fallback_chart = f"chart_{node_id}"
            charts = [fallback_chart]
        if not isinstance(charts, list):
            charts = [str(charts)]

        node_chart_map[node_id] = {
            "chart_ids": [str(c) for c in charts if c],
            "checkpoint_id": topology.get("strategy_gate") and "pre_h2" or "preflight",
        }

        task_to_chart_map[node_id] = [str(c) for c in charts if c]
        node_mode_policy[node_id] = infer_mode(theta)
        model_policy[node_id] = "gpt-4o-mini" if theta != "wide" else "claude-3.5-sonnet"

    return {
        "run_id": topology.get("run_id", f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"),
        "bundle_ref": bundle.get("bundle_ref", "bundle-unknown"),
        "node_chart_map": node_chart_map,
        "task_to_chart_map": task_to_chart_map,
        "node_mode_policy": node_mode_policy,
        "model_selection_policy": model_policy,
        "handoff_contract": {
            "required_keys": ["output", "status", "evidence"],
            "target": "next_node",
            "format": "json",
        },
        "fallback_rules": {
            "retry": {
                "max_retries": 2,
                "retry_interval_s": 10,
            },
            "on_failure": "send_hitl_request",
        },
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "nodes_processed": topo_node_ids,
        },
    }


def main() -> int:
    args = parse_args()
    topology = load_json(args.topology)
    bundle = load_json(args.bundle)

    for req in ["nodes", "topology_type"]:
        if req not in topology:
            raise SystemExit(f"invalid topology: missing {req}")

    for req in ["bundle_ref", "local_charts"]:
        if req not in bundle:
            raise SystemExit(f"invalid bundle: missing {req}")

    output = build(topology, bundle)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
