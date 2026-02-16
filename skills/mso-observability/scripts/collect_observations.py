#!/usr/bin/env python3
"""Collect observability signals from audit DB and emit callback events."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config.yaml"
DEFAULT_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "observability_callback.schema.json"

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}

    try:
        return json.loads(raw)
    except Exception:
        pass

    if yaml is None:
        return {}
    cfg = yaml.safe_load(raw) or {}
    return cfg if isinstance(cfg, dict) else {}


def resolve_user_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    else:
        p = p.resolve()
    return p


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


def read_db_rows(db_path: Path, limit: int) -> List[Dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT id, date, task_name, mode, action, status, notes, continuation_hint, transition_repeated, created_at, updated_at "
            "FROM audit_logs ORDER BY COALESCE(created_at, date||' 00:00:00') DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def parse_bool(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).lower()
    return any(token in s for token in ("1", "true", "yes", "manual", "승인", "검토"))


def emit_event(
    event_type: str,
    checkpoint_id: str,
    severity: str,
    message: str,
    target_skills: List[str],
    correlation: Dict[str, Any],
    retry_policy: Dict[str, int],
) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "checkpoint_id": checkpoint_id,
        "payload": {
            "target_skills": target_skills,
            "severity": severity,
            "message": message,
        },
        "retry_policy": retry_policy,
        "correlation": correlation,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def build_events(rows: List[Dict[str, Any]], run_id: str, artifact: str, mode: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    now_compact = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    if not rows:
        events.append(
            emit_event(
                event_type="periodic_report",
                checkpoint_id=f"HC-{now_stamp}",
                severity="info",
                message="No rows in audit db; skipping signal detection.",
                target_skills=["mso-agent-audit-log", "mso-skill-governance"],
                correlation={"run_id": run_id, "artifact_uri": artifact},
                retry_policy={"max_retries": 0, "backoff_seconds": 0, "on_retry": "drop"},
            )
        )
        return events

    fails = [r for r in rows if str(r.get("status") or "").lower() == "fail"]
    fail_by_task = Counter(r["task_name"] for r in fails if r.get("task_name"))
    for task, cnt in fail_by_task.items():
        if cnt >= 3:
            events.append(
                emit_event(
                    event_type="anomaly_detected",
                    checkpoint_id=f"AS-{now_stamp}-{task}",
                    severity="warning",
                    message=f"failure_cluster detected for {task}: count={cnt}",
                    target_skills=["mso-execution-design", "mso-task-context-management"],
                    correlation={"run_id": run_id, "artifact_uri": artifact},
                    retry_policy={"max_retries": 2, "backoff_seconds": 10, "on_retry": "queue"},
                )
            )

    retry_rows = [r for r in rows if int(r.get("transition_repeated") or 0) == 1]
    ratio = (len(retry_rows) / len(rows)) if rows else 0.0
    if ratio >= 0.2:
        events.append(
            emit_event(
                event_type="anomaly_detected",
                checkpoint_id=f"AS-{now_stamp}-retry",
                severity="warning" if ratio < 0.5 else "critical",
                message=f"retry_spike detected: retries={len(retry_rows)}/{len(rows)} ({math.floor(ratio*100)}%)",
                target_skills=["mso-execution-design", "mso-agent-collaboration"],
                correlation={"run_id": run_id, "artifact_uri": artifact},
                retry_policy={"max_retries": 3, "backoff_seconds": 15, "on_retry": "queue"},
            )
        )

    if mode in {"scheduled", "on_demand", "event"}:
        tasks = Counter(r["task_name"] for r in rows if r.get("task_name"))
        if rows:
            top_task, top_count = tasks.most_common(1)[0]
            if top_count >= max(2, int(len(rows) * 0.6)):
                events.append(
                    emit_event(
                        event_type="anomaly_detected",
                        checkpoint_id=f"AS-{now_stamp}-bottleneck",
                        severity="warning",
                        message=f"bottleneck candidate: {top_task} consumed {top_count}/{len(rows)} events",
                        target_skills=["mso-workflow-topology-design", "mso-execution-design"],
                        correlation={"run_id": run_id, "artifact_uri": artifact},
                        retry_policy={"max_retries": 1, "backoff_seconds": 10, "on_retry": "queue"},
                    )
                )

    deferred = [r for r in rows if parse_bool(r.get("notes", "")) or parse_bool(r.get("continuation_hint", ""))]
    if len(deferred) >= max(1, int(len(rows) * 0.4)):
        events.append(
            emit_event(
                event_type="hitl_request",
                checkpoint_id=f"HC-{now_stamp}-manual",
                severity="critical",
                message=f"human_deferral_loop suspected; {len(deferred)}/{len(rows)} rows indicate manual intervention",
                target_skills=["mso-skill-governance", "mso-agent-collaboration"],
                correlation={"run_id": run_id, "artifact_uri": artifact},
                retry_policy={"max_retries": 5, "backoff_seconds": 20, "on_retry": "queue"},
            )
        )

    if not events:
        events.append(
            emit_event(
                event_type="periodic_report",
                checkpoint_id=f"HC-{now_stamp}-summary",
                severity="info",
                message=f"observability completed: rows={len(rows)}, fails={len(fails)}, retries={len(retry_rows)}",
                target_skills=["mso-agent-audit-log", "mso-skill-governance"],
                correlation={"run_id": run_id, "artifact_uri": artifact},
                retry_policy={"max_retries": 0, "backoff_seconds": 0, "on_retry": "drop"},
            )
        )

    return events


def main() -> int:
    p = argparse.ArgumentParser(description="Collect observations and write callback events")
    p.add_argument("--config", default=str(CONFIG_PATH), help="Path to orchestrator config")
    p.add_argument("--db", default="", help="SQLite DB path (fallback to config)")
    p.add_argument("--run-id", default=f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    p.add_argument("--artifact", default="")
    p.add_argument("--out", default="", help="Output directory (fallback to config)")
    p.add_argument("--mode", default="scheduled", choices=["scheduled", "event", "on_demand", "batch"])
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    cfg = load_config(Path(args.config).expanduser().resolve())
    db_path = resolve_user_path(args.db) if args.db else resolve_path(
        cfg,
        str(ROOT / "../../02.test/v0.0.1/agent_log.db"),
        "pipeline",
        "default_db_path",
    )
    if args.artifact:
        artifact = resolve_user_path(args.artifact)
    else:
        workflow_output_dir = resolve_path(
            cfg,
            str(ROOT / "../../02.test/v0.0.1/outputs"),
            "pipeline",
            "default_workflow_output_dir",
        )
        artifact = workflow_output_dir / "execution_plan.json"
    out_dir = resolve_user_path(args.out) if args.out else resolve_path(
        cfg,
        str(ROOT / "../../02.test/v0.0.1/observations"),
        "pipeline",
        "default_observation_dir",
    )

    rows = read_db_rows(db_path, args.limit)
    events = build_events(rows, args.run_id, str(artifact), args.mode)

    if args.dry_run:
        print(json.dumps({"run_id": args.run_id, "count": len(events)}, ensure_ascii=False, indent=2))
        return 0

    if not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    payload_path = out_dir / f"callbacks-{ts}.json"
    payload_path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")

    for idx, event in enumerate(events, start=1):
        event_path = out_dir / f"callback-{ts}-{idx:02d}.json"
        event_path.write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"WROTE {payload_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
