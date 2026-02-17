#!/usr/bin/env python3
"""Initialize / migrate audit log DB for runtime workspace."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config.yaml"
INIT_SQL = Path(__file__).resolve().parent.parent / "schema" / "init.sql"
MIGRATE_SQL = Path(__file__).resolve().parent.parent / "schema" / "migrate_v1_to_v1_1.sql"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mso_runtime.runtime_workspace import (  # noqa: E402
    resolve_runtime_paths,
    sanitize_case_slug,
    update_manifest_phase,
)


def ensure_db(db_path: Path, schema_version: str, run_migrate: bool) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        with conn:
            conn.execute("PRAGMA foreign_keys = ON;")
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
        return 0
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Initialize audit DB")
    p.add_argument("--config", default=str(CONFIG_PATH), help="Path to orchestrator config file")
    p.add_argument("--db", default=None, help="SQLite DB path override")
    p.add_argument("--schema-version", default="1.3.0", help="Schema version tag")
    p.add_argument("--migrate", action="store_true", help="Run migration script after init")
    p.add_argument("--run-id", default="", help="Run ID override")
    p.add_argument("--skill-key", default="msoal", help="Skill key for run-id generation")
    p.add_argument("--case-slug", default="", help="Case slug for run-id generation")
    p.add_argument("--observer-id", default="", help="Observer ID override")
    args = p.parse_args()

    paths = resolve_runtime_paths(
        config_path=args.config,
        run_id=args.run_id.strip() or None,
        skill_key=args.skill_key,
        case_slug=sanitize_case_slug(args.case_slug or "audit-db"),
        observer_id=args.observer_id.strip() or None,
        create=True,
    )

    db = Path(args.db).expanduser().resolve() if args.db else Path(paths["audit_db_path"])

    try:
        update_manifest_phase(paths, "50", "active")
        code = ensure_db(db, args.schema_version, args.migrate)
        update_manifest_phase(paths, "50", "completed")
        return code
    except Exception:
        update_manifest_phase(paths, "50", "failed")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
