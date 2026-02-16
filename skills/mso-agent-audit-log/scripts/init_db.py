#!/usr/bin/env python3
"""Initialize / migrate audit log DB for multi-swarm-orchestrator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config.yaml"
DEFAULT_DB = (ROOT / "../../02.test/v0.0.1/agent_log.db").resolve()
INIT_SQL = Path(__file__).resolve().parent.parent / "schema" / "init.sql"
MIGRATE_SQL = Path(__file__).resolve().parent.parent / "schema" / "migrate_v1_to_v1_1.sql"

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


def resolve_path(cfg: dict[str, Any], default: str, *keys: str) -> Path:
    base = cfg
    for key in keys:
        if not isinstance(base, dict):
            base = {}
        base = base.get(key)

    raw = str(base) if base is not None else default
    p = Path(raw)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p


def resolve_db_path(cfg: dict[str, Any], cli: str | None = None) -> Path:
    if cli:
        return Path(cli).expanduser().resolve()
    if isinstance(cfg, dict):
        if (audit := cfg.get("audit_log")) and isinstance(audit, dict):
            path = audit.get("db_path")
            if path:
                return resolve_path(cfg, str(DEFAULT_DB), "audit_log", "db_path")
        if (pipeline := cfg.get("pipeline")) and isinstance(pipeline, dict):
            path = pipeline.get("default_db_path")
            if path:
                return resolve_path(cfg, str(DEFAULT_DB), "pipeline", "default_db_path")
    return DEFAULT_DB


def parse_bool(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def ensure_db(db_path: Path, schema_version: str, skip_migrate: bool) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        with conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            if not INIT_SQL.exists():
                raise SystemExit(f"INIT SQL missing: {INIT_SQL}")
            init_sql = INIT_SQL.read_text(encoding="utf-8")
            conn.executescript(init_sql)
            conn.execute("CREATE TABLE IF NOT EXISTS _skill_meta (k TEXT PRIMARY KEY, v TEXT)")
            conn.execute(
                "INSERT OR REPLACE INTO _skill_meta(k, v) VALUES ('schema_version', ?)",
                (schema_version,),
            )

            if not skip_migrate and MIGRATE_SQL.exists():
                conn.execute("SELECT v FROM _skill_meta WHERE k='schema_version'")
                # Migration script is idempotent-friendly enough for this environment.
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
    p.add_argument("--db", default=None, help="SQLite DB path")
    p.add_argument("--schema-version", default="1.3.0", help="Schema version tag")
    p.add_argument("--migrate", action="store_true", help="Run migration script after init")
    args = p.parse_args()

    cfg = parse_config(Path(args.config).expanduser().resolve())
    db = resolve_db_path(cfg, args.db)
    return ensure_db(db, args.schema_version, args.migrate)


if __name__ == "__main__":
    raise SystemExit(main())
