#!/usr/bin/env python3
"""Run end-to-end repository checks for multi-swarm-orchestrator v0.0.1."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

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
    r"\bcontext_id\b",
    r"AAOS_ROOT",
    r"scope:\s*swarm",
]


def run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)
    return proc.returncode


def check_structure() -> list[str]:
    findings = []
    for skill in EXPECTED_SKILLS:
        base = ROOT / "skills" / skill
        if not base.exists():
            findings.append(f"MISSING_SKILL_DIR {skill}")
            continue
        for rel in ["core.md", "modules", "references", "scripts"]:
            p = base / rel
            if not p.exists():
                if rel == "scripts" and skill in {"mso-agent-audit-log", "mso-observability", "mso-skill-governance", "mso-agent-collaboration"}:
                    findings.append(f"MISSING_REQUIRED:{skill}/{rel}")
                elif rel != "scripts":
                    findings.append(f"MISSING_REQUIRED:{skill}/{rel}")
    return findings


def check_prohibited_text() -> list[str]:
    findings = []
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
    failures = []

    print("[validate_all] structure check")
    failures.extend(check_structure())

    print("[validate_all] dependency check")
    if run(["python3", "skills/mso-skill-governance/scripts/check_deps.py", "--config", "config.yaml"]):
        failures.append("dependency-check-failed")

    print("[validate_all] cc contract validation")
    if run(["python3", "skills/mso-skill-governance/scripts/validate_cc_contracts.py", "--json"]):
        failures.append("cc-contract-validation-failed")

    print("[validate_all] governance validation")
    if run(["python3", "skills/mso-skill-governance/scripts/validate_gov.py", "--json"]):
        failures.append("governance-validation-failed")

    print("[validate_all] banned text scan")
    banned = check_prohibited_text()
    failures.extend(banned)

    print(f"[validate_all] findings={len(failures)}")
    if failures:
        for f in failures:
            print(f"- {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
