from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_phases_to_workflows.py"
SPEC = importlib.util.spec_from_file_location("migrate_phases_to_workflows", SCRIPT)
migrate_phases_to_workflows = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(migrate_phases_to_workflows)


def test_migrate_phases_to_workflows_and_validation_to_eval():
    doc = {
        "phases": [
            {
                "id": "validation",
                "name": "Validation",
                "status": "active",
                "steps": [
                    {
                        "type": "validation",
                        "id": "v-001",
                        "label": "schema validation",
                        "status": "active",
                        "criteria": ["schema parses", "shape conforms"],
                        "target": "validation",
                        "target_artifact": "workflow.abox.ttl",
                        "oracle_type": "metric",
                        "branches": [{"on": "failed", "goto": "s-fix"}],
                    }
                ],
            }
        ]
    }

    migrated, changed = migrate_phases_to_workflows.migrate_doc(doc)

    assert changed
    assert "phases" not in migrated
    node = migrated["workflows"][0]["steps"][0]
    assert node["type"] == "eval"
    assert node["oracle_type"] == "metric"
    assert node["criteria"] == ["schema parses", "shape conforms"]
    assert node["target"] == "validation"
    assert node["target_artifact"] == "workflow.abox.ttl"
    assert {branch["on"] for branch in node["branches"]} == {"failed", "passed"}


def test_migrate_nested_workflow_validation_to_eval():
    doc = {
        "workflows": [
            {
                "id": "outer",
                "steps": [
                    {
                        "type": "group",
                        "id": "g-001",
                        "label": "group",
                        "status": "active",
                        "steps": [
                            {
                                "type": "validation",
                                "id": "v-002",
                                "label": "completeness",
                                "status": "pending",
                                "pass_criteria": ["package complete"],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    migrated, changed = migrate_phases_to_workflows.migrate_doc(doc)

    assert changed
    node = migrated["workflows"][0]["steps"][0]["steps"][0]
    assert node["type"] == "eval"
    assert node["oracle_type"] == "metric"
    assert node["criteria"] == ["package complete"]
    assert {branch["on"] for branch in node["branches"]} == {"failed", "passed"}
