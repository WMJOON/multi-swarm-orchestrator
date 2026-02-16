#!/usr/bin/env python3
"""Validate skill governance for v0.0.1 skill pack."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[3]
TEST_ARTIFACTS = (ROOT / "../../02.test/v0.0.1").resolve()

DEFAULT_MAX_SKILLS = 8
REQUIRED_SKILLS = [
    "mso-workflow-topology-design",
    "mso-mental-model-design",
    "mso-execution-design",
    "mso-task-context-management",
    "mso-agent-collaboration",
    "mso-agent-audit-log",
    "mso-observability",
    "mso-skill-governance",
]
REQUIRED_CONTRACT_FIELDS = [
    "id",
    "producer",
    "consumer",
    "required_input_keys",
    "required_output_keys",
    "compatibility_policy",
    "status",
]


def read_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    if yaml is None:
        return {}

    data = yaml.safe_load(raw)
    return data if isinstance(data, dict) else {}


def collect_skills(skills_root: Path) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    if not skills_root.exists():
        return {}

    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        out[skill_dir.name] = skill_dir
    return out


def has_aaos_string(path: Path) -> bool:
    txt = path.read_text(encoding="utf-8", errors="ignore")
    needles = [
        "04_Agentic_AI_OS",
        "04_AgentsTools/02_ai-collaborator",
        "cortex-agora",
        "AAOS_ROOT",
        "SKILL.meta.yaml",
    ]
    return any(n in txt for n in needles)


def validate_skill_structure(skills: Dict[str, Path], skills_root: Path) -> tuple[List[dict], List[dict]]:
    warnings: List[dict] = []
    errors: List[dict] = []

    for sid in REQUIRED_SKILLS:
        path = skills.get(sid)
        if path is None:
            errors.append({
                "id": sid,
                "severity": "fail",
                "finding": f"missing required skill folder: {sid}",
                "evidence": f"{skills_root}",
            })
            continue

        checks = {
            "core": path / "core.md",
            "modules": path / "modules" / "modules_index.md",
            "references": path / "references",
            "scripts": path / "scripts",
        }
        if not checks["core"].exists():
            errors.append({
                "id": sid,
                "severity": "fail",
                "finding": "missing core.md",
                "evidence": str(checks["core"]),
            })
        if not checks["modules"].exists():
            errors.append({
                "id": sid,
                "severity": "fail",
                "finding": "missing modules/modules_index.md",
                "evidence": str(checks["modules"]),
            })
        for key in ("references", "scripts"):
            if not checks[key].exists():
                errors.append({
                    "id": sid,
                    "severity": "warn",
                    "finding": f"missing directory: {key}",
                    "evidence": str(checks[key]),
                })

        for file in [path / "core.md", path / "SKILL.md", checks["modules"], path / "references"]:
            if file.exists() and file.is_file() and has_aaos_string(file):
                errors.append({
                    "id": sid,
                    "severity": "warn",
                    "finding": "legacy reference detected",
                    "evidence": str(file),
                })

    if len(skills) > DEFAULT_MAX_SKILLS:
        warnings.append({
            "id": "skill-overload",
            "severity": "warn",
            "finding": f"skill count={len(skills)} exceeds threshold={DEFAULT_MAX_SKILLS}",
            "evidence": str(skills_root),
        })

    return warnings, errors


def validate_contracts(config_path: Path) -> tuple[List[dict], List[dict]]:
    cfg = read_config(config_path)
    contracts = cfg.get("cc_contracts", {}).get("contracts") if isinstance(cfg.get("cc_contracts"), dict) else None
    if not contracts:
        return [], [{"id": "cc-contracts", "severity": "fail", "finding": "cc contracts not found in config.yaml", "evidence": "cc_contracts"}]

    if not isinstance(contracts, list):
        return [], [{"id": "cc-contracts", "severity": "fail", "finding": "cc contracts malformed", "evidence": str(type(contracts))}]

    warnings: List[dict] = []
    errors: List[dict] = []
    required_ids = {"CC-01", "CC-02", "CC-03", "CC-04", "CC-05"}
    seen = set()

    for contract in contracts:
        if not isinstance(contract, dict):
            errors.append({
                "id": "cc-contracts",
                "severity": "fail",
                "finding": "contract entry not object",
                "evidence": str(contract),
            })
            continue

        cid = str(contract.get("id", "")).strip()
        seen.add(cid)
        for field in REQUIRED_CONTRACT_FIELDS:
            if field not in contract:
                errors.append({
                    "id": cid or "(unknown)",
                    "severity": "fail",
                    "finding": f"missing required contract field: {field}",
                    "evidence": str(contract),
                })

        if contract.get("status") not in {"ok", "warn", "fail"}:
            warnings.append({
                "id": cid,
                "severity": "warn",
                "finding": "unexpected contract status",
                "evidence": str(contract.get("status")),
            })

    missing = sorted(required_ids - seen)
    for missing_id in missing:
        errors.append({
            "id": missing_id,
            "severity": "fail",
            "finding": "required CC contract missing",
            "evidence": f"expected in config.yaml:cc_contracts.contracts[{missing_id}]",
        })

    return warnings, errors


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


def write_report(warnings: List[dict], errors: List[dict], skill_pack_version: str, out_path: Path) -> None:
    status = "fail" if any(f["severity"] == "fail" for f in [*warnings, *errors]) else "ok"
    lines = ["# Governance Report", "", f"- generated_at: `{datetime.utcnow().isoformat()}`", f"- skill_pack_version: `{skill_pack_version}`", f"- status: `{status}`", "", "## Findings"]
    if not warnings and not errors:
        lines.append("- none")
    else:
        for item in warnings + errors:
            lines.append(f"- [{item['severity'].upper()}] {item['id']}: {item['finding']} (evidence: `{item['evidence']}`)")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate v0.0.1 skill governance")
    parser.add_argument("--pack-root", default=str(ROOT), help="v0.0.1 root path")
    parser.add_argument("--report-dir", default=None, help="Governance report output directory")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    args = parser.parse_args()

    pack_root = Path(args.pack_root).expanduser().resolve()
    skills_dir = pack_root / "skills"
    config_path = pack_root / "config.yaml"
    report_dir = pack_root / "references"

    if not skills_dir.is_dir():
        print(f"ERROR: skills directory not found: {skills_dir}")
        return 2

    if not config_path.is_file():
        print(f"ERROR: config file not found: {config_path}")
        return 2

    cfg = read_config(config_path)
    if args.report_dir:
        report_dir = Path(args.report_dir).expanduser().resolve()
    else:
        report_root = resolve_path(cfg, str(TEST_ARTIFACTS / "observations"), "pipeline", "default_observation_dir")
        report_dir = report_root.parent / "references"

    if not report_dir.exists():
        report_dir.mkdir(parents=True, exist_ok=True)

    skills = collect_skills(skills_dir)
    w1, e1 = validate_skill_structure(skills, skills_dir)
    w2, e2 = validate_contracts(config_path)

    warnings = w1 + w2
    errors = e1 + e2
    report_path = report_dir / "governance_check_report.md"
    write_report(warnings, errors, "v0.0.1", report_path)

    if args.json:
        payload = {
            "status": "fail" if any(f["severity"] == "fail" for f in errors) else "warn" if warnings else "ok",
            "skill_pack_version": "v0.0.1",
            "required_skill_ids": REQUIRED_SKILLS,
            "cc_coupling_id": "CC-00",
            "schema_version": "1.0.0",
            "findings": warnings + errors,
            "report_uri": str(report_path),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    if errors:
        return 1
    if warnings:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
