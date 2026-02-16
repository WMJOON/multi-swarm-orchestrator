#!/usr/bin/env python3
"""Adapter entrypoint for ticket -> ai-collaborator bridge."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config.yaml"
DEFAULT_TASK_DIR = (ROOT / "../02.test/v0.0.1/task-context").resolve()

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


def parse_config(path: Path) -> Dict[str, Any]:
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


def resolve_ai_root(cfg: Dict[str, Any]) -> Path | None:
    bundled = (ROOT / "skills" / "mso-agent-collaboration" / "v0.0.1" / "Skill" / "ai-collaborator").resolve()
    if (bundled / "scripts" / "collaborate.py").exists():
        return (ROOT / "skills" / "mso-agent-collaboration").resolve()

    rel = (
        cfg
        .get("external_dependencies", {})
        .get("ai-collaborator", {})
        .get("resolve_order", [])
    )
    for item in rel if isinstance(rel, list) else []:
        if isinstance(item, dict) and "relative" in item:
            p = (ROOT / str(item["relative"]).strip()).resolve()
            if (p / "v0.0.1" / "Skill" / "ai-collaborator" / "scripts" / "collaborate.py").exists():
                return p

    return None


def parse_frontmatter(path: Path) -> Dict[str, str]:
    if not path.exists():
        raise ValueError(f"ticket not found: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    raw = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        raw.append(line)

    if yaml is not None and raw:
        data = yaml.safe_load("\n".join(raw))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if k is not None}

    data: Dict[str, str] = {}
    for line in raw:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip().strip('"\'' )
    return data


def _parse_list(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        if raw.startswith("[") and raw.endswith("]"):
            body = raw[1:-1].strip()
            return [x.strip().strip('"\'' ) for x in body.split(",") if x.strip()]
        return [raw]
    return [str(raw)]


def infer_mode(fm: Dict[str, str], requested: str | None) -> str:
    if requested:
        return requested
    tags = _parse_list(fm.get("tags", ""))
    if "batch" in tags:
        return "batch"
    if "swarm" in tags or "multi" in tags:
        return "swarm"
    if fm.get("priority", "").strip().lower() in {"high", "critical"}:
        return "batch"
    return "run"


def artifact_reference(fm: Dict[str, str], ticket: Path) -> str:
    direct = (fm.get("artifact_uri") or "").strip()
    if direct:
        return direct
    return str(ticket)


def build_payload(fm: Dict[str, str], mode: str, artifact_uri: str) -> tuple[str, Dict[str, Any]]:
    task_id = fm.get("id") or fm.get("task_context_id") or "TASK-UNKNOWN"
    title = fm.get("title") or fm.get("task", "ticket")
    owner = fm.get("owner", "agent")
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # ai-collaborator task spec format: provider:prompt[:id]
    safe_title = title.replace(":", " - ").replace("\n", " ").strip() or "ticket"
    task_spec = f"codex:{safe_title}:{task_id}"
    handoff_payload: Dict[str, Any] = {
        "run_id": run_id,
        "task_id": task_id,
        "mode": mode,
        "artifact_uri": artifact_uri,
        "task_name": title,
        "owner": owner,
        "dependencies": _parse_list(fm.get("dependencies", "")),
        "tags": _parse_list(fm.get("tags", "")),
        "due_by": fm.get("due_by", ""),
        "status": fm.get("status", "todo"),
        "state_machine_version": fm.get("task_context_id", "v1"),
        "task_spec": task_spec,
        "cc_coupling_id": fm.get("cc_coupling_id", "CC-04"),
        "required_skill_ids": [
            "mso-agent-collaboration",
            "mso-task-context-management",
            "mso-agent-audit-log",
        ],
        "missing_dependency_action": "manual_required",
    }

    return task_spec, handoff_payload


def run_cli(ai_root: Path, mode: str, task_spec: str) -> Dict[str, Any]:
    script = ai_root / "v0.0.1" / "Skill" / "ai-collaborator" / "scripts" / "collaborate.py"
    if not script.exists():
        raise FileNotFoundError(f"collaborator script missing: {script}")

    task_timeout_s = int(os.environ.get("MSO_COLLAB_TASK_TIMEOUT", "30"))
    proc_timeout_s = int(os.environ.get("MSO_COLLAB_PROC_TIMEOUT", str(max(60, task_timeout_s + 20))))

    base_cmd = [
        "python3",
        str(script),
        "run",
        "--provider",
        "codex",
        "--tasks",
        task_spec,
        "--timeout",
        str(task_timeout_s),
        "--format",
        "json",
        "--no-fail",
    ]
    if mode == "batch":
        base_cmd.extend(["--parallel", "3"])

    proc = subprocess.run(base_cmd, capture_output=True, text=True, timeout=proc_timeout_s)
    if proc.returncode != 0:
        return {
            "status": "failure",
            "raw_stdout": proc.stdout.strip(),
            "raw_stderr": proc.stderr.strip(),
            "error": f"cli_exit={proc.returncode}",
        }

    if not proc.stdout.strip():
        return {"status": "success", "raw_stdout": "", "raw_stderr": proc.stderr.strip()}

    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"status": "success", "raw_stdout": proc.stdout.strip(), "raw_stderr": proc.stderr.strip()}


def build_fallback(task_id: str, reason: str, artifact_uri: str) -> Dict[str, Any]:
    return {
        "dispatch_mode": "run",
        "handoff_payload": {
            "task_id": task_id,
            "mode": "run",
            "artifact_uri": artifact_uri,
            "requires_manual_confirmation": True,
            "fallback_reason": reason,
        },
        "requires_manual_confirmation": True,
        "fallback_reason": reason,
        "status": "in_progress",
        "next_actions": ["manual_dispatch", "validate_manual_route"],
        "artifact_uri": artifact_uri,
        "run_id": f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "errors": [reason],
        "warnings": ["ai-collaborator runtime missing or unavailable"],
        "metadata": {
            "schema_version": "0.0.1",
            "cc_coupling_id": "CC-04",
            "required_skill_ids": [
                "mso-agent-collaboration",
                "mso-task-context-management",
                "mso-agent-audit-log",
            ],
            "missing_dependency_action": "manual_required",
        },
    }


def dispatch_one(ticket: Path, requested_mode: str | None, cfg: Dict[str, Any]) -> int:
    fm = parse_frontmatter(ticket)
    status = (fm.get("status") or "todo").strip()
    if status not in ("todo", "in_progress", "queued"):
        print(f"SKIP: status={status}")
        return 0

    mode = infer_mode(fm, requested_mode)
    task_id = fm.get("id") or "TKT-UNKNOWN"
    artifact_uri = artifact_reference(fm, ticket)
    task_spec, handoff_payload = build_payload(fm, mode, artifact_uri)
    handoff_payload["dispatch_mode"] = mode
    handoff_payload["requires_manual_confirmation"] = False

    ai_root = resolve_ai_root(cfg)
    out_json_path = ticket.with_suffix(".agent-collaboration.json")

    if not ai_root:
        result = build_fallback(task_id, "ai-collaborator runtime not found", artifact_uri)
        out_json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"FALLBACK: {ticket}")
        return 0

    try:
        cli_result = run_cli(ai_root, mode, task_spec)
    except Exception as exc:
        result = build_fallback(task_id, f"collaborator execution failed: {exc}", artifact_uri)
        out_json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"FALLBACK: {ticket}")
        return 0

    requires_manual = False
    fallback_reason = None
    if isinstance(cli_result, dict) and cli_result.get("status") == "failure":
        requires_manual = True
        fallback_reason = cli_result.get("error", "unknown collaborator failure")

    summary = {
        "dispatch_mode": mode,
        "handoff_payload": handoff_payload,
        "requires_manual_confirmation": requires_manual,
        "fallback_reason": fallback_reason,
        "status": "success" if not requires_manual else "in_progress",
        "run_id": handoff_payload["run_id"],
        "artifact_uri": artifact_uri,
        "errors": cli_result.get("errors", []) if isinstance(cli_result, dict) else [],
        "warnings": cli_result.get("warnings", []),
        "next_actions": ["monitor"],
        "metadata": {
            "schema_version": "0.0.1",
            "cc_coupling_id": "CC-04",
            "required_skill_ids": [
                "mso-agent-collaboration",
                "mso-task-context-management",
                "mso-agent-audit-log",
            ],
            "missing_dependency_action": "manual_required" if requires_manual else "auto",
        },
    }

    out_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DISPATCHED: {ticket} ({mode})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Dispatch one ticket")
    p.add_argument("--ticket", required=True, help="Path to ticket markdown")
    p.add_argument("--mode", default=None, choices=["run", "batch", "swarm"], help="Dispatch mode override")
    p.add_argument("--config", default=str(CONFIG_PATH), help="Path to orchestrator config file")
    p.add_argument("--task-dir", default=None, help="Optional task-context root path")
    args = p.parse_args()

    cfg = parse_config(Path(args.config).expanduser().resolve()) if args.config else {}
    task_root = Path(args.task_dir).resolve() if args.task_dir else resolve_path(
        cfg,
        str(DEFAULT_TASK_DIR),
        "pipeline",
        "default_task_dir",
    )
    ticket = Path(args.ticket).resolve()
    if not ticket.is_relative_to(task_root):
        task_root = ticket.parent

    return dispatch_one(ticket, args.mode, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
