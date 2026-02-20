#!/usr/bin/env python3
"""Initialize / migrate audit log DB (standalone — no _shared dependency)."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

INIT_SQL = Path(__file__).resolve().parent.parent / "schema" / "init.sql"
MIGRATE_SQL = Path(__file__).resolve().parent.parent / "schema" / "migrate_v1_to_v1_1.sql"
MIGRATE_V1_3_SQL = Path(__file__).resolve().parent.parent / "schema" / "migrate_v1_3_to_v1_4.sql"
MIGRATE_V1_4_SQL = Path(__file__).resolve().parent.parent / "schema" / "migrate_v1_4_to_v1_5.sql"


def resolve_audit_db_path(cli_db: str | None = None) -> Path:
    """Resolve audit DB path with priority: CLI arg > env > CWD walk > fallback."""
    # 1. Explicit CLI override
    if cli_db:
        return Path(cli_db).expanduser().resolve()

    # 2. MSO_WORKSPACE env var
    ws = os.environ.get("MSO_WORKSPACE")
    if ws:
        return Path(ws).expanduser().resolve() / ".mso-context" / "audit_global.db"

    # 3. CWD upward walk looking for .mso-context/
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".mso-context"
        if candidate.is_dir():
            return candidate / "audit_global.db"

    # 4. Fallback
    return Path.home() / ".mso-context" / "audit_global.db"


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in cols)


def ensure_db(db_path: Path, schema_version: str, run_migrate: bool) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        with conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode=WAL;")
            if not INIT_SQL.exists():
                raise SystemExit(f"INIT SQL missing: {INIT_SQL}")
            conn.executescript(INIT_SQL.read_text(encoding="utf-8"))
            conn.execute("CREATE TABLE IF NOT EXISTS _skill_meta (k TEXT PRIMARY KEY, v TEXT)")
            conn.execute(
                "INSERT OR REPLACE INTO _skill_meta(k, v) VALUES ('schema_version', ?)",
                (schema_version,),
            )
            if run_migrate and MIGRATE_SQL.exists():
                legacy_table = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs_old'"
                ).fetchone()
                if legacy_table:
                    conn.executescript(MIGRATE_SQL.read_text(encoding="utf-8"))
                    conn.execute(
                        "INSERT OR REPLACE INTO _skill_meta(k, v) VALUES ('schema_version', ?)",
                        (schema_version,),
                    )
            # v1.3 -> v1.4 migration: add node_snapshots if missing
            snapshots_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='node_snapshots'"
            ).fetchone()
            if not snapshots_table and MIGRATE_V1_3_SQL.exists():
                conn.executescript(MIGRATE_V1_3_SQL.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT OR REPLACE INTO _skill_meta(k, v) VALUES ('schema_version', ?)",
                    (schema_version,),
                )
            # v1.4 -> v1.5 migration: add work_type etc. if missing
            if not _has_column(conn, "audit_logs", "work_type") and MIGRATE_V1_4_SQL.exists():
                conn.executescript(MIGRATE_V1_4_SQL.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT OR REPLACE INTO _skill_meta(k, v) VALUES ('schema_version', ?)",
                    (schema_version,),
                )
        return 0
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Initialize audit DB")
    p.add_argument("--db", default=None, help="SQLite DB path override")
    p.add_argument("--schema-version", default="1.5.0", help="Schema version tag")
    p.add_argument("--migrate", action="store_true", help="Run migration script after init")
    args = p.parse_args()

    db = resolve_audit_db_path(args.db)
    code = ensure_db(db, args.schema_version, args.migrate)
    print(f"OK  db={db}  schema={args.schema_version}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
