#!/usr/bin/env python3
"""Build mental model bundle for runtime workspace."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

PACK_ROOT = Path(__file__).resolve().parents[3]

if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from skills._shared.runtime_workspace import (  # noqa: E402
    resolve_runtime_paths,
    sanitize_case_slug,
    update_manifest_phase,
)

# ---------------------------------------------------------------------------
# GT Angle helpers
# ---------------------------------------------------------------------------
THETA_RANGE_MAP = {
    "narrow": {"min": 0.0, "max": 0.2},
    "moderate": {"min": 0.2, "max": 0.6},
    "wide": {"min": 0.4, "max": 0.9},
}

WIDEN_MAP = {
    "narrow": "moderate",
    "moderate": "wide",
    "wide": "wide",
}


def _resolve_gt_angle(
    node: Dict,
    policy: str,
) -> Dict[str, object]:
    """Resolve GT Angle for a chart based on topology node and policy."""
    band = node.get("theta_gt_band", "moderate")
    topo_range = node.get("theta_gt_range")
    se = node.get("semantic_entropy_expected")

    if policy == "widen":
        band = WIDEN_MAP.get(band, band)
        topo_range = None  # recalculate from widened band
        se = None

    if topo_range is None:
        topo_range = THETA_RANGE_MAP.get(band, THETA_RANGE_MAP["moderate"])
    if se is None:
        se = round((topo_range["min"] + topo_range["max"]) / 2, 2)

    return {
        "theta_gt_band": band,
        "theta_gt_range": topo_range,
        "semantic_entropy_expected": se,
        "gt_angle_policy": policy,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build mental_model_bundle.json")
    parser.add_argument("--topology", default="", help="Path to workflow_topology_spec.json")
    parser.add_argument("--output", default="", help="Optional output path override")
    parser.add_argument("--domain", default="General")
    parser.add_argument(
        "--gt-policy",
        default="inherit",
        choices=["inherit", "widen", "override"],
        help="GT Angle policy: inherit (from topology), widen (one step wider), override (manual)",
    )
    parser.add_argument("--run-id", default="", help="Run ID override")
    parser.add_argument("--skill-key", default="msowd", help="Skill key for run-id generation")
    parser.add_argument("--case-slug", default="", help="Case slug for run-id generation")
    parser.add_argument("--observer-id", default="", help="Observer ID override")
    return parser.parse_args()


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(topology: Dict, domain: str, run_id: str, gt_policy: str = "inherit") -> Dict:
    nodes = topology.get("nodes") or []
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("topology.nodes must be a non-empty list")

    local_charts: List[Dict[str, object]] = []
    node_chart_map: Dict[str, List[str]] = {}

    for idx, node in enumerate(nodes, start=1):
        node_id = node.get("id", f"T{idx}")
        chart_id = f"chart_{node_id}"

        gt = _resolve_gt_angle(node, gt_policy)

        local_charts.append(
            {
                "id": chart_id,
                "name": f"Chart for {node_id}",
                "type": "validation",
                "owner": "mental-model-design",
                **gt,
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
        "gt_angle_config": {
            "default_policy": gt_policy,
        },
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
        bundle = build(topology, args.domain, run_id, gt_policy=args.gt_policy)

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
