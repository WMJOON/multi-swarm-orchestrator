#!/usr/bin/env python3
"""Contract tests for the MSO v0.2.2 repository skill layout."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / ".skill-modules"


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _schema_errors(schema: dict, instance: dict) -> list[str]:
    validator = Draft202012Validator(schema)
    return [f"{list(error.path)} {error.message}" for error in validator.iter_errors(instance)]


def test_required_skill_modules_exist():
    pack = _json(ROOT / "skills/mso-orchestration/references/pack_config.json")
    required = pack["required_skills"]

    assert "mso-execution-design" not in required
    assert "mso-workflow-repository-setup" in required
    assert "mso-harness-setup" in required

    for skill in required:
        skill_dir = MODULES / skill
        assert skill_dir.exists(), f"missing skill dir: {skill}"
        assert (skill_dir / "SKILL.md").exists(), f"missing SKILL.md: {skill}"


def test_deprecated_execution_design_alias_removed():
    assert not (MODULES / "mso-execution-design").exists()


def test_orchestration_routes_repository_setup_to_harness():
    orchestration = (ROOT / "skills/mso-orchestration/SKILL.md").read_text()

    for marker in [
        "mso-workflow-repository-setup",
        "mso-harness-setup",
        "[F-0]",
        "[F]",
        "workflow_repository.yaml",
        "harness_setup_input.yaml",
    ]:
        assert marker in orchestration


def test_runtime_harness_config_schema_accepts_example():
    skill = MODULES / "mso-harness-setup"
    schema = _json(skill / "schemas/runtime_harness_config.schema.json")
    sample = _yaml(skill / "configs/runtime-harness.example.yaml")

    assert _schema_errors(schema, sample) == []


def test_canonical_event_schema_accepts_contract_sample():
    skill = MODULES / "mso-harness-setup"
    schema = _json(skill / "schemas/canonical_event.schema.json")
    sample = {
        "event": {
            "id": "evt_contract_001",
            "timestamp": "2026-05-12T08:00:00Z",
            "lifecycle": {
                "phase": "execution.post",
                "state_transition": "tool_completed",
            },
        },
        "provider": {
            "name": "codex",
            "runtime_id": "contract-test",
            "native_event": "tool_result",
            "native_payload_ref": None,
            "native_payload": {"tool": "apply_patch"},
        },
        "capability": {
            "category": "filesystem.write",
            "operation": "edit",
            "target": "README.md",
            "risk_level": "medium",
        },
        "execution": {
            "tool_name": "apply_patch",
            "duration_ms": 10,
            "status": "success",
            "error_type": None,
            "error_message": None,
        },
        "semantic": {
            "entropy_delta": 0.01,
            "relevance_score": 0.95,
            "topology_stability": "stable",
            "loop_risk": 0.01,
            "boundary_status": "inside",
        },
        "governance": {
            "policy_decision": "allow",
            "requires_review": False,
            "escalation_triggered": False,
            "policy_ids": ["filesystem_write_medium_risk"],
            "review_reason": None,
        },
        "audit": {
            "run_id": "contract-run",
            "correlation_id": "corr-contract-001",
            "trace_id": None,
            "checkpoint_id": None,
        },
    }

    assert _schema_errors(schema, sample) == []


def test_workflow_repository_schema_accepts_contract_sample():
    skill = MODULES / "mso-workflow-repository-setup"
    schema = _json(skill / "schemas/workflow_repository.schema.json")
    sample = {
        "workflow": {
            "id": "wf-repo-ops",
            "objective": "repository operating contract",
            "scope": "reusable",
            "lifecycle_states": ["draft", "active", "archived"],
        },
        "scaffolding": {
            "directories": ["design", "memory", "harness", "governance", "optimizer", "audit"],
            "artifact_slots": ["workflow_repository.yaml", "harness_setup_input.yaml", "memory_layer.md"],
        },
        "memory": {
            "classes": ["runtime_state", "audit_memory", "retrieval_memory", "optimizer_memory"],
        },
        "governance": {
            "hooks": ["PreCompact", "Stop"],
            "state_triggers": ["audit_log_updated", "optimizer_threshold_crossed"],
        },
        "harness_input": {
            "required_inputs": ["workflow-design", "scaffolding-design"],
            "optional_inputs": ["mental-model"],
        },
    }

    assert _schema_errors(schema, sample) == []


def test_readme_states_v030_operating_target():
    readme = (ROOT / "README.md").read_text()

    assert "Repository Environment Operating" in readme
    assert "v0.3.0의 목표" in readme
    assert "Personal Memory" in readme
    assert "Repository Governance" in readme
    assert "Decision Control" in readme
    assert "user-decision" in readme
    assert "agent-decision" in readme
