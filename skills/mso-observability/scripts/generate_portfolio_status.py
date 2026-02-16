#!/usr/bin/env python3
"""Generate a Workflow Portfolio Status markdown from MSO pipeline artifacts.

Reads tickets, collaboration outputs, audit DB, and topology spec to produce
a human-readable status document following the good-practice.md pattern.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config.yaml"


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def resolve_path(cfg: Dict[str, Any], fallback: str, *keys: str) -> Path:
    base: Any = cfg
    for key in keys:
        if not isinstance(base, dict):
            base = {}
        base = base.get(key)
    raw = str(base) if base is not None else fallback
    p = Path(raw)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p


# --- Ticket parsing ---

def parse_frontmatter(path: Path) -> Dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip("'\"")
    return fm


def collect_tickets(task_dir: Path) -> List[Dict[str, str]]:
    tickets_dir = task_dir / "tickets"
    if not tickets_dir.exists():
        return []
    results = []
    for f in sorted(tickets_dir.glob("TKT-*.md")):
        fm = parse_frontmatter(f)
        if fm.get("id"):
            fm["_path"] = str(f)
            results.append(fm)
    return results


# --- Collaboration outputs ---

def collect_assignments(task_dir: Path) -> List[Dict[str, Any]]:
    tickets_dir = task_dir / "tickets"
    if not tickets_dir.exists():
        return []
    results = []
    for f in sorted(tickets_dir.glob("*.agent-collaboration.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_file"] = f.name
                results.append(data)
        except Exception:
            continue
    return results


# --- Audit DB ---

def collect_audit_summary(db_path: Path) -> Dict[str, Any]:
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) as cnt FROM audit_logs").fetchone()["cnt"]
        success = conn.execute("SELECT COUNT(*) as cnt FROM audit_logs WHERE status='success'").fetchone()["cnt"]
        fail = conn.execute("SELECT COUNT(*) as cnt FROM audit_logs WHERE status='fail'").fetchone()["cnt"]
        in_prog = conn.execute("SELECT COUNT(*) as cnt FROM audit_logs WHERE status='in_progress'").fetchone()["cnt"]
        last_row = conn.execute("SELECT created_at FROM audit_logs ORDER BY created_at DESC LIMIT 1").fetchone()
        last_event = last_row["created_at"] if last_row else "N/A"
        conn.close()
        return {
            "total": total, "success": success, "fail": fail,
            "in_progress": in_prog, "last_event_at": last_event,
        }
    except Exception:
        return {}


# --- Topology → Mermaid ---

def topology_to_mermaid(spec: Dict[str, Any]) -> str:
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])
    topo_type = spec.get("topology_type", "dag")

    lines = ["```mermaid", "flowchart LR"]
    for node in nodes:
        nid = node.get("id", "?")
        label = node.get("label", nid)
        band = node.get("theta_gt_band", "")
        desc = f'{nid}["{label}<br/>θ: {band}"]'
        lines.append(f"  {desc}")

    for edge in edges:
        f, t = edge.get("from", "?"), edge.get("to", "?")
        etype = edge.get("type", "")
        if etype == "hitl":
            lines.append(f"  {f} -.->|HITL| {t}")
        else:
            lines.append(f"  {f} --> {t}")

    lines.append("```")
    return "\n".join(lines)


# --- Markdown generation ---

def generate_markdown(
    tickets: List[Dict[str, str]],
    assignments: List[Dict[str, Any]],
    audit: Dict[str, Any],
    topology_spec: Optional[Dict[str, Any]],
    generated_at: str,
) -> str:
    lines: List[str] = []
    lines.append("# Workflow Portfolio Status")
    lines.append(f"\nGenerated at: {generated_at}\n")

    # --- Summary ---
    status_counts: Dict[str, int] = {}
    for t in tickets:
        s = t.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    lines.append("## Summary\n")
    lines.append(f"- total: {len(tickets)}")
    for s in ["todo", "in_progress", "blocked", "done", "cancelled"]:
        if status_counts.get(s, 0) > 0:
            lines.append(f"- {s}: {status_counts[s]}")

    # --- Ticket Status ---
    lines.append("\n## Ticket Status\n")
    lines.append("| id | status | priority | owner | due_by | tags |")
    lines.append("| -- | ------ | -------- | ----- | ------ | ---- |")
    for t in tickets:
        tid = t.get("id", "?")
        status = t.get("status", "?")
        priority = t.get("priority", "medium")
        owner = t.get("owner", "")
        due = t.get("due_by", "")
        tags = t.get("tags", "")
        lines.append(f"| {tid} | {status} | {priority} | {owner} | {due} | {tags} |")

    # --- Audit Logs ---
    if audit:
        lines.append("\n## Audit Logs (Collected)\n")
        lines.append(f"- collected_at: {generated_at}\n")
        lines.append("| metric | value |")
        lines.append("| ------ | ----: |")
        for k in ["total", "success", "fail", "in_progress", "last_event_at"]:
            lines.append(f"| {k} | {audit.get(k, 'N/A')} |")

    # --- Assignments ---
    if assignments:
        lines.append("\n## Assignments\n")
        lines.append("| ticket | owner | dispatch_mode | status | requires_manual |")
        lines.append("| ------ | ----- | ------------- | ------ | --------------- |")
        for a in assignments:
            ticket_id = a.get("task_id", a.get("_file", "?"))
            owner = a.get("owner", "")
            mode = a.get("dispatch_mode", "")
            status = a.get("status", "")
            manual = a.get("requires_manual_confirmation", False)
            lines.append(f"| {ticket_id} | {owner} | {mode} | {status} | {manual} |")

    # --- Workflow Map ---
    if topology_spec and topology_spec.get("nodes"):
        lines.append("\n## Workflow Map\n")
        lines.append(topology_to_mermaid(topology_spec))

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Generate Portfolio Status markdown")
    p.add_argument("--config", default=str(CONFIG_PATH))
    p.add_argument("--output", default="", help="Output markdown path")
    p.add_argument("--json", action="store_true", help="Also emit JSON summary to stdout")
    args = p.parse_args()

    cfg = load_config(Path(args.config).expanduser().resolve())

    task_dir = resolve_path(cfg, str(ROOT / "../02.test/v0.0.1/task-context"), "pipeline", "default_task_dir")
    db_path = resolve_path(cfg, str(ROOT / "../02.test/v0.0.1/agent_log.db"), "pipeline", "default_db_path")
    output_dir = resolve_path(cfg, str(ROOT / "../02.test/v0.0.1/outputs"), "pipeline", "default_workflow_output_dir")
    topo_path = output_dir / "workflow_topology_spec.json"

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    tickets = collect_tickets(task_dir)
    assignments = collect_assignments(task_dir)
    audit = collect_audit_summary(db_path)

    topology_spec = None
    if topo_path.exists():
        try:
            topology_spec = json.loads(topo_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    md = generate_markdown(tickets, assignments, audit, topology_spec, generated_at)

    if args.output:
        out = Path(args.output).expanduser().resolve()
    else:
        obs_dir = resolve_path(cfg, str(ROOT / "../02.test/v0.0.1/observations"), "pipeline", "default_observation_dir")
        obs_dir.mkdir(parents=True, exist_ok=True)
        out = obs_dir / "portfolio_status.md"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"WROTE {out}")

    if args.json:
        summary = {
            "generated_at": generated_at,
            "total_tickets": len(tickets),
            "status_counts": {},
            "assignments": len(assignments),
            "audit_rows": audit.get("total", 0),
            "has_topology": topology_spec is not None,
        }
        for t in tickets:
            s = t.get("status", "unknown")
            summary["status_counts"][s] = summary["status_counts"].get(s, 0) + 1
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
