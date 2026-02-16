#!/usr/bin/env python3
"""Validate v0.0.1 pipeline artifacts against schema definitions."""

from __future__ import annotations

import argparse
import ast
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config.yaml"
DEFAULT_WORKFLOW_OUTPUT_DIR = (ROOT / "../../02.test/v0.0.1/outputs").resolve()
DEFAULT_TASK_DIR = (ROOT / "../../02.test/v0.0.1/task-context").resolve()

SCHEMA_TARGETS = (
    {
        "skill": "mso-workflow-topology-design",
        "name": "workflow_topology_spec",
        "artifact": Path("workflow_topology_spec.json"),
        "schema": Path("skills/mso-workflow-topology-design/schemas/workflow_topology_spec.schema.json"),
        "kind": "json",
    },
    {
        "skill": "mso-mental-model-design",
        "name": "mental_model_bundle",
        "artifact": Path("mental_model_bundle.json"),
        "schema": Path("skills/mso-mental-model-design/schemas/mental_model_bundle.schema.json"),
        "kind": "json",
    },
    {
        "skill": "mso-execution-design",
        "name": "execution_plan",
        "artifact": Path("execution_plan.json"),
        "schema": Path("skills/mso-execution-design/schemas/execution_plan.schema.json"),
        "kind": "json",
    },
    {
        "skill": "mso-task-context-management",
        "name": "ticket_frontmatter",
        "artifact": Path("tickets"),
        "schema": Path("skills/mso-task-context-management/schemas/ticket.schema.json"),
        "kind": "ticket",
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

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    if yaml is None:
        return {}

    try:
        parsed = yaml.safe_load(raw)
    except Exception:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def resolve_path(cfg: Dict[str, Any], fallback: str, *keys: str) -> Path:
    base: Any = cfg
    for key in keys:
        if not isinstance(base, dict):
            base = {}
        base = base.get(key)

    raw = str(base) if base is not None else fallback
    path = Path(raw)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def resolve_output_dir(cfg: Dict[str, Any], cli: str | None = None) -> Path:
    if cli:
        return Path(cli).expanduser().resolve()
    return resolve_path(cfg, str(DEFAULT_WORKFLOW_OUTPUT_DIR), "pipeline", "default_workflow_output_dir")


def resolve_task_dir(cfg: Dict[str, Any], cli: str | None = None) -> Path:
    if cli:
        return Path(cli).expanduser().resolve()
    return resolve_path(cfg, str(DEFAULT_TASK_DIR), "pipeline", "default_task_dir")


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
        key = k.strip()
        value = v.strip()
        parsed = _parse_frontmatter_scalar(value)
        payload[key] = parsed
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


def load_artifact(path: Path, kind: str, ticket_id: str | None = None) -> tuple[str, Any]:
    if kind == "ticket":
        if ticket_id:
            exact = path / ticket_id if ticket_id.endswith(".md") else path / f"{ticket_id}.md"
            if exact.exists():
                payload = ticket_frontmatter(exact)
                if not payload:
                    return "invalid", {"error": f"frontmatter parse error: {exact}"}
                return "ok", payload

        tickets = sorted(path.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not tickets:
            return "missing", {"error": f"no tickets found under {path}"}
        payload = ticket_frontmatter(tickets[0])
        if not payload:
            return "invalid", {"error": f"frontmatter parse error: {tickets[0]}"}
        return "ok", payload

    if kind != "json":
        return "invalid", {"error": f"unknown kind: {kind}"}

    if not path.exists():
        return "missing", {"error": f"artifact missing: {path}"}

    try:
        return "ok", json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return "invalid", {"error": f"artifact parse error: {exc}"}


def normalize_schema_type(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            if item != "null":
                return normalize_schema_type(item)
        return "null"
    if isinstance(value, str):
        return value
    return None


def fallback_type_check(value: Any, expected_type: str | None) -> bool:
    if not expected_type or expected_type == "null":
        return True

    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)

    expected = JSONSCHEMA_TYPES.get(expected_type)
    return isinstance(value, expected) if expected is not None else True


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
        expected_type = normalize_schema_type(info.get("type"))
        if expected_type and not fallback_type_check(value, expected_type):
            findings.append(f"{name}: expected {expected_type}")
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
    cfg: Dict[str, Any],
    workflow_output_dir: str | None,
    task_dir: str | None,
    ticket_id: str | None,
    strict: bool,
    use_fallback: bool,
) -> Dict[str, Any]:
    kind = target["kind"]
    output_root = resolve_output_dir(cfg, workflow_output_dir)
    task_root = resolve_task_dir(cfg, task_dir)

    artifact_path = output_root / target["artifact"] if kind == "json" else task_root / target["artifact"]
    schema_path = resolve_schema_path(target["schema"])

    status_record: Dict[str, Any] = {
        "skill": target["skill"],
        "artifact": str(artifact_path),
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

    state, payload = load_artifact(artifact_path, kind, ticket_id)
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
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Path to orchestrator config")
    parser.add_argument("--workflow-output-dir", default=None, help="Override workflow output directory")
    parser.add_argument("--task-dir", default=None, help="Override task-context root directory")
    parser.add_argument("--ticket", default=None, help="Specific ticket id or filename without extension")
    parser.add_argument("--strict", action="store_true", help="Require jsonschema module")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    cfg = load_config(Path(args.config).expanduser().resolve())
    try:
        import jsonschema  # type: ignore

        has_jsonschema = True
    except Exception:
        has_jsonschema = False

    results: List[Dict[str, Any]] = []
    warnings: List[str] = []
    failures: List[str] = []

    workflow_output = args.workflow_output_dir
    task_root = args.task_dir
    ticket_id = args.ticket.strip() if args.ticket else None

    for target in SCHEMA_TARGETS:
        result = validate_target(
            target=target,
            cfg=cfg,
            workflow_output_dir=workflow_output,
            task_dir=task_root,
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
        "version": "0.0.1",
        "jsonschema_available": has_jsonschema,
        "strict_mode": bool(args.strict),
        "results": results,
    }

    if warnings:
        payload["warnings"] = warnings

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"jsonschema_available={has_jsonschema}")
        print(f"validation_status={payload['status']}")
        if failures:
            print("failures:")
            for item in failures:
                print(f"- {item}")
        if warnings:
            print("warnings:")
            for item in warnings:
                print(f"- {item}")

    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
