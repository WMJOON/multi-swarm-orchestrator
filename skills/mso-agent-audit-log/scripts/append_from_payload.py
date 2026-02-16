#!/usr/bin/env python3
"""Append one audit record from a run payload JSON file."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = (ROOT / "../02.test/v0.0.1/agent_log.db").resolve()
SCHEMA_VERSION = "1.3.0"

CONFIG_PATH = ROOT / "config.yaml"

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def parse_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    if yaml is None:
        return {}
    loaded = yaml.safe_load(raw)
    return loaded if isinstance(loaded, dict) else {}


def resolve_path(cfg: dict[str, Any], fallback: str, *keys: str) -> Path:
    base = cfg
    for key in keys:
        if not isinstance(base, dict):
            base = {}
        base = base.get(key)

    raw = str(base) if base is not None else fallback
    p = Path(raw)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p


def resolve_db_path(cfg: dict[str, Any], cli_path: str | None) -> Path:
    if cli_path:
        return Path(cli_path).expanduser().resolve()

    audit = cfg.get("audit_log")
    if isinstance(audit, dict):
        path = audit.get("db_path")
        if isinstance(path, str) and path:
            return resolve_path(cfg, str(DEFAULT_DB), "audit_log", "db_path")

    pipeline = cfg.get("pipeline")
    if isinstance(pipeline, dict):
        path = pipeline.get("default_db_path")
        if isinstance(path, str) and path:
            return resolve_path(cfg, str(DEFAULT_DB), "pipeline", "default_db_path")

    return resolve_path(cfg, str(DEFAULT_DB), "pipeline", "default_db_path")


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


def build_common(payload: Dict[str, Any]) -> Dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata.setdefault("schema_version", payload.get("schema_version", SCHEMA_VERSION))
    if "cc_coupling_id" not in metadata:
        metadata["cc_coupling_id"] = payload.get("cc_coupling_id", "CC-SET")
    if "required_skill_ids" not in metadata:
        metadata["required_skill_ids"] = payload.get("required_skill_ids", [
            "mso-workflow-topology-design",
            "mso-mental-model-design",
            "mso-execution-design",
            "mso-task-context-management",
            "mso-agent-collaboration",
            "mso-agent-audit-log",
            "mso-observability",
            "mso-skill-governance",
        ])

    return {
        "run_id": safe_text(payload.get("run_id"), f"run-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"),
        "artifact_uri": safe_text(payload.get("artifact_uri") or payload.get("artifact"), "outputs/unknown.json"),
        "status": safe_text(payload.get("status"), "in_progress"),
        "errors": as_list(payload.get("errors")),
        "warnings": as_list(payload.get("warnings")),
        "next_actions": as_list(payload.get("next_actions")),
        "metadata": metadata,
        "task_name": safe_text(payload.get("task_name"), safe_text(payload.get("source"), "pipeline-operation")),
        "mode": safe_text(payload.get("mode"), "pipeline"),
        "action": safe_text(payload.get("action"), "record"),
        "script": safe_text(payload.get("script"), Path(__file__).name),
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
    notes = safe_text(
        common.get("notes")
    )
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
            transition_repeated, transition_reuse, transition_decision, created_at, updated_at
        ) VALUES (
            ?, date('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
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
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a payload into audit DB")
    parser.add_argument("payload")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to orchestrator config")
    parser.add_argument("--db", default=None, help="SQLite DB path")
    parser.add_argument("--schema-version", default=SCHEMA_VERSION, help="Expected schema version")
    args = parser.parse_args()

    payload = load_payload(Path(args.payload).expanduser().resolve())
    common = build_common(payload)

    task_id = safe_text(payload.get("task_id"), gen_task_id(common["run_id"]))

    cfg = parse_config(Path(args.config).expanduser().resolve())
    db = resolve_db_path(cfg, args.db)
    if not db.exists():
        raise SystemExit(f"DB not found: {db}")

    with sqlite3.connect(str(db)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        insert_audit_row(cur, common, task_id)
        insert_decision_rows(cur, task_id, payload.get("decisions", []))
        conn.commit()

    print(json.dumps({
        "task_id": task_id,
        "run_id": common["run_id"],
        "artifact_uri": common["artifact_uri"],
        "status": common["status"],
        "db": str(db),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
