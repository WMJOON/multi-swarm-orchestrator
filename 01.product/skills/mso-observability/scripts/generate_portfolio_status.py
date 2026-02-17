#!/usr/bin/env python3
"""Generate a workflow portfolio status markdown from runtime artifacts."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config.yaml"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mso_runtime.runtime_workspace import (  # noqa: E402
    resolve_runtime_paths,
    sanitize_case_slug,
    update_manifest_phase,
)


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
            "total": total,
            "success": success,
            "fail": fail,
            "in_progress": in_prog,
            "last_event_at": last_event,
        }
    except Exception:
        return {}


def topology_to_mermaid(spec: Dict[str, Any]) -> str:
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])

    lines = ["```mermaid", "flowchart LR"]
    for node in nodes:
        nid = node.get("id", "?")
        label = node.get("label", nid)
        band = node.get("theta_gt_band", "")
        lines.append(f"  {nid}[\"{label}<br/>theta: {band}\"]")

    for edge in edges:
        src, dst = edge.get("from", "?"), edge.get("to", "?")
        etype = edge.get("type", "")
        if etype == "hitl":
            lines.append(f"  {src} -.->|HITL| {dst}")
        else:
            lines.append(f"  {src} --> {dst}")

    lines.append("```")
    return "\n".join(lines)


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

    status_counts: Dict[str, int] = {}
    for t in tickets:
        s = t.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    lines.append("## Summary\n")
    lines.append(f"- total: {len(tickets)}")
    for s in ["todo", "in_progress", "blocked", "done", "cancelled"]:
        if status_counts.get(s, 0) > 0:
            lines.append(f"- {s}: {status_counts[s]}")

    lines.append("\n## Ticket Status\n")
    lines.append("| id | status | priority | owner | due_by | tags |")
    lines.append("| -- | ------ | -------- | ----- | ------ | ---- |")
    for t in tickets:
        lines.append(
            f"| {t.get('id', '?')} | {t.get('status', '?')} | {t.get('priority', 'medium')} | {t.get('owner', '')} | {t.get('due_by', '')} | {t.get('tags', '')} |"
        )

    if audit:
        lines.append("\n## Audit Logs (Collected)\n")
        lines.append(f"- collected_at: {generated_at}\n")
        lines.append("| metric | value |")
        lines.append("| ------ | ----: |")
        for k in ["total", "success", "fail", "in_progress", "last_event_at"]:
            lines.append(f"| {k} | {audit.get(k, 'N/A')} |")

    if assignments:
        lines.append("\n## Assignments\n")
        lines.append("| ticket | owner | dispatch_mode | status | requires_manual |")
        lines.append("| ------ | ----- | ------------- | ------ | --------------- |")
        for a in assignments:
            ticket_id = a.get("task_id", a.get("_file", "?"))
            lines.append(
                f"| {ticket_id} | {a.get('owner', '')} | {a.get('dispatch_mode', '')} | {a.get('status', '')} | {a.get('requires_manual_confirmation', False)} |"
            )

    if topology_spec and topology_spec.get("nodes"):
        lines.append("\n## Workflow Map\n")
        lines.append(topology_to_mermaid(topology_spec))

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Generate Portfolio Status markdown")
    p.add_argument("--config", default=str(CONFIG_PATH))
    p.add_argument("--output", default="", help="Output markdown path override")
    p.add_argument("--json", action="store_true", help="Also emit JSON summary to stdout")
    p.add_argument("--run-id", default="", help="Run ID override")
    p.add_argument("--skill-key", default="msoobs", help="Skill key for run-id generation")
    p.add_argument("--case-slug", default="", help="Case slug for run-id generation")
    p.add_argument("--observer-id", default="", help="Observer ID override")
    args = p.parse_args()

    paths = resolve_runtime_paths(
        config_path=args.config,
        run_id=args.run_id.strip() or None,
        skill_key=args.skill_key,
        case_slug=sanitize_case_slug(args.case_slug or "portfolio-status"),
        observer_id=args.observer_id.strip() or None,
        create=True,
    )

    task_dir = Path(paths["task_context_dir"])
    db_path = Path(paths["audit_db_path"])
    topo_path = Path(paths["topology_path"])
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        update_manifest_phase(paths, "60", "active")
        tickets = collect_tickets(task_dir)
        assignments = collect_assignments(task_dir)
        audit = collect_audit_summary(db_path)

        topology_spec = None
        if topo_path.exists():
            try:
                topology_spec = json.loads(topo_path.read_text(encoding="utf-8"))
            except Exception:
                topology_spec = None

        md = generate_markdown(tickets, assignments, audit, topology_spec, generated_at)

        out = Path(args.output).expanduser().resolve() if args.output else (Path(paths["observability_dir"]) / "portfolio_status.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        update_manifest_phase(paths, "60", "completed")
        print(f"WROTE {out}")

        if args.json:
            summary = {
                "generated_at": generated_at,
                "run_id": paths["run_id"],
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
    except Exception:
        update_manifest_phase(paths, "60", "failed")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
