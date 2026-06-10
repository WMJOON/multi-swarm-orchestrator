#!/usr/bin/env python3
"""Contract tests for the MSO v0.3.x repository skill layout.

v0.2.2 의 ``.skill-modules/`` 설치 사본 + ``pack_config.json`` 정본 기반 레이아웃은
v0.3.0 "5-skill pack 전면 교체"에서 폐기됐다. 본 테스트는 현재 8-스킬 구조
(Design/Ops/Infra 5종 + v0.3.1 Runtime/NLU 3종)의 계약을 검증한다.

검증 대상은 "선언(manifest/SKILL.md)이 파일시스템 실재와 일치하는가"이지,
파일 존재의 동어반복이 아니다.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

# v0.3.0 코어 5종 (Design/Ops/Infra)
CORE_SKILLS = {
    "mso-orchestration",
    "mso-repository-setup",
    "mso-scaffold-design",
    "mso-workflow-design",
    "mso-work-memory",
}

# v0.3.1 Utterance Grounding Layer (Runtime/NLU) — manifest.json 보유
RUNTIME_SKILLS = {
    "mso-utterance-grounding",
    "mso-intent-registry",
    "mso-conversation-analytics",
}

ALL_SKILLS = CORE_SKILLS | RUNTIME_SKILLS

# v0.2.2 에서 폐기된 스킬 — 되살아나면 구조 회귀
DEPRECATED_SKILLS = {
    "mso-execution-design",
    "mso-harness-setup",
    "mso-workflow-repository-setup",
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
    for skill in sorted(RUNTIME_SKILLS):
        manifest_path = SKILLS / skill / "manifest.json"
        assert manifest_path.exists(), f"missing manifest.json: {skill}"
        assert _manifest(skill)["name"] == skill, (
            f"{skill}: manifest name mismatch ({_manifest(skill)['name']!r})"
        )


def test_runtime_manifest_depends_on_resolve():
    """manifest 가 선언한 mso-* depends_on 이 실재 스킬을 가리킨다 (dangling 방지)."""
    for skill in sorted(RUNTIME_SKILLS):
        for dep in _manifest(skill).get("depends_on") or []:
            if not (isinstance(dep, str) and dep.startswith("mso-")):
                continue
            if dep in PLANNED_SKILLS:
                continue
            assert (SKILLS / dep).is_dir(), f"{skill} depends_on missing skill: {dep}"


def test_orchestration_routes_runtime_layer():
    """v0.3.1 통합 회귀 방지: orchestration 이 Runtime/NLU 3종을 라우팅 언급한다."""
    text = (SKILLS / "mso-orchestration" / "SKILL.md").read_text()
    for skill in sorted(RUNTIME_SKILLS):
        assert skill in text, f"orchestration no longer routes: {skill}"


def test_readme_reflects_current_version_and_structure():
    """README 헤더 버전과 핵심 구조 어휘가 v0.3.2 와 일치한다."""
    readme = (ROOT / "README.md").read_text()
    assert "MSO) v0.3.2" in readme, "README header is not v0.3.2"
    assert "스킬 구성" in readme
    assert "Work-Memory" in readme
