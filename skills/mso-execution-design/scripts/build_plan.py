#!/usr/bin/env python3
"""Build execution_plan.json from topology + directive binding.

v0.0.3: Outputs execution_graph (Git-metaphor state transition graph)
instead of flat node_chart_map / task_to_chart_map / node_mode_policy.
v0.0.7: Accepts directive_binding.json (Vertex Registry) instead of mental_model_bundle.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PACK_ROOT = Path(__file__).resolve().parents[3]

if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from skills._shared.runtime_workspace import (  # noqa: E402
    resolve_runtime_paths,
    sanitize_case_slug,
    update_manifest_phase,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build execution_plan.json (v0.0.3)")
    p.add_argument("--topology", default="", help="Path to workflow_topology_spec.json")
    p.add_argument("--bundle", default="", help="Path to directive_binding.json")
    p.add_argument("--output", default="", help="Optional output path override")
    p.add_argument("--run-id", default="", help="Run ID override")
    p.add_argument("--skill-key", default="msowd", help="Skill key for run-id generation")
    p.add_argument("--case-slug", default="", help="Case slug for run-id generation")
    p.add_argument("--observer-id", default="", help="Observer ID override")
    return p.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def infer_mode(theta: str) -> str:
    if theta == "wide":
        return "dontAsk"
    if theta == "moderate":
        return "default"
    return "plan"


def determine_node_type(node_id: str, topology: dict) -> str:
    """Classify node type based on edge connectivity.

    - merge: 2+ incoming edges (fan-in)
    - branch: 2+ outgoing edges from this node (fan-out source)
    - commit: default (linear chain)
    """
    edges = topology.get("edges") or []
    if not isinstance(edges, list):
        edges = []

    incoming = [e for e in edges if str(e.get("to", "")) == node_id]
    outgoing = [e for e in edges if str(e.get("from", "")) == node_id]

    if len(incoming) >= 2:
        return "merge"
    if len(outgoing) >= 2:
        return "branch"
    return "commit"


def compute_parent_refs(node_id: str, topology: dict) -> List[str]:
    """Return list of source node IDs that feed into this node."""
    edges = topology.get("edges") or []
    if not isinstance(edges, list):
        edges = []

    parents = [str(e.get("from", "")) for e in edges if str(e.get("to", "")) == node_id]
    return [p for p in parents if p]


def _build_directive_map(binding: dict) -> Dict[str, List[str]]:
    """Build node_id → directive_ids map from directive_binding.json."""
    result: Dict[str, List[str]] = {}
    for b in binding.get("bindings") or []:
        node_id = b.get("node_id", "")
        dirs = [d.get("directive_id", "") for d in b.get("directives") or [] if d.get("directive_id")]
        if node_id and dirs:
            result[node_id] = dirs
    return result


def build(topology: dict, bundle: dict, run_id: str) -> dict:
    nodes = topology.get("nodes") or []
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("topology.nodes is empty")

    # Support both legacy (node_chart_map) and new (bindings) format
    directive_map = _build_directive_map(bundle)
    legacy_chart_map = bundle.get("node_chart_map") or {}

    execution_graph: Dict[str, Any] = {}

    for node in nodes:
        node_id = str(node.get("id"))
        theta = str(node.get("theta_gt_band", "moderate"))

        # Prefer directive_map, fallback to legacy chart_map
        directive_refs = directive_map.get(node_id) or legacy_chart_map.get(node_id) or [f"dir-{node_id}"]
        if not isinstance(directive_refs, list):
            directive_refs = [str(directive_refs)]

        node_type = determine_node_type(node_id, topology)
        parent_refs = compute_parent_refs(node_id, topology)

        bundle_ref = bundle.get("bundle_ref") or bundle.get("run_id") or "binding-unknown"

        graph_node: Dict[str, Any] = {
            "type": node_type,
            "bundle_ref": bundle_ref,
            "parent_refs": parent_refs,
            "tree_hash_type": "sha256",
            "tree_hash_ref": None,
            "model_selection": "gpt-4o-mini" if theta != "wide" else "claude-3.5-sonnet",
            "directive_refs": directive_refs,
            "mode": infer_mode(theta),
            "handoff_contract": {
                "required_keys": ["output", "status", "evidence"],
                "target": "next_node",
                "format": "json",
            },
        }

        if node_type == "merge":
            graph_node["merge_policy"] = {
                "strategy": "score_weighted",
                "scoring_weights": {
                    "confidence": 0.4,
                    "completeness": 0.3,
                    "format_compliance": 0.3,
                },
                "quorum": max(2, len(parent_refs)),
                "manual_review_required": False,
            }

        execution_graph[node_id] = graph_node

    return {
        "run_id": run_id,
        "bundle_ref": bundle.get("bundle_ref") or bundle.get("run_id") or "binding-unknown",
        "execution_graph": execution_graph,
        "fallback_rules": [
            {
                "error_type": "schema_validation_error",
                "severity": "high",
                "action": "checkout",
                "target_commit": None,
                "max_retry": 2,
                "requires_human": False,
                "retry_profile": {
                    "model": "gpt-4o-mini",
                    "temperature": 0.2,
                    "prompt_override": "strict_output_format",
                },
            },
            {
                "error_type": "hallucination",
                "severity": "medium",
                "action": "retry",
                "target_commit": None,
                "max_retry": 1,
                "requires_human": False,
            },
            {
                "error_type": "timeout",
                "severity": "low",
                "action": "retry",
                "target_commit": None,
                "max_retry": 3,
                "requires_human": False,
            },
            {
                "error_type": "hitl_block",
                "severity": "critical",
                "action": "escalate",
                "target_commit": None,
                "max_retry": 0,
                "requires_human": True,
            },
        ],
        "lifecycle_policy": {
            "branch_ttl_days": 7,
            "artifact_retention_days": 30,
            "archive_on_merge": True,
            "cleanup_job_interval_days": 1,
        },
        "metadata": {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "nodes_processed": [str(n.get("id")) for n in nodes if n.get("id")],
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

        # Accept both new (directive_binding) and legacy (mental_model_bundle) formats
        has_new = "bindings" in bundle
        has_legacy = "bundle_ref" in bundle and "local_charts" in bundle
        if not has_new and not has_legacy:
            raise SystemExit("invalid bundle: expected 'bindings' (directive_binding) or 'bundle_ref'+'local_charts' (legacy)")

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
