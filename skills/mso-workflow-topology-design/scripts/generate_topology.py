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


def tokenize_dqs(goal: str) -> List[str]:
    parts = re.split(r"[.?!\n]|그리고 |및 |또는 ", goal)
    dq = [p.strip() for p in parts if len(p.strip()) > 2]
    if not dq:
        return [goal.strip()]
    return dq[:6]


def build_nodes(dqs: List[str]) -> List[Dict[str, object]]:
    nodes = []
    for i, dq in enumerate(dqs, start=1):
        dqsig = min(1.0, max(0.05, 1.0 / max(1, len(dqs)) + 0.05 * (i - 1)))
        theta = "moderate"
        if i == 1:
            theta = "wide"
        elif i == len(dqs):
            theta = "narrow"
        nodes.append(
            {
                "id": f"T{i}",
                "label": dq[:60],
                "theta_gt_band": theta,
                "assigned_dqs": [f"DQ{i}"],
                "rsv_target": round(min(1.0, dqsig), 2),
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


def build_spec(goal: str, risk: str, run_id: str) -> Dict[str, object]:
    dqs = tokenize_dqs(goal)
    nodes = build_nodes(dqs)
    topology_type = choose_topology(goal)
    return {
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
    }


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
