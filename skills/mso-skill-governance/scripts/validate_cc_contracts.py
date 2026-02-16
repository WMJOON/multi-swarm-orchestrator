#!/usr/bin/env python3
"""Validate CC-01~CC-05 contract definitions and optional runtime wiring."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"
CC_SCHEMA_PATH = SCRIPT_DIR.parent / "schemas" / "cc_contracts.schema.json"
DEFAULT_OUTPUT_DIR = (ROOT / "../02.test/v0.0.1/outputs").resolve()
DEFAULT_TASK_DIR = (ROOT / "../02.test/v0.0.1/task-context").resolve()
DEFAULT_DB = (ROOT / "../02.test/v0.0.1/agent_log.db").resolve()

REQUIRED_CONTRACTS = {
    "CC-01": {
        "producer": "mso-workflow-topology-design",
        "consumer": "mso-execution-design",
        "required_output_keys": ["run_id", "nodes", "edges", "topology_type", "rsv_total"],
        "required_input_keys": ["run_id", "nodes", "topology_type"],
    },
    "CC-02": {
        "producer": "mso-mental-model-design",
        "consumer": "mso-execution-design",
        "required_output_keys": ["node_chart_map", "local_charts", "output_contract", "bundle_ref", "run_id"],
        "required_input_keys": ["nodes", "assigned_dqs"],
    },
    "CC-03": {
        "producer": "mso-task-context-management",
        "consumer": "mso-agent-collaboration",
        "required_output_keys": ["task_context_id", "id", "status", "owner", "due_by", "dependencies"],
        "required_input_keys": ["id", "status", "owner"],
    },
    "CC-04": {
        "producer": "mso-agent-collaboration",
        "consumer": "mso-agent-audit-log",
        "required_output_keys": ["dispatch_mode", "handoff_payload", "run_id", "status", "requires_manual_confirmation", "fallback_reason"],
        "required_input_keys": ["id", "status", "owner", "due_by", "dependencies", "tags"],
    },
    "CC-05": {
        "producer": "mso-agent-audit-log",
        "consumer": "mso-observability",
        "required_output_keys": ["run_id", "artifact_uri", "status", "errors", "warnings", "next_actions", "metadata"],
        "required_input_keys": ["run_id", "artifact_uri", "event_type", "correlation"],
    },
}


try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def parse_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}

    try:
        cfg = json.loads(raw)
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        pass

    if yaml is None:
        return {}

    try:
        loaded = yaml.safe_load(raw)
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        return {}
    return {}


def resolve_path(cfg: Dict[str, Any], fallback: str, *keys: str) -> Path:
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


def resolve_outputs_dir(cfg: Dict[str, Any], cli: str | None = None) -> Path:
    if cli:
        return Path(cli).expanduser().resolve()
    return resolve_path(cfg, str(DEFAULT_OUTPUT_DIR), "pipeline", "default_workflow_output_dir")


def resolve_task_dir(cfg: Dict[str, Any], cli: str | None = None) -> Path:
    if cli:
        return Path(cli).expanduser().resolve()
    return resolve_path(cfg, str(DEFAULT_TASK_DIR), "pipeline", "default_task_dir")


def resolve_db_path(cfg: Dict[str, Any], cli: str | None = None) -> Path:
    if cli:
        return Path(cli).expanduser().resolve()

    if isinstance(cfg.get("audit_log"), dict):
        path = cfg["audit_log"].get("db_path")
        if path:
            return resolve_path(cfg, str(DEFAULT_DB), "audit_log", "db_path")

    if isinstance(cfg.get("pipeline"), dict):
        path = cfg["pipeline"].get("default_db_path")
        if path:
            return resolve_path(cfg, str(DEFAULT_DB), "pipeline", "default_db_path")

    return DEFAULT_DB


def resolve_contract_output(cfg: Dict[str, Any], contract_id: str) -> Path:
    outputs = resolve_outputs_dir(cfg)
    tasks = resolve_task_dir(cfg)

    mapping = {
        "CC-01": outputs / "workflow_topology_spec.json",
        "CC-02": outputs / "mental_model_bundle.json",
        "CC-03": tasks / "tickets",
        "CC-04": tasks / "tickets",
        "CC-05": resolve_db_path(cfg),
    }
    return mapping[contract_id]


def parse_frontmatter(path: Path) -> Dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    raw = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        raw.append(line)

    front: Dict[str, Any] = {}
    for line in raw:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        value = v.strip().strip('"\'')
        front[k.strip()] = value
    return front


def check_frontmatter_fields(path: Path, required_fields: List[str]) -> Tuple[bool, List[str]]:
    fm = parse_frontmatter(path)
    missing = [f for f in required_fields if f not in fm]
    if missing:
        return False, [f"missing frontmatter fields: {', '.join(sorted(missing))}"]
    return True, []


def parse_list(raw: Any) -> List[str]:
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
            return [x.strip().strip('"\'') for x in body.split(",") if x.strip()]
        return [raw]
    return [str(raw)]


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    return json.loads(raw) if raw else {}


def parse_contracts(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    cc = cfg.get("cc_contracts")
    if isinstance(cc, dict) and isinstance(cc.get("contracts"), list):
        return [c for c in cc.get("contracts") if isinstance(c, dict)]
    if isinstance(cc, list):
        return [c for c in cc if isinstance(c, dict)]
    return []


def check_file_json_fields(path: Path, required_fields: List[str]) -> tuple[bool, List[str]]:
    if not path.exists():
        return False, [f"missing file: {path}"]

    data = load_json(path)
    if not isinstance(data, dict):
        return False, ["not a json object"]

    missing = [f for f in required_fields if f not in data]
    if missing:
        return False, [f"missing fields: {', '.join(missing)}"]
    return True, []


def check_db_exists(path: Path) -> bool:
    return path.exists() and path.is_file()


def check_contract_definitions(contracts: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    index = {c.get("id"): c for c in contracts if isinstance(c, dict)}
    warnings: List[Dict[str, Any]] = []
    fails: List[Dict[str, Any]] = []

    required_keys = [
        "id",
        "producer",
        "consumer",
        "required_input_keys",
        "required_output_keys",
        "compatibility_policy",
    ]

    for cid in sorted(REQUIRED_CONTRACTS.keys()):
        row = REQUIRED_CONTRACTS[cid]
        item = index.get(cid)
        if not item:
            fails.append({
                "contract": cid,
                "level": "fail",
                "finding": "missing required contract ID",
                "producer": row["producer"],
                "consumer": row["consumer"],
                "evidence": "config.yaml cc_contracts",
            })
            continue

        missing = [k for k in required_keys if k not in item]
        if missing:
            fails.append({
                "contract": cid,
                "level": "fail",
                "finding": f"missing contract fields: {', '.join(missing)}",
                "evidence": f"{cid}: {item}",
            })
            continue

        for k in ["producer", "consumer"]:
            if not isinstance(item.get(k), str):
                fails.append({
                    "contract": cid,
                    "level": "fail",
                    "finding": f"{k} must be a string",
                    "evidence": f"{cid}: {item.get(k)!r}",
                })

        if item.get("producer") != row["producer"] or item.get("consumer") != row["consumer"]:
            warnings.append({
                "contract": cid,
                "level": "warn",
                "finding": "producer/consumer pair differs from expected",
                "evidence": f"expected {row['producer']}->{row['consumer']}, configured {item.get('producer')}->{item.get('consumer')}",
            })

    return warnings, fails


def check_runtime_wiring(contracts: List[Dict[str, Any]], cfg: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    warnings: List[Dict[str, Any]] = []
    fails: List[Dict[str, Any]] = []
    index = {c.get("id"): c for c in contracts if isinstance(c, dict)}

    for cid in sorted(REQUIRED_CONTRACTS.keys()):
        expected = REQUIRED_CONTRACTS[cid]
        producer_output = resolve_contract_output(cfg, cid)

        item = index.get(cid)
        if item:
            raw_override = item.get("producer_output_path")
            if raw_override:
                producer_output = resolve_path(cfg, str(producer_output), raw_override)

        if cid == "CC-03":
            if not producer_output.exists():
                fails.append({
                    "contract": cid,
                    "level": "fail",
                    "finding": "ticket directory missing",
                    "evidence": str(producer_output),
                })
                continue

            tickets = sorted(producer_output.glob("*.md"))
            if not tickets:
                warnings.append({
                    "contract": cid,
                    "level": "warn",
                    "finding": "no tickets found",
                    "evidence": str(producer_output),
                })
                continue

            for ticket in tickets[:2]:
                ok, problems = check_frontmatter_fields(ticket, list(expected["required_output_keys"]) + ["status"])
                if not ok:
                    fails.append({
                        "contract": cid,
                        "level": "fail",
                        "finding": "; ".join(problems),
                        "evidence": str(ticket),
                    })
                    break

        elif cid == "CC-04":
            collab_outputs = sorted(producer_output.glob("*.agent-collaboration.json"))
            if not collab_outputs:
                warnings.append({
                    "contract": cid,
                    "level": "warn",
                    "finding": "no collaboration outputs found",
                    "evidence": str(producer_output),
                })
                continue

            for path in collab_outputs[:1]:
                ok, problems = check_file_json_fields(path, list(expected["required_output_keys"]))
                if not ok:
                    fails.append({
                        "contract": cid,
                        "level": "fail",
                        "finding": "; ".join(problems),
                        "evidence": str(path),
                    })

        elif cid == "CC-05":
            if not check_db_exists(producer_output):
                warnings.append({
                    "contract": cid,
                    "level": "warn",
                    "finding": "agent_log.db missing",
                    "evidence": str(producer_output),
                })
            # No strict runtime schema check in this offline mode.

        elif producer_output.exists() and producer_output.suffix == ".json":
            ok, problems = check_file_json_fields(producer_output, list(expected["required_output_keys"]))
            if not ok:
                fails.append({
                    "contract": cid,
                    "level": "fail",
                    "finding": "; ".join(problems),
                    "evidence": str(producer_output),
                })

    return warnings, fails


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CC contract definitions")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to orchestrator config file")
    parser.add_argument("--workflow-output-dir", default=None, help="workflow outputs directory")
    parser.add_argument("--task-dir", default=None, help="task-context root directory")
    parser.add_argument("--db-path", default=None, help="agent_log.db path")
    parser.add_argument("--output", default=None, help="CC validation output path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not CC_SCHEMA_PATH.exists():
        print(f"ERR: missing CC schema file: {CC_SCHEMA_PATH}")
        return 1

    cfg = parse_config(Path(args.config).expanduser().resolve())
    cfg = dict(cfg)

    # CLI fallback: if provided, only replace the relevant config key; if omitted, keep config/default.
    if args.workflow_output_dir:
        cfg.setdefault("pipeline", {})["default_workflow_output_dir"] = str(args.workflow_output_dir)
    if args.task_dir:
        cfg.setdefault("pipeline", {})["default_task_dir"] = str(args.task_dir)
    if args.db_path:
        cfg.setdefault("audit_log", {})["db_path"] = str(args.db_path)

    contracts = parse_contracts(cfg)
    w1, f1 = check_contract_definitions(contracts)
    w2, f2 = check_runtime_wiring(contracts, cfg)
    warnings = w1 + w2
    fails = f1 + f2

    output_root = resolve_outputs_dir(cfg, args.workflow_output_dir)
    output_path = Path(args.output).expanduser().resolve() if args.output else (output_root / "cc_contract_validation.json")

    status = "fail" if fails else ("warn" if warnings else "ok")
    payload = {
        "status": status,
        "version": "0.0.1",
        "cc_coupling_id": "CC-SET",
        "required_skill_ids": sorted({v["producer"] for v in REQUIRED_CONTRACTS.values()} | {v["consumer"] for v in REQUIRED_CONTRACTS.values()}),
        "schema_version": "1.0.0",
        "findings": warnings + fails,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"CC validation status: {status}")
        print(f"findings: {len(payload['findings'])}")

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
