#!/usr/bin/env python3
"""Generate workflow topology spec for runtime workspace."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

SKILL_ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = Path(__file__).resolve().parents[3]

if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from skills._shared.runtime_workspace import (  # noqa: E402
    resolve_runtime_paths,
    sanitize_case_slug,
    update_manifest_phase,
)

# ---------------------------------------------------------------------------
# theta_gt_range mapping (band -> numeric range)
# ---------------------------------------------------------------------------
THETA_RANGE_MAP = {
    "narrow": {"min": 0.0, "max": 0.2},
    "moderate": {"min": 0.2, "max": 0.6},
    "wide": {"min": 0.4, "max": 0.9},
}

# ---------------------------------------------------------------------------
# Default loop risk profiles per topology type
# ---------------------------------------------------------------------------
DEFAULT_LOOP_RISKS: Dict[str, List[Dict[str, object]]] = {
    "linear": [
        {
            "loop_type": "redundancy_accumulation",
            "where": "sequential nodes",
            "risk": "low",
            "mitigation": ["output schema enforces distinct sections"],
        }
    ],
    "fan_out": [
        {
            "loop_type": "exploration_spiral",
            "where": "parallel branches",
            "risk": "med",
            "mitigation": ["max_axes cap per branch", "orthogonality check"],
        },
        {
            "loop_type": "redundancy_accumulation",
            "where": "branch outputs",
            "risk": "med",
            "mitigation": ["deduplicate at synthesis node"],
        },
    ],
    "fan_in": [
        {
            "loop_type": "rsv_inflation",
            "where": "convergence node",
            "risk": "med",
            "mitigation": ["RSV cap at synthesis", "DQ re-scope if exceeded"],
        }
    ],
    "dag": [
        {
            "loop_type": "semantic_dependency_cycle",
            "where": "cross-dependency edges",
            "risk": "med",
            "mitigation": ["DAG validation", "merge or insert synthesis node"],
        },
        {
            "loop_type": "rsv_inflation",
            "where": "multi-path convergence",
            "risk": "med",
            "mitigation": ["DQ boundary review", "goal decomposition if needed"],
        },
    ],
    "loop": [
        {
            "loop_type": "infinite_loop",
            "where": "cycle back-edge",
            "risk": "high",
            "mitigation": ["max_iterations cap", "convergence check per iteration"],
        },
        {
            "loop_type": "redundancy_accumulation",
            "where": "repeated iterations",
            "risk": "high",
            "mitigation": ["output length cap", "delta_entropy threshold"],
        },
        {
            "loop_type": "human_deferral_loop",
            "where": "HITL gate",
            "risk": "med",
            "mitigation": ["explicit judgment criteria at gate"],
        },
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate workflow_topology_spec.json")
    parser.add_argument("--goal", help="Goal statement")
    parser.add_argument("--goal-file", help="Read goal from text file")
    parser.add_argument("--output", default="", help="Optional output path override")
    parser.add_argument("--risk", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--run-id", default="", help="Run ID override")
    parser.add_argument("--skill-key", default="msowd", help="Skill key for run-id generation")
    parser.add_argument("--case-slug", default="", help="Case slug for run-id generation")
    parser.add_argument("--observer-id", default="", help="Observer ID override")
    return parser.parse_args()


def read_goal(args: argparse.Namespace) -> str:
    if args.goal:
        return args.goal.strip()
    if args.goal_file:
        return Path(args.goal_file).read_text(encoding="utf-8").strip()
    raise SystemExit("--goal or --goal-file is required")


def choose_topology(goal: str) -> str:
    lowered = goal.lower()
    if any(token in lowered for token in ["반복", "루프", "개선", "개량"]):
        return "loop"
    if "분기" in lowered or "조건" in lowered or "경우" in lowered:
        return "fan_out"
    if "합치" in lowered or "통합" in lowered or "요약" in lowered:
        return "fan_in"
    if any(token in lowered for token in ["동시", "병렬", "비교", "분석", "채점"]):
        return "dag"
    return "linear"


def tokenize_dqs(goal: str) -> List[Dict[str, object]]:
    """Split goal into DQs with normalized weights."""
    parts = re.split(r"[.?!\n]|그리고 |및 |또는 ", goal)
    raw = [p.strip() for p in parts if len(p.strip()) > 2]
    if not raw:
        raw = [goal.strip()]
    raw = raw[:6]
    n = len(raw)
    base_weight = round(1.0 / max(1, n), 2)
    return [
        {"id": f"DQ{i}", "question": q, "weight": base_weight}
        for i, q in enumerate(raw, start=1)
    ]


def _output_type_for_position(index: int, total: int) -> str:
    if index == 0:
        return "memo"
    if index == total - 1:
        return "decision"
    return "table"


def build_nodes(dqs: List[Dict[str, object]]) -> List[Dict[str, object]]:
    nodes = []
    n = len(dqs)
    for i, dq in enumerate(dqs):
        idx = i + 1
        dqsig = min(1.0, max(0.05, 1.0 / max(1, n) + 0.05 * i))

        if i == 0:
            theta = "wide"
        elif i == n - 1:
            theta = "narrow"
        else:
            theta = "moderate"

        nodes.append(
            {
                "id": f"T{idx}",
                "label": str(dq["question"])[:60],
                "theta_gt_band": theta,
                "assigned_dqs": [dq["id"]],
                "rsv_target": round(min(1.0, dqsig), 2),
                "stop_condition": f"{dq['id']} closed OR redundancy detected",
                "explicit_output": {
                    "type": _output_type_for_position(i, n),
                    "required_sections": [],
                    "acceptance_criteria": [],
                },
                "theta_gt_range": THETA_RANGE_MAP[theta],
                "semantic_entropy_expected": round(
                    (THETA_RANGE_MAP[theta]["min"] + THETA_RANGE_MAP[theta]["max"]) / 2, 2
                ),
            }
        )
    return nodes


def build_edges(nodes: List[Dict[str, object]]) -> List[Dict[str, str]]:
    if len(nodes) <= 1:
        return []
    edges = []
    for i in range(len(nodes) - 1):
        edges.append({"from": nodes[i]["id"], "to": nodes[i + 1]["id"], "type": "data"})
    return edges


def _build_execution_policy(
    risk: str, topology_type: str, nodes: List[Dict[str, object]]
) -> Dict[str, object]:
    rules = [
        "CONTINUE: delta_entropy > epsilon AND new DQ closure detected",
        "REFRAME: redundancy flag AND delta_rsv == 0 for 2 consecutive iterations",
        "STOP: all assigned DQs closed OR rsv_accumulated >= rsv_total",
    ]
    if risk == "high":
        rules.append("STOP: strategy_gate triggered — require human approval before proceed")

    human_gates: List[str] = []
    if risk == "high" and nodes:
        human_gates = [str(nodes[-1]["id"])]

    return {
        "continue_reframe_stop_rules": rules,
        "estimator_integration": {
            "script": "scripts/estimator.py",
            "invoke_per": "node_iteration",
            "normalized_output_schema": "canonical_output with decision_questions, claims, assumptions",
        },
        "human_gate_nodes": human_gates,
    }


def _build_handoff_strategy(
    topology_type: str, nodes: List[Dict[str, object]]
) -> Dict[str, object] | None:
    if topology_type not in ("fan_out", "fan_in", "dag"):
        return None
    handoff_points = []
    if topology_type == "fan_out" and len(nodes) > 1:
        handoff_points = [str(nodes[0]["id"])]
    elif topology_type == "fan_in" and len(nodes) > 1:
        handoff_points = [str(nodes[-1]["id"])]
    elif topology_type == "dag":
        handoff_points = [str(n["id"]) for n in nodes if n.get("theta_gt_band") == "narrow"]

    return {
        "handoff_points": handoff_points,
        "minimize_context_loss_rules": [
            "pass structured DQ status, not prose summaries",
            "include constraint_list and open_dqs at each handoff",
        ],
    }


def build_spec(goal: str, risk: str, run_id: str) -> Dict[str, object]:
    dqs = tokenize_dqs(goal)
    nodes = build_nodes(dqs)
    topology_type = choose_topology(goal)

    spec: Dict[str, object] = {
        "run_id": run_id,
        "nodes": nodes,
        "edges": build_edges(nodes),
        "topology_type": topology_type,
        "rsv_total": round(sum(float(n["rsv_target"]) for n in nodes), 2),
        "strategy_gate": risk == "high",
        "metadata": {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "source": "workflow-topology-design",
            "goal_preview": goal[:120],
        },
        "decision_questions": [
            {"id": dq["id"], "question": dq["question"], "weight": dq["weight"]}
            for dq in dqs
        ],
        "loop_risk_assessment": DEFAULT_LOOP_RISKS.get(topology_type, []),
        "execution_policy": _build_execution_policy(risk, topology_type, nodes),
    }

    handoff = _build_handoff_strategy(topology_type, nodes)
    if handoff:
        spec["handoff_strategy"] = handoff

    return spec


def ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    goal = read_goal(args)
    if not goal:
        print("Error: goal is empty", flush=True)
        return 1

    case_slug = args.case_slug.strip() or sanitize_case_slug(goal[:40])
    paths = resolve_runtime_paths(
        run_id=args.run_id.strip() or None,
        skill_key=args.skill_key,
        case_slug=case_slug,
        observer_id=args.observer_id.strip() or None,
        create=True,
    )

    out = Path(args.output).expanduser().resolve() if args.output else Path(paths["topology_path"])

    try:
        update_manifest_phase(paths, "10", "active")
        spec = build_spec(goal, args.risk, paths["run_id"])
        ensure_dir(out)
        out.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        update_manifest_phase(paths, "10", "completed")
    except Exception:
        update_manifest_phase(paths, "10", "failed")
        raise

    print(f"WROTE {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
