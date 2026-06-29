from pathlib import Path
import subprocess
import sys

import yaml


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_workflows_to_ttl.py"


def test_migrate_workflows_to_ttl_writes_and_checks(tmp_path):
    workflow_dir = tmp_path / "workflow"
    workflow_dir.mkdir()
    wf = workflow_dir / "01.consultdata-workflow-00.yaml"
    wf.write_text(
        yaml.safe_dump(
            {
                "phases": [
                    {
                        "id": "p",
                        "name": "Plan",
                        "status": "active",
                        "steps": [
                            {
                                "type": "step",
                                "id": "p-s-01",
                                "label": "계획",
                                "instruction": "작업 계획을 작성하라",
                                "status": "active",
                            }
                        ],
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    subprocess.run([sys.executable, str(SCRIPT), str(workflow_dir)], check=True)
    ttl = workflow_dir / "01.consultdata-workflow-00.abox.ttl"
    assert ttl.exists()
    assert not (workflow_dir / "01.abox.ttl").exists()
    text = ttl.read_text(encoding="utf-8")
    assert "wf:Step" in text
    assert "p-s-01" in text

    subprocess.run([sys.executable, str(SCRIPT), str(workflow_dir), "--check"], check=True)
