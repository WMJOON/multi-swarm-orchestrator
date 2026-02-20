#!/usr/bin/env python3
"""Validate CC-01~CC-06 contract definitions and runtime wiring."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
CC_SCHEMA_PATH = SCRIPT_DIR.parent / "schemas" / "cc_contracts.schema.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills._shared.runtime_workspace import (  # noqa: E402
    resolve_runtime_paths,
    sanitize_case_slug,
    update_manifest_phase,
)

from _cc_defaults import CC_VERSION, get_contract_index, get_default_contracts, get_required_skill_ids

REQUIRED_CONTRACTS = get_contract_index()


def resolve_contract_output(paths: Dict[str, Any], contract_id: str) -> Path:
    mapping = {
        "CC-01": Path(paths["topology_path"]),
        "CC-02": Path(paths["bundle_path"]),
        "CC-03": Path(paths["task_context_dir"]) / "tickets",
        "CC-04": Path(paths["task_context_dir"]) / "tickets",
        "CC-05": Path(paths["audit_db_path"]),
        "CC-06": Path(paths["execution_plan_path"]),
    }
    return mapping[contract_id]


def render_override(raw_override: str, paths: Dict[str, Any], fallback: Path) -> Path:
    text = raw_override.replace("{run_id}", paths["run_id"])
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (Path(paths["settings"]["project_root"]) / path).resolve()
    return path if text.strip() else fallback


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
        front[k.strip()] = v.strip().strip("\"'")
    return front


def check_frontmatter_fields(path: Path, required_fields: List[str]) -> Tuple[bool, List[str]]:
    fm = parse_frontmatter(path)
    missing = [f for f in required_fields if f not in fm]
    if missing:
        return False, [f"missing frontmatter fields: {', '.join(sorted(missing))}"]
    return True, []


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    return json.loads(raw) if raw else {}


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
        expected = REQUIRED_CONTRACTS[cid]
        item = index.get(cid)
        if not item:
            fails.append(
                {
                    "contract": cid,
                    "level": "fail",
                    "finding": "missing required contract ID",
                    "producer": expected["producer"],
                    "consumer": expected["consumer"],
                    "evidence": "embedded defaults: scripts/_cc_defaults.py",
                }
            )
            continue

        missing = [k for k in required_keys if k not in item]
        if missing:
            fails.append(
                {
                    "contract": cid,
                    "level": "fail",
                    "finding": f"missing contract fields: {', '.join(missing)}",
                    "evidence": f"{cid}: {item}",
                }
            )
            continue

        for key in ["producer", "consumer"]:
            if not isinstance(item.get(key), str):
                fails.append(
                    {
                        "contract": cid,
                        "level": "fail",
                        "finding": f"{key} must be a string",
                        "evidence": f"{cid}: {item.get(key)!r}",
                    }
                )

        if item.get("producer") != expected["producer"] or item.get("consumer") != expected["consumer"]:
            warnings.append(
                {
                    "contract": cid,
                    "level": "warn",
                    "finding": "producer/consumer pair differs from expected",
                    "evidence": (
                        f"expected {expected['producer']}->{expected['consumer']}, "
                        f"configured {item.get('producer')}->{item.get('consumer')}"
                    ),
                }
            )

    return warnings, fails


def check_runtime_wiring(
    contracts: List[Dict[str, Any]],
    paths: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    warnings: List[Dict[str, Any]] = []
    fails: List[Dict[str, Any]] = []
    index = {c.get("id"): c for c in contracts if isinstance(c, dict)}

    for cid in sorted(REQUIRED_CONTRACTS.keys()):
        expected = REQUIRED_CONTRACTS[cid]
        producer_output = resolve_contract_output(paths, cid)

        item = index.get(cid)
        if item:
            raw_override = item.get("producer_output_path")
            if isinstance(raw_override, str) and raw_override.strip():
                producer_output = render_override(raw_override, paths, producer_output)

        if cid == "CC-03":
            if not producer_output.exists():
                fails.append(
                    {
                        "contract": cid,
                        "level": "fail",
                        "finding": "ticket directory missing",
                        "evidence": str(producer_output),
                    }
                )
                continue

            tickets = sorted(producer_output.glob("*.md"))
            if not tickets:
                warnings.append(
                    {
                        "contract": cid,
                        "level": "warn",
                        "finding": "no tickets found",
                        "evidence": str(producer_output),
                    }
                )
                continue

            for ticket in tickets[:2]:
                ok, problems = check_frontmatter_fields(ticket, list(expected["required_output_keys"]) + ["status"])
                if not ok:
                    fails.append(
                        {
                            "contract": cid,
                            "level": "fail",
                            "finding": "; ".join(problems),
                            "evidence": str(ticket),
                        }
                    )
                    break

        elif cid == "CC-04":
            collab_outputs = sorted(producer_output.glob("*.agent-collaboration.json"))
            if not collab_outputs:
                warnings.append(
                    {
                        "contract": cid,
                        "level": "warn",
                        "finding": "no collaboration outputs found",
                        "evidence": str(producer_output),
                    }
                )
                continue

            for path in collab_outputs[:1]:
                ok, problems = check_file_json_fields(path, list(expected["required_output_keys"]))
                if not ok:
                    fails.append(
                        {
                            "contract": cid,
                            "level": "fail",
                            "finding": "; ".join(problems),
                            "evidence": str(path),
                        }
                    )

        elif cid == "CC-05":
            if not check_db_exists(producer_output):
                warnings.append(
                    {
                        "contract": cid,
                        "level": "warn",
                        "finding": "agent_log.db missing",
                        "evidence": str(producer_output),
                    }
                )

        elif cid == "CC-06":
            if not producer_output.exists():
                warnings.append(
                    {
                        "contract": cid,
                        "level": "warn",
                        "finding": "execution_plan.json missing",
                        "evidence": str(producer_output),
                    }
                )
                continue

            data = load_json(producer_output)
            if not isinstance(data, dict):
                fails.append(
                    {
                        "contract": cid,
                        "level": "fail",
                        "finding": "execution_plan is not a json object",
                        "evidence": str(producer_output),
                    }
                )
                continue

            eg = data.get("execution_graph")
            if not isinstance(eg, dict) or not eg:
                fails.append(
                    {
                        "contract": cid,
                        "level": "fail",
                        "finding": "execution_graph missing or empty",
                        "evidence": str(producer_output),
                    }
                )
                continue

            for node_id, node in eg.items():
                if not isinstance(node, dict):
                    continue
                if "type" not in node:
                    fails.append(
                        {
                            "contract": cid,
                            "level": "fail",
                            "finding": f"node {node_id}: missing 'type' field",
                            "evidence": str(producer_output),
                        }
                    )
                    break

        elif producer_output.exists() and producer_output.suffix == ".json":
            ok, problems = check_file_json_fields(producer_output, list(expected["required_output_keys"]))
            if not ok:
                fails.append(
                    {
                        "contract": cid,
                        "level": "fail",
                        "finding": "; ".join(problems),
                        "evidence": str(producer_output),
                    }
                )

    return warnings, fails


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CC contract definitions")
    parser.add_argument("--output", default=None, help="CC validation output path")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--run-id", default="", help="Run ID override")
    parser.add_argument("--skill-key", default="msogov", help="Skill key for run-id generation")
    parser.add_argument("--case-slug", default="", help="Case slug for run-id generation")
    parser.add_argument("--observer-id", default="", help="Observer ID override")
    args = parser.parse_args()

    if not CC_SCHEMA_PATH.exists():
        print(f"ERR: missing CC schema file: {CC_SCHEMA_PATH}")
        return 1

    paths = resolve_runtime_paths(
        run_id=args.run_id.strip() or None,
        skill_key=args.skill_key,
        case_slug=sanitize_case_slug(args.case_slug or "validate-cc"),
        observer_id=args.observer_id.strip() or None,
        create=True,
    )

    try:
        update_manifest_phase(paths, "70", "active")

        contracts = get_default_contracts()
        w1, f1 = check_contract_definitions(contracts)
        w2, f2 = check_runtime_wiring(contracts, paths)
        warnings = w1 + w2
        fails = f1 + f2

        output_path = (
            Path(args.output).expanduser().resolve()
            if args.output
            else (Path(paths["governance_dir"]) / "cc_contract_validation.json")
        )

        status = "fail" if fails else ("warn" if warnings else "ok")
        payload = {
            "status": status,
            "version": CC_VERSION,
            "run_id": paths["run_id"],
            "cc_coupling_id": "CC-SET",
            "required_skill_ids": get_required_skill_ids(),
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
            print(f"output: {output_path}")

        if fails:
            update_manifest_phase(paths, "70", "failed")
            return 1

        update_manifest_phase(paths, "70", "completed")
        return 0
    except Exception:
        update_manifest_phase(paths, "70", "failed")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
