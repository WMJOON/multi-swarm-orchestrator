from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MESSAGE_TYPES = [
    "TASK_REQUEST",
    "TASK_ACCEPT",
    "TASK_UPDATE",
    "TASK_RESULT",
    "TASK_ERROR",
    "PING",
    "PONG",
]

MESSAGE_STATUSES = ["queued", "leased", "done", "retry", "dead"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _ensure_db_parent(db_path: str) -> None:
    Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def init_bus(db_path: str) -> None:
    _ensure_db_parent(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS messages (
              id TEXT PRIMARY KEY,
              trace_id TEXT NOT NULL,
              thread_id TEXT NOT NULL,
              from_agent TEXT NOT NULL,
              to_agent TEXT NOT NULL,
              type TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',
              attempt INTEGER NOT NULL DEFAULT 0,
              leased_by TEXT,
              lease_until TEXT,
              error_text TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_queue
              ON messages (to_agent, status, created_at);

            CREATE INDEX IF NOT EXISTS idx_messages_trace
              ON messages (trace_id, thread_id, created_at);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_message(row: sqlite3.Row) -> Dict[str, Any]:
    payload_obj: Any = None
    try:
        payload_obj = json.loads(row[6])
    except Exception:
        payload_obj = row[6]

    return {
        "id": row[0],
        "trace_id": row[1],
        "thread_id": row[2],
        "from_agent": row[3],
        "to_agent": row[4],
        "type": row[5],
        "payload": payload_obj,
        "status": row[7],
        "attempt": row[8],
        "leased_by": row[9],
        "lease_until": row[10],
        "error_text": row[11],
        "created_at": row[12],
        "updated_at": row[13],
    }


def send_message(
    db_path: str,
    *,
    from_agent: str,
    to_agent: str,
    msg_type: str,
    payload: Any,
    trace_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> str:
    if msg_type not in MESSAGE_TYPES:
        raise ValueError(f"Unsupported message type: {msg_type}")

    if isinstance(payload, str):
        payload_obj = json.loads(payload)
    else:
        payload_obj = payload

    msg_id = f"msg_{uuid.uuid4().hex}"
    now = utc_now_iso()

    trace = trace_id or f"tr_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    thread = thread_id or "th_default"

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO messages (
              id, trace_id, thread_id, from_agent, to_agent, type, payload_json,
              status, attempt, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?)
            """,
            (
                msg_id,
                trace,
                thread,
                from_agent,
                to_agent,
                msg_type,
                json.dumps(payload_obj, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return msg_id


def claim_next_message(
    db_path: str,
    *,
    to_agent: str,
    worker_id: str,
    lease_seconds: int,
) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT *
            FROM messages
            WHERE to_agent = ?
              AND status IN ('queued', 'retry')
              AND (lease_until IS NULL OR lease_until < ?)
            ORDER BY created_at
            LIMIT 1
            """,
            (to_agent, utc_now_iso()),
        ).fetchone()

        if row is None:
            conn.execute("COMMIT")
            return None

        lease_until = datetime.now(timezone.utc).timestamp() + max(1, lease_seconds)
        lease_until_iso = datetime.fromtimestamp(lease_until, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

        updated = conn.execute(
            """
            UPDATE messages
            SET status = 'leased',
                leased_by = ?,
                lease_until = ?,
                attempt = attempt + 1,
                updated_at = ?
            WHERE id = ?
              AND status IN ('queued', 'retry')
              AND (lease_until IS NULL OR lease_until < ?)
            """,
            (worker_id, lease_until_iso, utc_now_iso(), row[0], utc_now_iso()),
        )

        if updated.rowcount != 1:
            conn.execute("COMMIT")
            return None

        claimed = conn.execute("SELECT * FROM messages WHERE id = ?", (row[0],)).fetchone()
        conn.execute("COMMIT")
        if claimed is None:
            return None
        return _row_to_message(claimed)
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def mark_done(db_path: str, message_id: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE messages
            SET status = 'done', lease_until = NULL, updated_at = ?
            WHERE id = ?
            """,
            (utc_now_iso(), message_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_retry(db_path: str, message_id: str, error_text: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE messages
            SET status = 'retry', error_text = ?, lease_until = NULL, updated_at = ?
            WHERE id = ?
            """,
            (error_text, utc_now_iso(), message_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_dead(db_path: str, message_id: str, error_text: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE messages
            SET status = 'dead', error_text = ?, lease_until = NULL, updated_at = ?
            WHERE id = ?
            """,
            (error_text, utc_now_iso(), message_id),
        )
        conn.commit()
    finally:
        conn.close()


def status_counts(db_path: str) -> List[Tuple[str, int]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) as cnt
            FROM messages
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
        return [(str(r[0]), int(r[1])) for r in rows]
    finally:
        conn.close()


def recent_messages(db_path: str, limit: int = 20) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM messages
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_message(r) for r in rows]
    finally:
        conn.close()


def messages_for_trace(db_path: str, trace_id: str) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM messages
            WHERE trace_id = ?
            ORDER BY created_at
            """,
            (trace_id,),
        ).fetchall()
        return [_row_to_message(r) for r in rows]
    finally:
        conn.close()
