#!/usr/bin/env python3
"""Build execution_plan.json from topology + mental model bundle."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[3]

if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from skills._shared.runtime_workspace import (  # noqa: E402
    resolve_runtime_paths,
    sanitize_case_slug,
    update_manifest_phase,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build execution_plan.json")
    p.add_argument("--topology", default="", help="Path to workflow_topology_spec.json")
    p.add_argument("--bundle", default="", help="Path to mental_model_bundle.json")
    p.add_argument("--output", default="", help="Optional output path override")
    p.add_argument("--run-id", default="", help="Run ID override")
    p.add_argument("--skill-key", default="msowd", help="Skill key for run-id generation")
    p.add_argument("--case-slug", default="", help="Case slug for run-id generation")
    p.add_argument("--observer-id", default="", help="Observer ID override")
    return p.parse_args()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def infer_mode(theta: str) -> str:
    if theta == "wide":
        return "dontAsk"
    if theta == "moderate":
        return "default"
    return "plan"


def build(topology: dict, bundle: dict, run_id: str) -> dict:
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
        "run_id": run_id,
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
            "created_at": datetime.utcnow().isoformat() + "Z",
            "nodes_processed": topo_node_ids,
        },
    }


def main() -> int:
    args = parse_args()

    case_slug = sanitize_case_slug(args.case_slug or "execution-plan")
    paths = resolve_runtime_paths(
        run_id=args.run_id.strip() or None,
        skill_key=args.skill_key,
        case_slug=case_slug,
        observer_id=args.observer_id.strip() or None,
        create=True,
    )

    topo_path = Path(args.topology).expanduser().resolve() if args.topology else Path(paths["topology_path"])
    bundle_path = Path(args.bundle).expanduser().resolve() if args.bundle else Path(paths["bundle_path"])
    out = Path(args.output).expanduser().resolve() if args.output else Path(paths["execution_plan_path"])

    try:
        update_manifest_phase(paths, "30", "active")
        topology = load_json(topo_path)
        bundle = load_json(bundle_path)

        for req in ["nodes", "topology_type"]:
            if req not in topology:
                raise SystemExit(f"invalid topology: missing {req}")

        for req in ["bundle_ref", "local_charts"]:
            if req not in bundle:
                raise SystemExit(f"invalid bundle: missing {req}")

        run_id = str(topology.get("run_id") or bundle.get("run_id") or paths["run_id"])
        output = build(topology, bundle, run_id)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        update_manifest_phase(paths, "30", "completed")
    except Exception:
        update_manifest_phase(paths, "30", "failed")
        raise

    print(f"WROTE {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
