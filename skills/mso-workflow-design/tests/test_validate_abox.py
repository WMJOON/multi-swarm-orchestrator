"""validate_abox.py — TTL ABox(SSOT) 직접 검증 진입점 테스트."""

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
sys.path.insert(0, str(SCRIPTS))

import validate_abox  # noqa: E402

PREFIX = "@prefix wf: <https://mso.dev/ontology/workflow#> .\n"


def write_abox(tmp_path: Path, body: str, name: str = "workflow-t.abox.ttl") -> Path:
    path = tmp_path / name
    path.write_text(PREFIX + body, encoding="utf-8")
    return path


def test_bundled_example_abox_passes():
    res = validate_abox.validate_abox([ASSETS / "examples"])
    assert res["ok"], res
    assert res["shacl_conforms"]
    assert not res["uncontrolled_loops"]
    assert not res["directory_issues"]


def test_decision_missing_subject_fails_shacl(tmp_path):
    body = """
<https://mso.dev/ontology/workflow#node/t/bad-d-001> a wf:Decision, wf:Node ;
    wf:label "불완전 결정" .
"""
    res = validate_abox.validate_abox([write_abox(tmp_path, body)])
    assert not res["ok"]
    assert not res["shacl_conforms"]
    assert "decisionSubject" in res["shacl_report"]


def test_directory_missing_role_reported(tmp_path):
    body = """
<https://mso.dev/ontology/workflow#node/t/t-s-001> a wf:Step, wf:Node, wf:Task ;
    wf:label "산출" ;
    wf:instruction "산출물을 만든다" ;
    wf:status "active" ;
    wf:directory <https://mso.dev/ontology/workflow#node/t/t-s-001_dir> .
<https://mso.dev/ontology/workflow#node/t/t-s-001_dir> wf:dirPath "out/" .
"""
    res = validate_abox.validate_abox([write_abox(tmp_path, body)])
    assert not res["ok"]
    assert any("wf:dirRole" in issue for issue in res["directory_issues"])


def test_step_multi_outgoing_is_warning_not_error(tmp_path):
    body = """
<https://mso.dev/ontology/workflow#node/t/t-s-001> a wf:Step, wf:Node, wf:Task ;
    wf:label "분기 냄새" ;
    wf:instruction "다음으로 진행" ;
    wf:status "active" ;
    wf:next <https://mso.dev/ontology/workflow#node/t/t-s-002>,
        <https://mso.dev/ontology/workflow#node/t/t-s-003> .
<https://mso.dev/ontology/workflow#node/t/t-s-002> a wf:Step, wf:Node, wf:Task ;
    wf:label "A" ; wf:instruction "A" ; wf:status "pending" .
<https://mso.dev/ontology/workflow#node/t/t-s-003> a wf:Step, wf:Node, wf:Task ;
    wf:label "B" ; wf:instruction "B" ; wf:status "pending" .
"""
    res = validate_abox.validate_abox([write_abox(tmp_path, body)])
    assert res["ok"], res  # 경고이지 오류가 아니다
    assert len(res["step_multi_outgoing_warnings"]) == 1
    assert "t-s-001" in res["step_multi_outgoing_warnings"][0]
    assert "wf:Decision" in res["step_multi_outgoing_warnings"][0]


def test_legacy_yaml_residue_warned(tmp_path):
    body = """
<https://mso.dev/ontology/workflow#node/t/t-s-001> a wf:Step, wf:Node, wf:Task ;
    wf:label "산출" ; wf:instruction "산출" ; wf:status "active" .
"""
    write_abox(tmp_path, body, name="workflow-t.abox.ttl")
    (tmp_path / "workflow-t.yaml").write_text("workflows: []\n", encoding="utf-8")
    (tmp_path / "workflow-orphan.yaml").write_text("workflows: []\n", encoding="utf-8")
    res = validate_abox.validate_abox([tmp_path])
    assert res["ok"]  # 거버넌스 경고이지 shape 오류가 아니다
    warnings = "\n".join(res["legacy_yaml_warnings"])
    assert "제거 후보" in warnings
    assert "migration blocker" in warnings


def test_strict_mode_promotes_warnings_to_failure(tmp_path):
    body = """
<https://mso.dev/ontology/workflow#node/t/t-s-001> a wf:Step, wf:Node, wf:Task ;
    wf:label "분기 냄새" ; wf:instruction "진행" ; wf:status "active" ;
    wf:next <https://mso.dev/ontology/workflow#node/t/t-s-002>,
        <https://mso.dev/ontology/workflow#node/t/t-s-003> .
<https://mso.dev/ontology/workflow#node/t/t-s-002> a wf:Step, wf:Node, wf:Task ;
    wf:label "A" ; wf:instruction "A" ; wf:status "pending" .
<https://mso.dev/ontology/workflow#node/t/t-s-003> a wf:Step, wf:Node, wf:Task ;
    wf:label "B" ; wf:instruction "B" ; wf:status "pending" .
"""
    path = write_abox(tmp_path, body)
    assert validate_abox.main([str(path)]) == 0
    assert validate_abox.main([str(path), "--strict"]) == 1


def test_no_abox_found_is_error(tmp_path):
    res = validate_abox.validate_abox([tmp_path])
    assert not res["ok"]
    assert res.get("error")
