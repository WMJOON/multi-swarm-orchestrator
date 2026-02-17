#!/usr/bin/env python3
"""Run end-to-end repository checks for runtime workspace (v0.0.2)."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_SKILLS = [
    "mso-workflow-topology-design",
    "mso-mental-model-design",
    "mso-execution-design",
    "mso-task-context-management",
    "mso-agent-collaboration",
    "mso-agent-audit-log",
    "mso-observability",
    "mso-skill-governance",
]
PROHIBITED_TEXT = [
    r"04_Agentic_AI_OS",
    r"cortex-agora",
    r"@ref\(",
    r"@skill\(",
    r"SKILL\.meta\.yaml",
    r"AAOS_ROOT",
    r"scope:\s*swarm",
]


def run(cmd: List[str]) -> int:
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)
    return proc.returncode


def check_structure() -> List[str]:
    findings: List[str] = []
    for skill in EXPECTED_SKILLS:
        base = ROOT / "skills" / skill
        if not base.exists():
            findings.append(f"MISSING_SKILL_DIR {skill}")
            continue
        for rel in ["core.md", "modules", "references", "scripts"]:
            p = base / rel
            if not p.exists():
                if rel == "scripts" and skill in {
                    "mso-agent-audit-log",
                    "mso-observability",
                    "mso-skill-governance",
                    "mso-agent-collaboration",
                }:
                    findings.append(f"MISSING_REQUIRED:{skill}/{rel}")
                elif rel != "scripts":
                    findings.append(f"MISSING_REQUIRED:{skill}/{rel}")
    return findings


def check_prohibited_text() -> List[str]:
    findings: List[str] = []
    pattern = re.compile("|".join(PROHIBITED_TEXT))
    for path in ROOT.rglob("*.md"):
        if path.name.startswith("SPEC-CRITIQUE"):
            continue
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            findings.append(f"PROHIBITED_TEXT:{path}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run complete governance checks")
    parser.add_argument("--run-id", default="", help="Run ID override for runtime validators")
    parser.add_argument("--case-slug", default="validate-all", help="Case slug for runtime validators")
    parser.add_argument("--observer-id", default="", help="Observer ID override")
    args = parser.parse_args()

    failures: List[str] = []

    print("[validate_all] structure check")
    failures.extend(check_structure())

    print("[validate_all] dependency check")
    if run(["python3", "skills/mso-skill-governance/scripts/check_deps.py"]):
        failures.append("dependency-check-failed")

    print("[validate_all] schema/runtime validation")
    schema_cmd = [
        "python3",
        "skills/mso-skill-governance/scripts/validate_schemas.py",
        "--run-id",
        args.run_id,
        "--skill-key",
        "msogov",
        "--case-slug",
        args.case_slug,
    ]
    if args.observer_id:
        schema_cmd.extend(["--observer-id", args.observer_id])
    if run(schema_cmd):
        failures.append("schema-runtime-validation-failed")

    print("[validate_all] cc contract validation")
    cc_cmd = [
        "python3",
        "skills/mso-skill-governance/scripts/validate_cc_contracts.py",
        "--run-id",
        args.run_id,
        "--skill-key",
        "msogov",
        "--case-slug",
        args.case_slug,
    ]
    if args.observer_id:
        cc_cmd.extend(["--observer-id", args.observer_id])
    if run(cc_cmd):
        failures.append("cc-contract-validation-failed")

    print("[validate_all] governance validation")
    gov_cmd = [
        "python3",
        "skills/mso-skill-governance/scripts/validate_gov.py",
        "--run-id",
        args.run_id,
        "--skill-key",
        "msogov",
        "--case-slug",
        args.case_slug,
    ]
    if args.observer_id:
        gov_cmd.extend(["--observer-id", args.observer_id])
    if run(gov_cmd):
        failures.append("governance-validation-failed")

    print("[validate_all] banned text scan")
    failures.extend(check_prohibited_text())

    print(f"[validate_all] findings={len(failures)}")
    if failures:
        for finding in failures:
            print(f"- {finding}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
