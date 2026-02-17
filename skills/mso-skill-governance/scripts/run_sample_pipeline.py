#!/usr/bin/env python3
"""Run an integrated v0.0.2 sample pipeline on runtime workspace."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[3]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills._shared.runtime_workspace import (  # noqa: E402
    finalize_manifest,
    resolve_runtime_paths,
    sanitize_case_slug,
    update_manifest_phase,
)


def run(cmd: List[str]) -> int:
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)
    return proc.returncode


def _script(path: str) -> str:
    return str((ROOT / path).resolve())


def _ticket_title_slug(task_title: str) -> str:
    return sanitize_case_slug(task_title)[:40]


def main() -> int:
    p = argparse.ArgumentParser(description="Run full v0.0.2 sample orchestration")
    p.add_argument("--goal", required=True)
    p.add_argument("--task-title", required=True)
    p.add_argument("--risk", default="medium", choices=["low", "medium", "high"])
    p.add_argument("--skip-cc", action="store_true")
    p.add_argument("--schema-version", default="1.3.0")
    p.add_argument("--run-id", default="", help="Run ID override")
    p.add_argument("--skill-key", default="msowd", help="Skill key for run-id generation")
    p.add_argument("--case-slug", default="", help="Case slug for run-id generation")
    p.add_argument("--observer-id", default="", help="Observer ID override")
    args = p.parse_args()

    case_slug = args.case_slug.strip() or _ticket_title_slug(args.task_title) or "sample-run"
    paths = resolve_runtime_paths(
        run_id=args.run_id.strip() or None,
        skill_key=args.skill_key,
        case_slug=case_slug,
        observer_id=args.observer_id.strip() or None,
        create=True,
    )

    run_id = paths["run_id"]
    topology_output = Path(paths["topology_path"])
    bundle_output = Path(paths["bundle_path"])
    plan_output = Path(paths["execution_plan_path"])
    task_root = Path(paths["task_context_dir"])
    obs_root = Path(paths["observability_dir"])
    db_path = Path(paths["audit_db_path"])

    topology_output.parent.mkdir(parents=True, exist_ok=True)
    bundle_output.parent.mkdir(parents=True, exist_ok=True)
    plan_output.parent.mkdir(parents=True, exist_ok=True)
    task_root.mkdir(parents=True, exist_ok=True)
    obs_root.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        print(f"[pipeline:{run_id}] 00 collect")
        update_manifest_phase(paths, "00", "active")
        update_manifest_phase(paths, "00", "completed")

        print(f"[pipeline:{run_id}] 10 generate topology")
        if run(
            [
                "python3",
                _script("skills/mso-workflow-topology-design/scripts/generate_topology.py"),
                "--goal",
                args.goal,
                "--risk",
                args.risk,
                "--output",
                str(topology_output),
                "--run-id",
                run_id,
                "--skill-key",
                "msowd",
                "--case-slug",
                case_slug,
                "--observer-id",
                paths["observer_id"],
            ]
        ):
            raise RuntimeError("topology generation failed")

        print(f"[pipeline:{run_id}] 20 build bundle")
        if run(
            [
                "python3",
                _script("skills/mso-mental-model-design/scripts/build_bundle.py"),
                "--topology",
                str(topology_output),
                "--output",
                str(bundle_output),
                "--run-id",
                run_id,
                "--skill-key",
                "msowd",
                "--case-slug",
                case_slug,
                "--observer-id",
                paths["observer_id"],
            ]
        ):
            raise RuntimeError("bundle build failed")

        print(f"[pipeline:{run_id}] 30 build plan")
        if run(
            [
                "python3",
                _script("skills/mso-execution-design/scripts/build_plan.py"),
                "--topology",
                str(topology_output),
                "--bundle",
                str(bundle_output),
                "--output",
                str(plan_output),
                "--run-id",
                run_id,
                "--skill-key",
                "msowd",
                "--case-slug",
                case_slug,
                "--observer-id",
                paths["observer_id"],
            ]
        ):
            raise RuntimeError("execution plan build failed")

        print(f"[pipeline:{run_id}] 40 task bootstrap + ticket")
        if run(["python3", _script("skills/mso-task-context-management/scripts/bootstrap_node.py"), "--path", str(task_root)]):
            raise RuntimeError("task bootstrap failed")

        if run(
            [
                "python3",
                _script("skills/mso-task-context-management/scripts/create_ticket.py"),
                args.task_title,
                "--path",
                str(task_root),
                "--owner",
                "agent",
                "--status",
                "todo",
                "--tags",
                "sample",
                "runtime-v002",
            ]
        ):
            raise RuntimeError("ticket creation failed")

        ticket_files = sorted((task_root / "tickets").glob("*.md"))
        if not ticket_files:
            raise RuntimeError("no ticket generated")
        ticket = ticket_files[-1]

        print(f"[pipeline:{run_id}] 40 dispatch")
        if run(
            [
                "python3",
                _script("skills/mso-agent-collaboration/scripts/dispatch.py"),
                "--ticket",
                str(ticket),
                "--mode",
                "run",
                "--run-id",
                run_id,
                "--skill-key",
                "msoac",
                "--case-slug",
                case_slug,
                "--observer-id",
                paths["observer_id"],
            ]
        ):
            raise RuntimeError("dispatch failed")

        result_json = ticket.with_suffix(".agent-collaboration.json")
        if not result_json.exists():
            raise RuntimeError("dispatch output missing")

        print(f"[pipeline:{run_id}] 50 init audit db")
        if run(
            [
                "python3",
                _script("skills/mso-agent-audit-log/scripts/init_db.py"),
                "--db",
                str(db_path),
                "--migrate",
                "--schema-version",
                args.schema_version,
                "--run-id",
                run_id,
                "--skill-key",
                "msoal",
                "--case-slug",
                case_slug,
                "--observer-id",
                paths["observer_id"],
            ]
        ):
            raise RuntimeError("audit db init failed")

        manifest = json.loads(result_json.read_text(encoding="utf-8"))
        manifest["run_id"] = run_id
        manifest.setdefault("artifact_uri", str(plan_output))

        run_payload_path = obs_root / "run_payload.json"
        run_payload_path.parent.mkdir(parents=True, exist_ok=True)
        run_payload_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"[pipeline:{run_id}] 50 append audit payload")
        if run(
            [
                "python3",
                _script("skills/mso-agent-audit-log/scripts/append_from_payload.py"),
                str(run_payload_path),
                "--db",
                str(db_path),
                "--schema-version",
                args.schema_version,
                "--run-id",
                run_id,
                "--skill-key",
                "msoal",
                "--case-slug",
                case_slug,
                "--observer-id",
                paths["observer_id"],
            ]
        ):
            raise RuntimeError("audit append failed")

        print(f"[pipeline:{run_id}] 60 observability")
        if run(
            [
                "python3",
                _script("skills/mso-observability/scripts/collect_observations.py"),
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
                "--skill-key",
                "msoobs",
                "--case-slug",
                case_slug,
                "--observer-id",
                paths["observer_id"],
            ]
        ):
            raise RuntimeError("observability collection failed")

        print(f"[pipeline:{run_id}] 60 portfolio status")
        if run(
            [
                "python3",
                _script("skills/mso-observability/scripts/generate_portfolio_status.py"),
                "--run-id",
                run_id,
                "--skill-key",
                "msoobs",
                "--case-slug",
                case_slug,
                "--observer-id",
                paths["observer_id"],
                "--output",
                str(obs_root / "portfolio_status.md"),
            ]
        ):
            raise RuntimeError("portfolio status generation failed")

        if not args.skip_cc:
            print(f"[pipeline:{run_id}] 70 cc validation")
            if run(
                [
                    "python3",
                    _script("skills/mso-skill-governance/scripts/validate_cc_contracts.py"),
                    "--run-id",
                    run_id,
                    "--skill-key",
                    "msogov",
                    "--case-slug",
                    case_slug,
                    "--observer-id",
                    paths["observer_id"],
                ]
            ):
                raise RuntimeError("cc validation failed")

        finalize_manifest(paths, "completed", tags=["sample", "runtime-v0.0.2"])
        print(f"[pipeline:{run_id}] done")
        return 0
    except Exception as exc:
        finalize_manifest(paths, "failed", error={"message": str(exc), "phase": "pipeline"})
        print(f"[pipeline:{run_id}] failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
