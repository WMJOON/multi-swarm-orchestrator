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


# ---- artifact 층 registry (v0.13.0): 별도 파일에 선언된 artifact 를 Stream 검증에 합친다 ----

_STREAM_WORKFLOW = """\
@prefix wf: <https://mso.dev/ontology/workflow#> .
@prefix art: <https://example.org/art#> .
@prefix x: <https://example.org/x#> .
x:workflow a wf:Workflow ; wf:label "X" ; wf:workflowType "base" ; wf:has x:start, x:end, x:run .
x:start a wf:Node, wf:Start .
x:end a wf:Node, wf:End .
x:run a wf:Node, wf:Execution, wf:Task ; wf:label "run" ; wf:inWorkflow x:workflow ; wf:hasSubject "system" ; wf:instruction "do" .
x:r0 a wf:Edge, wf:Rail ; wf:railType "default" ; wf:from x:start ; wf:to x:run .
x:r1 a wf:Edge, wf:Rail ; wf:railType "default" ; wf:from x:run ; wf:to x:end .
x:s1 a wf:Edge, wf:Stream ; wf:streamType "consumed_by" ; wf:from art:src ; wf:to x:run .
x:s2 a wf:Edge, wf:Stream ; wf:streamType "produces_to" ; wf:from x:run ; wf:to art:out .
"""

_REGISTRY = """\
@prefix wf: <https://mso.dev/ontology/workflow#> .
@prefix art: <https://example.org/art#> .
art:src a wf:RegisteredArtifact ; wf:hasArtifactType wf:KnowledgeStore ; wf:hasConvention art:src_c .
art:src_c a wf:ArtifactConvention .
art:out a wf:RegisteredArtifact ; wf:hasArtifactType wf:KnowledgeStore ; wf:hasConvention art:out_c .
art:out_c a wf:ArtifactConvention .
"""


def _project(tmp_path, with_registry):
    wf = tmp_path / "agent-context" / "workflow"
    wf.mkdir(parents=True)
    (wf / "x.abox.ttl").write_text(_STREAM_WORKFLOW, encoding="utf-8")
    if with_registry:
        index = tmp_path / "agent-context" / "index"
        index.mkdir(parents=True)
        (index / "artifacts.abox.ttl").write_text(_REGISTRY, encoding="utf-8")
    return wf, tmp_path / "agent-context" / "index" / "artifacts.abox.ttl"


def test_stream_to_undeclared_artifact_still_fails(tmp_path):
    pytest.importorskip("pyshacl")
    wf, _ = _project(tmp_path, with_registry=False)
    res = validate_abox.validate_abox([wf])
    assert not res["ok"] and "Artifact여야 함" in res["v07"]["shacl_report"]


def test_registry_next_to_workflow_dir_is_discovered_automatically(tmp_path):
    pytest.importorskip("pyshacl")
    wf, registry = _project(tmp_path, with_registry=True)
    res = validate_abox.validate_abox([wf])  # 훅처럼 workflow 디렉토리만 넘긴다
    assert res["ok"], res["v07"]["shacl_report"]
    assert res["artifact_registry_files"] == [str(registry)] and res["v06_files"] == []


def test_registry_given_explicitly_is_merged_not_validated_as_v06(tmp_path):
    pytest.importorskip("pyshacl")
    wf, registry = _project(tmp_path, with_registry=True)
    res = validate_abox.validate_abox([wf, registry])
    assert res["ok"] and res["v06_files"] == [] and res["artifact_registry_files"] == [str(registry)]


def test_oracle_evolves_to_registered_artifact_passes(tmp_path):
    """evolves_to 의 대상이 registry 에 선언된 artifact 여도 `?t a wf:Artifact` SPARQL shape 를 통과한다(Oracle workflow)."""
    pytest.importorskip("pyshacl")
    wf, registry = _project(tmp_path, with_registry=True)
    oracle = _STREAM_WORKFLOW.replace("x:workflow", "o:workflow").replace("x:", "o:").replace("https://example.org/x#", "https://example.org/o#")
    oracle = oracle.replace('wf:workflowType "base"', 'wf:workflowType "oracle"').replace("o:run a wf:Node, wf:Execution, wf:Task", "o:run a wf:Node, wf:Execution, wf:Task")
    # 평가 대상은 같은 디렉토리의 base workflow(x:workflow). 간단히 하려고 oracle 은 Task 가 art:out 을 evolve 하는 구조만 검증한다.
    extra = """
o:evolve a wf:Edge, wf:Rail ; wf:railType "evolves_to" ; wf:from o:run ; wf:to art:out .
"""
    (wf / "o.abox.ttl").write_text(oracle + extra, encoding="utf-8")
    res = validate_abox.validate_abox([wf])
    report = res["v07"]["shacl_report"]
    assert "evolves_to/tests_to Rail의 to는 Workflow 또는 Artifact여야 함" not in report, report
