#!/usr/bin/env python3
"""Append one audit record from a run payload JSON file (standalone — no _shared dependency)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

SCHEMA_VERSION = "1.5.0"


def resolve_audit_db_path(cli_db: str | None = None) -> Path:
    """Resolve audit DB path with priority: CLI arg > env > CWD walk > fallback."""
    if cli_db:
        return Path(cli_db).expanduser().resolve()

    ws = os.environ.get("MSO_WORKSPACE")
    if ws:
        return Path(ws).expanduser().resolve() / ".mso-context" / "audit_global.db"

    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".mso-context"
        if candidate.is_dir():
            return candidate / "audit_global.db"

    return Path.home() / ".mso-context" / "audit_global.db"


def gen_task_id(run_id: str, prefix: str = "TASK") -> str:
    base = run_id or datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    digest = hashlib.md5(base.encode("utf-8")).hexdigest()[:4].upper()
    return f"{prefix}-{datetime.utcnow().strftime('%Y%m%d')}-{digest}"


def load_payload(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    return data


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [safe_text(v) for v in value if safe_text(v)]
    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []
    return [str(value)]


def to_bool_int(value: Any) -> int:
    return 1 if bool(value) else 0


def build_common(payload: Dict[str, Any], run_id: str, default_artifact: str) -> Dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata.setdefault("schema_version", payload.get("schema_version", SCHEMA_VERSION))
    if "cc_coupling_id" not in metadata:
        metadata["cc_coupling_id"] = payload.get("cc_coupling_id", "CC-SET")
    if "required_skill_ids" not in metadata:
        metadata["required_skill_ids"] = payload.get(
            "required_skill_ids",
            [
                "mso-workflow-topology-design",
                "mso-mental-model-design",
                "mso-execution-design",
                "mso-task-context-management",
                "mso-agent-collaboration",
                "mso-agent-audit-log",
                "mso-observability",
                "mso-skill-governance",
            ],
        )

    # v0.0.4 new fields
    files_affected = payload.get("files_affected")
    if isinstance(files_affected, list):
        files_affected = json.dumps(files_affected, ensure_ascii=False)

    return {
        "run_id": safe_text(payload.get("run_id"), run_id),
        "artifact_uri": safe_text(payload.get("artifact_uri") or payload.get("artifact"), default_artifact),
        "status": safe_text(payload.get("status"), "in_progress"),
        "errors": as_list(payload.get("errors")),
        "warnings": as_list(payload.get("warnings")),
        "next_actions": as_list(payload.get("next_actions")),
        "metadata": metadata,
        "task_name": safe_text(payload.get("task_name"), safe_text(payload.get("source"), "pipeline-operation")),
        "mode": safe_text(payload.get("mode"), "pipeline"),
        "action": safe_text(payload.get("action"), "record"),
        "script": safe_text(payload.get("script"), Path(__file__).name),
        # v0.0.4 fields
        "work_type": payload.get("work_type"),
        "triggered_by": payload.get("triggered_by"),
        "duration_sec": payload.get("duration_sec"),
        "files_affected": files_affected,
        "sprint": payload.get("sprint"),
        "pattern_tag": payload.get("pattern_tag"),
        "session_id": payload.get("session_id"),
        "intent": payload.get("intent"),
    }


def insert_decision_rows(cur: sqlite3.Cursor, task_id: str, decisions: List[Dict[str, Any]]) -> None:
    if not decisions:
        return

    for idx, decision in enumerate(decisions, start=1):
        decision_id = safe_text(decision.get("id"), f"DEC-{task_id}-{idx:02d}")
        title = safe_text(decision.get("title"), "Pipeline decision")
        context = safe_text(decision.get("context"), "")
        decision_content = safe_text(decision.get("decision_content") or decision.get("content"), "")
        requested_by = safe_text(decision.get("requested_by"), "orchestrator")
        approved_by = safe_text(decision.get("approved_by"), None)

        cur.execute(
            """
            INSERT OR REPLACE INTO decisions (
                id, date, title, context, decision_content, requested_by, approved_by, related_audit_id
            ) VALUES (?, date('now'), ?, ?, ?, ?, ?, ?)
            """,
            (decision_id, title, context, decision_content, requested_by, approved_by or None, task_id),
        )


def insert_audit_row(cur: sqlite3.Cursor, common: Dict[str, Any], task_id: str) -> None:
    metadata = common.get("metadata", {}) if isinstance(common.get("metadata"), dict) else {}
    notes = safe_text(common.get("notes"))
    if not notes:
        parts = []
        if common["errors"]:
            parts.append("errors=" + "; ".join(common["errors"]))
        if common["warnings"]:
            parts.append("warnings=" + "; ".join(common["warnings"]))
        if common["next_actions"]:
            parts.append("next_actions=" + "; ".join(common["next_actions"]))
        notes = " | ".join(parts)

    cur.execute(
        """
        INSERT OR REPLACE INTO audit_logs (
            id, date, task_name, mode, action, input_path, output_path, script_path,
            status, notes, context_for_next, continuation_hint,
            transition_repeated, transition_reuse, transition_decision,
            work_type, triggered_by, duration_sec, files_affected,
            sprint, pattern_tag, session_id, intent,
            created_at, updated_at
        ) VALUES (
            ?, date('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        """,
        (
            task_id,
            common["task_name"],
            common["mode"],
            common["action"],
            common["artifact_uri"],
            common["artifact_uri"],
            common["script"],
            common["status"],
            notes or None,
            safe_text(metadata.get("context_for_next", "")),
            safe_text(metadata.get("continuation_hint", "")) or None,
            to_bool_int(metadata.get("transition_repeated", 0)),
            to_bool_int(metadata.get("transition_reuse", 0)),
            to_bool_int(metadata.get("transition_decision", 0)),
            common.get("work_type"),
            common.get("triggered_by"),
            common.get("duration_sec"),
            common.get("files_affected"),
            common.get("sprint"),
            common.get("pattern_tag"),
            common.get("session_id"),
            common.get("intent"),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a payload into audit DB")
    parser.add_argument("payload")
    parser.add_argument("--db", default=None, help="SQLite DB path override")
    parser.add_argument("--schema-version", default=SCHEMA_VERSION, help="Expected schema version")
    args = parser.parse_args()

    payload = load_payload(Path(args.payload).expanduser().resolve())
    run_id = safe_text(payload.get("run_id"), "")

    db = resolve_audit_db_path(args.db)
    common = build_common(payload, run_id, "")
    task_id = safe_text(payload.get("task_id"), gen_task_id(common["run_id"]))

    if not db.exists():
        raise SystemExit(f"DB not found: {db}")

    with sqlite3.connect(str(db)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL;")
        cur = conn.cursor()
        insert_audit_row(cur, common, task_id)
        insert_decision_rows(cur, task_id, payload.get("decisions", []))
        conn.commit()

    print(
        json.dumps(
            {
                "task_id": task_id,
                "run_id": common["run_id"],
                "artifact_uri": common["artifact_uri"],
                "status": common["status"],
                "db": str(db),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
