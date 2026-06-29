#!/usr/bin/env python3
"""Contract tests for the MSO v0.3.x repository skill layout.

v0.2.2 의 ``.skill-modules/`` 설치 사본 + ``pack_config.json`` 정본 기반 레이아웃은
v0.3.0 "5-skill pack 전면 교체"에서 폐기됐다. 본 테스트는 현재 8-스킬 구조
(Design/Ops/Infra/Optimizer 6종 + Runtime/NLU 후단 2종)의 계약을 검증한다.

검증 대상은 "선언(manifest/SKILL.md)이 파일시스템 실재와 일치하는가"이지,
파일 존재의 동어반복이 아니다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

# v0.3.0 코어 5종 (Design/Ops/Infra)
CORE_SKILLS = {
    "mso-orchestration",
    "mso-repository-setup",
    "mso-scaffold-design",
    "mso-workflow-design",
    "mso-workflow-optimizer",
    "mso-work-memory",
}

# NLU/Runtime 레이어 (§11 재편 후) — manifest.json 보유, orchestration 라우팅 대상
#   mso-intent-analytics = registry SoT + 뒷단 dispatch(slot/resolve/validate/turn).
#   앞단(utterance→intent)은 UUG(uug-grounding)로 흡수 — 이 repo 밖.
RUNTIME_SKILLS = {
    "mso-intent-analytics",
}

# present 하지만 orchestration 라우팅에서 de-route 됨 (§11.1: 분석 메서드 UUG 흡수 대기).
# 흡수 완료 후 제거 예정 — 그때까지 capability 보존 위해 잔존.
PENDING_ABSORB_SKILLS = {
    "mso-conversation-analytics",
}

ALL_SKILLS = CORE_SKILLS | RUNTIME_SKILLS | PENDING_ABSORB_SKILLS

# 폐기된 스킬 — 되살아나면 구조 회귀
#   v0.2.2: execution-design/harness-setup/workflow-repository-setup
#   §11 재편: utterance-grounding(해체) / intent-registry(→intent-analytics 개명)
DEPRECATED_SKILLS = {
    "mso-execution-design",
    "mso-harness-setup",
    "mso-workflow-repository-setup",
    "mso-utterance-grounding",
    "mso-intent-registry",
}

# orchestration SKILL.md 가 라우팅을 *예정* 으로만 언급하는 미래 스킬
# (디렉토리 미실재가 정상 — depends_on 무결성 검사에서 제외)
PLANNED_SKILLS = {"mso-discussion-coworker"}


def _manifest(skill: str) -> dict:
    return json.loads((SKILLS / skill / "manifest.json").read_text())


def test_all_skills_present_with_skill_md():
    """8-스킬 디렉토리 + SKILL.md 가 모두 존재한다."""
    for skill in sorted(ALL_SKILLS):
        skill_dir = SKILLS / skill
        assert skill_dir.is_dir(), f"missing skill dir: {skill}"
        assert (skill_dir / "SKILL.md").exists(), f"missing SKILL.md: {skill}"


def test_deprecated_v022_layout_removed():
    """v0.2.2 의 .skill-modules / pack_config / 폐기 스킬이 되살아나지 않았다."""
    assert not (ROOT / ".skill-modules").exists(), ".skill-modules resurfaced"
    assert not (
        SKILLS / "mso-orchestration" / "references" / "pack_config.json"
    ).exists(), "pack_config.json resurfaced"
    for skill in sorted(DEPRECATED_SKILLS):
        assert not (SKILLS / skill).exists(), f"deprecated skill resurfaced: {skill}"


def test_runtime_manifest_name_matches_directory():
    """manifest.json(선언)의 name 이 디렉토리(실재)와 일치한다."""
    for skill in sorted(RUNTIME_SKILLS | PENDING_ABSORB_SKILLS):
        manifest_path = SKILLS / skill / "manifest.json"
        assert manifest_path.exists(), f"missing manifest.json: {skill}"
        assert _manifest(skill)["name"] == skill, (
            f"{skill}: manifest name mismatch ({_manifest(skill)['name']!r})"
        )


def test_runtime_manifest_depends_on_resolve():
    """manifest 가 선언한 mso-* depends_on 이 실재 스킬을 가리킨다 (dangling 방지).
    utterance-grounding 해체 후 depends_on 에 그 이름이 남으면 dangling → 실패."""
    for skill in sorted(RUNTIME_SKILLS | PENDING_ABSORB_SKILLS):
        for dep in _manifest(skill).get("depends_on") or []:
            if not (isinstance(dep, str) and dep.startswith("mso-")):
                continue
            if dep in PLANNED_SKILLS:
                continue
            assert (SKILLS / dep).is_dir(), f"{skill} depends_on missing skill: {dep}"


def test_orchestration_routes_runtime_layer():
    """orchestration 이 NLU/Runtime(intent-analytics)을 라우팅 언급한다."""
    text = (SKILLS / "mso-orchestration" / "SKILL.md").read_text()
    for skill in sorted(RUNTIME_SKILLS):
        assert skill in text, f"orchestration no longer routes: {skill}"


def test_dissolved_utterance_grounding_not_routed():
    """§11: utterance-grounding 해체 회귀 방지 — orchestration 이 더는 라우팅하지 않는다."""
    text = (SKILLS / "mso-orchestration" / "SKILL.md").read_text()
    assert "mso-utterance-grounding" not in text, "해체된 utterance-grounding 라우팅 잔존"


def test_readme_reflects_current_version_and_structure():
    """README 헤더 버전과 핵심 구조 어휘가 현재 패치와 일치한다."""
    readme = (ROOT / "README.md").read_text()
    assert "MSO) v0.5.1" in readme, "README header is not v0.5.1"
    assert "Repository Execution System" in readme
    assert "Core Philosophy" in readme
    assert "Artifact Supply Chain" in readme
    assert "Work Memory" in readme
    assert "Skills" in readme
    assert "mso-graph-observability" in readme
    assert "docs/changelog.md" in readme


def test_skill_versions_are_current_patch():
    """정식 repository 스킬 메타가 현재 패치 버전으로 정렬되어 있다."""
    for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
        text = skill_md.read_text()
        assert 'version: "0.5.1"' in text, f"{skill_md.parent.name} version is not 0.5.1"


def test_work_memory_decision_governance_schema_contract():
    """v0.3.6 PLAN: AR 타입과 UD boundary/criterion 이 schema SSOT 에 존재한다."""
    schema = (SKILLS / "mso-work-memory" / "references" / "schema.yaml").read_text()
    assert "alternatives-record: {prefix: AR, dir: track-record/alternatives-record}" in schema
    assert "provided_by" in schema
    assert "options" in schema
    assert "recommended" in schema
    assert "boundary" in schema
    assert "criterion" in schema
    assert "supersedes" in schema
    assert "refines" in schema


def test_repository_setup_bootstraps_alternatives_record_dir(tmp_path):
    """init.py 가 새 프로젝트에 AR 디렉토리와 schema-driven AR 타입을 부트스트랩한다."""
    init_py = SKILLS / "mso-repository-setup" / "scripts" / "init.py"
    target = tmp_path / "project"
    subprocess.run(
        [sys.executable, str(init_py), "--target", str(target), "--name", "T", "--id", "t"],
        check=True,
        capture_output=True,
        text=True,
    )
    ar_dir = target / "agent-context" / "work-memory" / "track-record" / "alternatives-record"
    assert ar_dir.is_dir()
    schema = (target / "agent-context" / "work-memory" / "schema.yaml").read_text()
    assert "alternatives-record" in schema
    assert "boundary" in schema


def test_scaffold_design_declares_directory_refinement_guardrail():
    """디렉토리 정리는 self-workflow 가 아니라 scaffold skill + hook guardrail 이 담당한다."""
    skill_md = (SKILLS / "mso-scaffold-design" / "SKILL.md").read_text()
    hook_path = SKILLS / "mso-scaffold-design" / "hooks" / "scaffold-check.sh"
    assert "Directory Refinement Protocol" in skill_md
    assert "scaffold-check.sh" in skill_md
    assert hook_path.exists()
    assert os.access(hook_path, os.X_OK)


def test_repository_setup_hook_installs_scaffold_guardrail_for_codex(tmp_path):
    """--hook --provider codex 가 scaffold-check + sf_node + schema 를 self-contained 로 복사한다."""
    init_py = SKILLS / "mso-repository-setup" / "scripts" / "init.py"
    target = tmp_path / "project"
    subprocess.run(
        [sys.executable, str(init_py), "--target", str(target), "--name", "T", "--id", "t"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, str(init_py), "--hook", str(target), "--provider", "codex"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (target / ".codex" / "scripts" / "scaffold-check.sh").exists()
    assert (target / ".codex" / "scripts" / "sf_node.py").exists()
    assert (target / ".codex" / "references" / "schemas" / "project.schema.yaml").exists()
    config = (target / ".codex" / "config.toml").read_text()
    assert "scaffold-check.sh" in config
    assert "sf_node.py" in config


def test_scaffold_check_strict_detects_index_inventory_mismatch(tmp_path):
    """strict 모드에서는 index 에 없는 directory 가 생기면 hook 이 실패한다."""
    init_py = SKILLS / "mso-repository-setup" / "scripts" / "init.py"
    target = tmp_path / "project"
    subprocess.run(
        [sys.executable, str(init_py), "--target", str(target), "--name", "T", "--id", "t"],
        check=True,
        capture_output=True,
        text=True,
    )
    (target / "unexpected-dir").mkdir()
    hook_path = SKILLS / "mso-scaffold-design" / "hooks" / "scaffold-check.sh"
    sf_node = SKILLS / "mso-scaffold-design" / "scripts" / "sf_node.py"
    env = os.environ.copy()
    env.update(
        {
            "CODEX_PROJECT_DIR": str(target),
            "MSO_SCAFFOLD_TOOL": str(sf_node),
            "MSO_SCAFFOLD_CHECK_STRICT": "1",
        }
    )
    result = subprocess.run(
        ["bash", str(hook_path)],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "[scaffold-check]" in output
    assert "unexpected-dir" in output
