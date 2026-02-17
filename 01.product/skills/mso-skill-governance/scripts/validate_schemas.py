#!/usr/bin/env python3
"""Validate runtime pipeline artifacts against schema definitions."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[3]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills._shared.runtime_workspace import (  # noqa: E402
    resolve_runtime_paths,
    sanitize_case_slug,
    update_manifest_phase,
)

SCHEMA_TARGETS: Tuple[Dict[str, Any], ...] = (
    {
        "skill": "mso-workflow-topology-design",
        "name": "workflow_topology_spec",
        "schema": Path("skills/mso-workflow-topology-design/schemas/workflow_topology_spec.schema.json"),
        "kind": "json",
    },
    {
        "skill": "mso-mental-model-design",
        "name": "mental_model_bundle",
        "schema": Path("skills/mso-mental-model-design/schemas/mental_model_bundle.schema.json"),
        "kind": "json",
    },
    {
        "skill": "mso-execution-design",
        "name": "execution_plan",
        "schema": Path("skills/mso-execution-design/schemas/execution_plan.schema.json"),
        "kind": "json",
    },
    {
        "skill": "mso-task-context-management",
        "name": "ticket_frontmatter",
        "schema": Path("skills/mso-task-context-management/schemas/ticket.schema.json"),
        "kind": "ticket",
    },
    {
        "skill": "mso-runtime",
        "name": "run_manifest",
        "schema": Path("skills/mso-skill-governance/schemas/run_manifest.schema.json"),
        "kind": "json",
    },
    {
        "skill": "mso-runtime",
        "name": "manifest_index_record",
        "schema": Path("skills/mso-skill-governance/schemas/manifest_index_record.schema.json"),
        "kind": "jsonl_record",
    },
)

JSONSCHEMA_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}


def resolve_schema_path(raw_path: Path) -> Path:
    if raw_path.is_absolute():
        return raw_path
    return (ROOT / raw_path).resolve()


def ticket_frontmatter(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    payload: Dict[str, Any] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        payload[k.strip()] = _parse_frontmatter_scalar(v.strip())
    return payload


def _parse_frontmatter_scalar(raw: str) -> Any:
    value = raw.strip().strip("\"'")
    if not value:
        return ""
    if value.lower() == "null":
        return None
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"

    try:
        parsed = ast.literal_eval(value)
        if isinstance(parsed, (str, int, float, bool, list, dict, type(None))):
            return parsed
    except Exception:
        pass

    return value


def _latest_ticket_payload(tickets_dir: Path, ticket_id: str | None) -> Tuple[str, Any]:
    if ticket_id:
        exact = tickets_dir / ticket_id if ticket_id.endswith(".md") else tickets_dir / f"{ticket_id}.md"
        if exact.exists():
            payload = ticket_frontmatter(exact)
            if payload:
                return "ok", payload
            return "invalid", {"error": f"frontmatter parse error: {exact}"}

    tickets = sorted(tickets_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not tickets:
        return "missing", {"error": f"no tickets found under {tickets_dir}"}

    payload = ticket_frontmatter(tickets[0])
    if not payload:
        return "invalid", {"error": f"frontmatter parse error: {tickets[0]}"}
    return "ok", payload


def _latest_index_record(index_path: Path) -> Tuple[str, Any]:
    if not index_path.exists():
        return "missing", {"error": f"index missing: {index_path}"}

    lines = [line.strip() for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return "missing", {"error": f"index empty: {index_path}"}

    try:
        payload = json.loads(lines[-1])
    except Exception as exc:
        return "invalid", {"error": f"index parse error: {exc}"}

    if not isinstance(payload, dict):
        return "invalid", {"error": "index record is not an object"}
    return "ok", payload


def load_artifact(paths: Dict[str, Any], target_name: str, kind: str, ticket_id: str | None = None) -> Tuple[str, Any, Path]:
    if target_name == "workflow_topology_spec":
        artifact_path = Path(paths["topology_path"])
    elif target_name == "mental_model_bundle":
        artifact_path = Path(paths["bundle_path"])
    elif target_name == "execution_plan":
        artifact_path = Path(paths["execution_plan_path"])
    elif target_name == "ticket_frontmatter":
        tickets_dir = Path(paths["task_context_dir"]) / "tickets"
        state, payload = _latest_ticket_payload(tickets_dir, ticket_id)
        return state, payload, tickets_dir
    elif target_name == "run_manifest":
        artifact_path = Path(paths["manifest_path"])
    elif target_name == "manifest_index_record":
        index_path = Path(paths["manifest_index_path"])
        state, payload = _latest_index_record(index_path)
        return state, payload, index_path
    else:
        return "invalid", {"error": f"unknown target: {target_name}"}, Path(".")

    if kind != "json":
        return "invalid", {"error": f"unknown kind: {kind}"}, artifact_path

    if not artifact_path.exists():
        return "missing", {"error": f"artifact missing: {artifact_path}"}, artifact_path

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return "invalid", {"error": f"artifact parse error: {exc}"}, artifact_path

    return "ok", payload, artifact_path


def normalize_schema_types(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def fallback_type_check(value: Any, expected_types: List[str]) -> bool:
    if not expected_types:
        return True

    for expected_type in expected_types:
        if expected_type == "null" and value is None:
            return True
        if expected_type == "integer":
            if isinstance(value, int) and not isinstance(value, bool):
                return True
            continue
        expected = JSONSCHEMA_TYPES.get(expected_type)
        if expected is not None and isinstance(value, expected):
            return True
    return False


def fallback_checks(payload: Any, schema: Dict[str, Any]) -> List[str]:
    if not isinstance(payload, dict):
        return ["payload is not an object"]

    findings: List[str] = []
    required_fields = schema.get("required", [])
    if not isinstance(required_fields, list):
        required_fields = []

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}

    for name in required_fields:
        if name not in payload:
            findings.append(f"missing required field: {name}")
            continue

        value = payload[name]
        info = properties.get(name)
        if not isinstance(info, dict):
            continue
        expected_types = normalize_schema_types(info.get("type"))
        if expected_types and not fallback_type_check(value, expected_types):
            findings.append(f"{name}: expected {'|'.join(expected_types)}")

        enum_values = info.get("enum")
        if isinstance(enum_values, list) and value not in enum_values:
            findings.append(f"{name}: value not in enum set")

    return findings


def validate_with_jsonschema(payload: Any, schema: Dict[str, Any]) -> List[str]:
    try:
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(schema)
        errs = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
        return [str(err.message) for err in errs]
    except ModuleNotFoundError:
        raise
    except Exception as exc:
        return [f"jsonschema runtime error: {exc}"]


def validate_target(
    target: Dict[str, Any],
    paths: Dict[str, Any],
    ticket_id: str | None,
    strict: bool,
    use_fallback: bool,
) -> Dict[str, Any]:
    kind = target["kind"]
    schema_path = resolve_schema_path(target["schema"])

    status_record: Dict[str, Any] = {
        "skill": target["skill"],
        "artifact": "",
        "schema": str(schema_path),
        "status": "pass",
        "errors": [],
    }

    if not schema_path.exists():
        status_record["status"] = "fail"
        status_record["errors"].append(f"schema missing: {schema_path}")
        return status_record

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        status_record["status"] = "fail"
        status_record["errors"].append(f"schema parse failed: {exc}")
        return status_record

    state, payload, artifact_path = load_artifact(paths, target["name"], kind, ticket_id)
    status_record["artifact"] = str(artifact_path)

    if state == "missing":
        status_record["status"] = "fail"
        status_record["errors"].append(payload.get("error", "missing artifact"))
        return status_record
    if state == "invalid":
        status_record["status"] = "fail"
        status_record["errors"].append(payload.get("error", "invalid artifact"))
        return status_record

    try:
        errors = validate_with_jsonschema(payload, schema)
        if errors:
            status_record["status"] = "fail"
            status_record["errors"].extend([f"jsonschema: {err}" for err in errors])
            return status_record
        status_record["validation_mode"] = "jsonschema"
        return status_record
    except ModuleNotFoundError:
        if strict:
            status_record["status"] = "fail"
            status_record["errors"].append("jsonschema module missing in strict mode")
            return status_record
        if not use_fallback:
            status_record["status"] = "warn"
            status_record["errors"].append("jsonschema module missing; skipped validation")
            return status_record

        findings = fallback_checks(payload, schema)
        if findings:
            status_record["status"] = "fail"
            status_record["errors"].extend([f"fallback: {item}" for item in findings])
        else:
            status_record["validation_mode"] = "fallback-required-keys"
        return status_record


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate generated artifacts against schemas")
    parser.add_argument("--ticket", default=None, help="Specific ticket id or filename without extension")
    parser.add_argument("--strict", action="store_true", help="Require jsonschema module")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--run-id", default="", help="Run ID override")
    parser.add_argument("--skill-key", default="msogov", help="Skill key for run-id generation")
    parser.add_argument("--case-slug", default="", help="Case slug for run-id generation")
    parser.add_argument("--observer-id", default="", help="Observer ID override")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    paths = resolve_runtime_paths(
        run_id=args.run_id.strip() or None,
        skill_key=args.skill_key,
        case_slug=sanitize_case_slug(args.case_slug or "validate-schemas"),
        observer_id=args.observer_id.strip() or None,
        create=True,
    )

    try:
        update_manifest_phase(paths, "70", "active")
        try:
            import jsonschema  # type: ignore  # noqa: F401

            has_jsonschema = True
        except Exception:
            has_jsonschema = False

        results: List[Dict[str, Any]] = []
        warnings: List[str] = []
        failures: List[str] = []

        ticket_id = args.ticket.strip() if args.ticket else None

        for target in SCHEMA_TARGETS:
            result = validate_target(
                target=target,
                paths=paths,
                ticket_id=ticket_id,
                strict=args.strict,
                use_fallback=True,
            )
            results.append(result)
            if result["status"] == "fail":
                failures.extend(result["errors"])
            if result["status"] == "warn":
                warnings.extend(result["errors"])

        payload = {
            "status": "ok" if not failures else "fail",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "version": "0.0.2",
            "run_id": paths["run_id"],
            "jsonschema_available": has_jsonschema,
            "strict_mode": bool(args.strict),
            "results": results,
        }
        if warnings:
            payload["warnings"] = warnings

        out_path = Path(paths["governance_dir"]) / "schema_validation.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"jsonschema_available={has_jsonschema}")
            print(f"validation_status={payload['status']}")
            print(f"output={out_path}")
            if failures:
                print("failures:")
                for item in failures:
                    print(f"- {item}")
            if warnings:
                print("warnings:")
                for item in warnings:
                    print(f"- {item}")

        if payload["status"] == "ok":
            update_manifest_phase(paths, "70", "completed")
            return 0

        update_manifest_phase(paths, "70", "failed")
        return 1
    except Exception:
        update_manifest_phase(paths, "70", "failed")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
