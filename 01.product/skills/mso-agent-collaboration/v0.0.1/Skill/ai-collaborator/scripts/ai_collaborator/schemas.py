from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from jsonschema import Draft202012Validator  # type: ignore
except Exception:  # pragma: no cover
    Draft202012Validator = None


class SchemaValidationError(ValueError):
    pass


_SKILL_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_DIR = _SKILL_ROOT / "schemas"


def _load_schema(name: str) -> Dict[str, Any]:
    path = _SCHEMA_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def _fallback_required_check(payload: Any, required_fields: List[str]) -> List[str]:
    if not isinstance(payload, dict):
        return ["payload must be an object"]

    errors: List[str] = []
    for field in required_fields:
        if field not in payload:
            errors.append(f"missing required field: {field}")
    return errors


def _validate(schema_name: str, payload: Any) -> List[str]:
    if Draft202012Validator is None:
        if schema_name == "task-handoff.schema.json":
            return _fallback_required_check(
                payload,
                ["run_id", "task_id", "phase", "owner_agent", "role", "objective", "allowed_paths", "constraints"],
            )
        if schema_name == "output-report.schema.json":
            return _fallback_required_check(
                payload,
                ["run_id", "task_id", "status", "exit_code", "changed_files", "summary", "next_action"],
            )
        if schema_name == "bus-message.schema.json":
            return _fallback_required_check(
                payload,
                [
                    "id",
                    "trace_id",
                    "thread_id",
                    "from_agent",
                    "to_agent",
                    "type",
                    "payload",
                    "status",
                    "attempt",
                    "created_at",
                    "updated_at",
                ],
            )
        if schema_name == "run-manifest.schema.json":
            return _fallback_required_check(
                payload,
                ["run_id", "created_at", "status", "tasks", "config_hash", "system_rules_hash"],
            )
        return []

    schema = _load_schema(schema_name)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    return [e.message for e in errors]


def _apply_mode(errors: List[str], strict: bool, label: str) -> List[str]:
    if errors and strict:
        raise SchemaValidationError(f"{label} validation failed: " + "; ".join(errors))
    return errors


def validate_task_request_payload(payload: Any, strict: bool = False) -> List[str]:
    errors = _validate("task-handoff.schema.json", payload)
    return _apply_mode(errors, strict, "TASK_REQUEST payload")


def validate_task_result_payload(payload: Any, strict: bool = False) -> List[str]:
    errors = _validate("output-report.schema.json", payload)
    return _apply_mode(errors, strict, "TASK_RESULT payload")


def validate_bus_message(message: Any, strict: bool = False) -> List[str]:
    errors = _validate("bus-message.schema.json", message)
    return _apply_mode(errors, strict, "bus message")


def validate_payload_by_type(msg_type: str, payload: Any, strict: bool = False) -> List[str]:
    if msg_type == "TASK_REQUEST":
        return validate_task_request_payload(payload, strict=strict)
    if msg_type == "TASK_RESULT":
        return validate_task_result_payload(payload, strict=strict)
    return []


def validate_run_manifest(payload: Any, strict: bool = False) -> List[str]:
    errors = _validate("run-manifest.schema.json", payload)
    return _apply_mode(errors, strict, "run manifest")
