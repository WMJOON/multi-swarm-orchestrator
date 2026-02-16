#!/usr/bin/env python3
"""Run an integrated v0.0.1 sample pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config.yaml"

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
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    if yaml is None:
        return {}

    parsed = yaml.safe_load(raw)
    return parsed if isinstance(parsed, dict) else {}


def resolve_path(cfg: Dict[str, Any], default: str, *keys: str) -> Path:
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


def run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)
    return proc.returncode


def init_db(db_path: Path) -> None:
    script = ROOT / "skills" / "mso-agent-audit-log" / "scripts" / "init_db.py"
    run(["python3", str(script), "--db", str(db_path), "--migrate"])


def write_audit_from_payload(payload: dict, out_dir: Path, db_path: Path, schema_version: str) -> int:
    in_path = out_dir / "run_payload.json"
    in_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    script = ROOT / "skills" / "mso-agent-audit-log" / "scripts" / "append_from_payload.py"
    return run([
        "python3",
        str(script),
        str(in_path),
        "--db",
        str(db_path),
        "--schema-version",
        schema_version,
    ])


def main() -> int:
    p = argparse.ArgumentParser(description="Run full v0.0.1 sample orchestration")
    p.add_argument("--goal", required=True)
    p.add_argument("--task-title", required=True)
    p.add_argument("--risk", default="medium", choices=["low", "medium", "high"])
    p.add_argument("--skip-cc", action="store_true")
    p.add_argument("--config", default=str(CONFIG_PATH), help="Path to orchestrator config file")
    p.add_argument("--workflow-output-dir", default=None, help="workflow outputs directory")
    p.add_argument("--task-dir", default=None, help="task-context root directory")
    p.add_argument("--observation-dir", default=None, help="observations output directory")
    p.add_argument("--db-path", default=None, help="agent_log.db location")
    p.add_argument("--schema-version", default="1.3.0")
    args = p.parse_args()

    cfg = load_config(Path(args.config).expanduser().resolve())

    default_outputs = str(ROOT / "../../02.test/v0.0.1/outputs")
    default_task_root = str(ROOT / "../../02.test/v0.0.1/task-context")
    default_observations = str(ROOT / "../../02.test/v0.0.1/observations")
    default_db = str(ROOT / "../../02.test/v0.0.1/agent_log.db")

    outputs_root = Path(args.workflow_output_dir).resolve() if args.workflow_output_dir else resolve_path(
        cfg,
        default_outputs,
        "pipeline",
        "default_workflow_output_dir",
    )
    task_root = Path(args.task_dir).resolve() if args.task_dir else resolve_path(
        cfg,
        default_task_root,
        "pipeline",
        "default_task_dir",
    )
    obs_root = Path(args.observation_dir).resolve() if args.observation_dir else resolve_path(
        cfg,
        default_observations,
        "pipeline",
        "default_observation_dir",
    )
    db_path = Path(args.db_path).resolve() if args.db_path else resolve_path(
        cfg,
        default_db,
        "audit_log",
        "db_path",
    )

    outputs_root.mkdir(parents=True, exist_ok=True)
    task_root.mkdir(parents=True, exist_ok=True)
    obs_root.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    run_id = f"run-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    topology_output = outputs_root / "workflow_topology_spec.json"
    bundle_output = outputs_root / "mental_model_bundle.json"
    plan_output = outputs_root / "execution_plan.json"

    print(f"[pipeline:{run_id}] 00 generate topology")
    if run([
        "python3",
        "skills/mso-workflow-topology-design/scripts/generate_topology.py",
        "--goal",
        args.goal,
        "--risk",
        args.risk,
        "--output",
        str(topology_output),
    ]):
        return 1

    print(f"[pipeline:{run_id}] 01 build bundle")
    if run([
        "python3",
        "skills/mso-mental-model-design/scripts/build_bundle.py",
        "--topology",
        str(topology_output),
        "--output",
        str(bundle_output),
    ]):
        return 1

    print(f"[pipeline:{run_id}] 02 build plan")
    if run([
        "python3",
        "skills/mso-execution-design/scripts/build_plan.py",
        "--topology",
        str(topology_output),
        "--bundle",
        str(bundle_output),
        "--output",
        str(plan_output),
    ]):
        return 1

    print(f"[pipeline:{run_id}] 03 task bootstrap + ticket")
    if run([
        "python3",
        "skills/mso-task-context-management/scripts/bootstrap_node.py",
        "--path",
        str(task_root),
    ]):
        return 1

    if run([
        "python3",
        "skills/mso-task-context-management/scripts/create_ticket.py",
        args.task_title,
        "--path",
        str(task_root),
        "--owner",
        "agent",
        "--status",
        "todo",
        "--tags",
        "sample",
    ]):
        return 1

    ticket_files = sorted((task_root / "tickets").glob("*.md"))
    if not ticket_files:
        print("no ticket generated")
        return 1
    ticket = ticket_files[-1]

    print(f"[pipeline:{run_id}] 04 dispatch")
    if run([
        "python3",
        "skills/mso-agent-collaboration/scripts/dispatch.py",
        "--ticket",
        str(ticket),
        "--mode",
        "run",
    ]):
        return 1

    result_json = ticket.with_suffix(".agent-collaboration.json")
    if not result_json.exists():
        print("dispatch output missing")
        return 1

    init_db(db_path)

    manifest = json.loads(result_json.read_text(encoding="utf-8"))
    manifest.setdefault("run_id", run_id)
    manifest.setdefault("artifact_uri", str(plan_output))
    if write_audit_from_payload(manifest, obs_root, db_path, args.schema_version):
        print("audit append warning (non-blocking)")

    print(f"[pipeline:{run_id}] 05 observability")
    if run([
        "python3",
        "skills/mso-observability/scripts/collect_observations.py",
        "--db",
        str(db_path),
        "--run-id",
        run_id,
        "--artifact",
        str(plan_output),
        "--out",
        str(obs_root),
        "--mode",
        "scheduled",
        "--config",
        str(args.config),
    ]):
        return 1

    if not args.skip_cc:
        print(f"[pipeline:{run_id}] 06 cc validation")
        if run([
            "python3",
            "skills/mso-skill-governance/scripts/validate_cc_contracts.py",
            "--config",
            str(args.config),
        ]):
            return 1

    print(f"[pipeline:{run_id}] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
