"""wf_to_ttl 테스트 — YAML→TTL 투영 + feedback-loop(SPARQL) + 로컬 shape(SHACL).

실행: python3 -m pytest tests/ -q   (rdflib + pyshacl 필요)
"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from pyshacl import validate as shacl_validate

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))
import wf_to_ttl  # noqa: E402

_ASSETS = Path(__file__).resolve().parent.parent / "assets"


def _write(tmp_path, name, doc):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return p


# ─── 투영 ────────────────────────────────────────────────────────────────────

def test_projects_workflow_membership_edges(tmp_path):
    doc = {
        "workflow": {"id": "root"},
        "workflows": [
            {"id": "a", "name": "A", "status": "completed", "steps": [
                {"type": "step", "id": "a-s-01", "label": "A", "status": "completed"}
            ]},
            {"id": "b", "name": "B", "status": "active", "steps": [
                {"type": "step", "id": "b-s-01", "label": "B", "status": "active"}
            ]},
        ]
    }
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "wf.yaml", doc))
    memberships = list(g.triples((None, wf_to_ttl.WF.hasNode, None)))
    subflows = list(g.triples((None, wf_to_ttl.WF.has_subWorkflow, None)))
    assert len(memberships) == 2
    assert len(subflows) == 2
    assert all("workflow/root/" in str(s) for s, _, _ in memberships)


def test_real_root_template_feedback_control_and_shape_conform():
    """배포 root-workflow 템플릿은 feedback-loop control + 로컬 shape 를 통과해야 한다."""
    res = wf_to_ttl.validate(_ASSETS / "root-workflow-template.yaml")
    assert res["ok"], res
    assert res["cycles"] == []
    assert res["shacl_conforms"]


# ─── Feedback loop control (cycle 자체가 아니라 Eval 개입점 유무를 검증) ───

def test_node_feedback_loop_without_eval_fails(tmp_path):
    doc = {
        "workflows": [
            {"id": "a", "name": "A", "status": "active", "steps": [
                {"type": "step", "id": "s-01", "label": "작업", "instruction": "작업을 수행한다", "status": "active"},
                {"type": "decision", "id": "d-01", "label": "분기", "status": "active",
                 "decision_subject": "agent", "branches": [{"on": "again", "goto": "s-01"}]},
            ]},
        ]
    }
    res = wf_to_ttl.validate(_write(tmp_path, "cyclic.yaml", doc))
    assert res["ok"] is False
    assert len(res["uncontrolled_loops"]) >= 1
    assert any(u.endswith(("node/a/s-01", "node/a/d-01")) for u in res["uncontrolled_loops"])


def test_node_feedback_loop_with_user_decision_gate_conforms(tmp_path):
    """HITL/user decision gate는 feedback loop의 제어점으로 인정한다."""
    doc = {
        "workflows": [
            {"id": "a", "name": "A", "status": "active", "steps": [
                {"type": "step", "id": "s-01", "label": "수정", "instruction": "반려 내용을 수정한다", "status": "active"},
                {"type": "decision", "id": "d-01", "label": "승인", "status": "active",
                 "decision_subject": "user",
                 "branches": [{"on": "rejected", "goto": "s-01"}, {"on": "approved"}]},
            ]},
        ]
    }
    res = wf_to_ttl.validate(_write(tmp_path, "user-loop-controlled.yaml", doc))
    assert res["ok"], res
    assert res["uncontrolled_loops"] == []


def test_node_feedback_loop_with_agent_decision_gate_conforms(tmp_path):
    """선택/라우팅 Decision gate는 criteria가 있으면 process loop 제어점이다."""
    ttl = tmp_path / "agent-decision-loop.ttl"
    ttl.write_text(
        """
@prefix wf: <https://mso.dev/ontology/workflow#> .

<https://mso.dev/ontology/workflow#workflow/a> a wf:Workflow ;
    wf:hasNode <https://mso.dev/ontology/workflow#node/a/s-01>, <https://mso.dev/ontology/workflow#node/a/v-01> .

<https://mso.dev/ontology/workflow#node/a/s-01> a wf:Step, wf:Task, wf:Node ;
    wf:label "수정" ;
    wf:instruction "검증 실패 내용을 수정한다" ;
    wf:status "active" ;
    wf:next <https://mso.dev/ontology/workflow#node/a/v-01> .

<https://mso.dev/ontology/workflow#node/a/v-01> a wf:Decision, wf:Node ;
    wf:decisionSubject "agent" ;
    wf:decisionCriteria "schema validates" ;
    wf:label "검증" ;
    wf:status "active" ;
    wf:hasBranch <https://mso.dev/ontology/workflow#node/a/v-01_branch_failed_s-01>,
        <https://mso.dev/ontology/workflow#node/a/v-01_branch_passed> .

<https://mso.dev/ontology/workflow#node/a/v-01_branch_failed_s-01> a wf:Branch ;
    wf:on "failed" ;
    wf:goto "s-01" ;
    wf:gotoNode <https://mso.dev/ontology/workflow#node/a/s-01> .

<https://mso.dev/ontology/workflow#node/a/v-01_branch_passed> a wf:Branch ;
    wf:on "passed" .
""",
        encoding="utf-8",
    )
    conforms, _, text = shacl_validate(
        str(ttl),
        shacl_graph=str(wf_to_ttl.SHAPES),
        ont_graph=str(wf_to_ttl.TBOX),
        inference="rdfs",
        abort_on_first=False,
    )
    assert conforms, text


def test_node_feedback_loop_with_eval_gate_conforms(tmp_path):
    """순환은 허용하되 loop 안에 별도 Eval gate 가 있어야 한다."""
    doc = {
        "workflows": [
            {"id": "a", "name": "A", "status": "active", "steps": [
                {"type": "step", "id": "s-01", "label": "작업", "instruction": "작업을 수행한다", "status": "active"},
                {"type": "eval", "id": "e-01", "label": "품질 평가", "status": "active",
                 "oracle_type": "metric", "criteria": ["accepted"], "target": "a",
                 "target_artifact": "out/",
                 "branches": [{"on": "fail", "goto": "s-fix"}, {"on": "pass"}]},
                {"type": "step", "id": "s-fix", "label": "개선 반영", "status": "active",
                 "instruction": "평가 결과를 작업 workflow에 반영한다", "evolves": "a"},
                {"type": "decision", "id": "d-01", "label": "분기", "status": "active",
                 "decision_subject": "agent",
                 "branches": [{"on": "again", "goto": "s-01"}, {"on": "done"}]},
            ]},
        ]
    }
    res = wf_to_ttl.validate(_write(tmp_path, "controlled.yaml", doc))
    assert res["ok"], res
    assert res["uncontrolled_loops"] == []


def test_decision_branch_target_does_not_get_auto_next(tmp_path):
    """branch가 있는 Decision은 같은 방향의 sequential wf:next를 자동 생성하지 않는다."""
    doc = {"workflows": [{
        "id": "a", "name": "A", "status": "active", "steps": [
            {"type": "step", "id": "s-01", "label": "작업", "status": "active"},
            {"type": "decision", "id": "d-01", "label": "분기", "status": "active",
             "decision_subject": "agent", "branches": [{"on": "ok", "goto": "s-02"}]},
            {"type": "step", "id": "s-02", "label": "후속", "status": "active"},
        ],
    }]}
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "decision-branch.yaml", doc))
    decision = wf_to_ttl._node_uri("d-01", "a")
    target = wf_to_ttl._node_uri("s-02", "a")
    assert (decision, wf_to_ttl.WF.next, target) not in g


def test_critical_dep_cycle_is_observed_not_rejected(tmp_path):
    """module dependency cycle은 Eval 모델이 없으므로 shape range만 검증하고 topology에서 관측한다."""
    doc = {
        "phases": [{"id": "p", "name": "P", "status": "active"}],
        "critical_dependencies": [
            {"from": "m1", "to": "m2"},
            {"from": "m2", "to": "m1"},
        ],
    }
    res = wf_to_ttl.validate(_write(tmp_path, "cd.yaml", doc))
    assert res["ok"], res


# ─── 로컬 shape (SHACL) ───

def test_bad_status_enum_fails_shacl(tmp_path):
    doc = {"phases": [{"id": "x", "name": "X", "status": "done"}]}  # done ∉ enum
    res = wf_to_ttl.validate(_write(tmp_path, "badstatus.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False


def test_validation_projects_to_eval_metric(tmp_path):
    # Legacy YAML type:validation → wf:Eval(metric). 산출물 검증은 Eval이다.
    doc = {
        "phases": [{
            "id": "t", "name": "T", "status": "active",
            "steps": [
                {
                    "type": "step", "id": "t-s-00", "label": "스키마 산출",
                    "instruction": "검증 대상 schema artifact를 생산한다",
                    "status": "active", "deliverables": ["schema.yaml"],
                },
                {
                    "type": "validation", "id": "t-v-01", "label": "스키마 검증",
                    "status": "active", "criteria": ["schema valid"], "target": "t",
                    "target_artifact": "schema.yaml",
                    "branches": [{"on": "fail", "goto": "t-s-01"}, {"on": "pass"}],
                },
                {
                    "type": "step", "id": "t-s-01", "label": "스키마 개선",
                    "instruction": "검증 결과를 바탕으로 workflow schema를 개선한다",
                    "status": "active", "evolves": "t",
                },
            ],
        }]
    }
    res = wf_to_ttl.validate(_write(tmp_path, "okv.yaml", doc))
    assert res["ok"], res  # validation → eval, oracle_type=metric 주입으로 conform
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "okv-graph.yaml", doc))
    node = wf_to_ttl._node_uri("t-v-01")
    assert (node, wf_to_ttl.RDF.type, wf_to_ttl.WF.Eval) in g
    assert (node, wf_to_ttl.RDF.type, wf_to_ttl.WF.Decision) not in g
    assert (node, wf_to_ttl.WF.oracleType, wf_to_ttl.Literal("metric")) in g
    assert (node, wf_to_ttl.WF.criteria, wf_to_ttl.Literal("schema valid")) in g


# ─── ABox ↔ TBox 정합 (range / 통제어휘) ───

def test_node_typed_as_wf_node(tmp_path):
    """투영 노드는 specific class + wf:Node 로 명시 타입핑된다(추론 없이 range 성립)."""
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "step", "id": "p-s-01", "label": "작업", "status": "active"}],
    }]}
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "n.yaml", doc))
    from rdflib import RDF
    nu = wf_to_ttl._node_uri("p-s-01")
    types = {str(o) for o in g.objects(nu, RDF.type)}
    assert str(wf_to_ttl.WF.Step) in types
    assert str(wf_to_ttl.WF.Node) in types


def test_sequential_next_and_branch_goto_node_projected(tmp_path):
    """phase.steps[] 순서와 decision.branches[].goto 를 실행 edge 로 투영한다."""
    doc = {
        "workflow": {"id": "wf"},
        "phases": [{
            "id": "p",
            "name": "P",
            "status": "active",
            "steps": [
                {
                    "type": "step",
                    "id": "s-01",
                    "label": "첫 작업",
                    "instruction": "첫 작업을 수행하라",
                    "status": "active",
                },
                {
                    "type": "decision",
                    "id": "d-01",
                    "label": "승인",
                    "status": "active",
                    "decision_subject": "user",
                    "owner": "wmjoon",
                    "branches": [{"on": "rejected", "goto": "s-01"}],
                },
                {
                    "type": "step",
                    "id": "s-02",
                    "label": "다음 작업",
                    "instruction": "다음 작업을 수행하라",
                    "status": "pending",
                },
            ],
        }],
    }
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "wf.yaml", doc))
    s1 = wf_to_ttl._node_uri("s-01", "wf")
    d1 = wf_to_ttl._node_uri("d-01", "wf")
    s2 = wf_to_ttl._node_uri("s-02", "wf")
    branch = next(g.objects(d1, wf_to_ttl.WF.hasBranch))

    assert (s1, wf_to_ttl.WF.next, d1) in g
    assert (d1, wf_to_ttl.WF.next, s2) in g
    assert (branch, wf_to_ttl.WF.gotoNode, s1) in g


def test_task_and_eval_roles_projected_from_legacy_oracle_alias(tmp_path):
    """legacy YAML oracle 노드는 TTL에서 wf:Eval gate로 투영된다."""
    doc = {"phases": [{
        "id": "p",
        "name": "P",
        "status": "active",
        "steps": [
            {
                "type": "step",
                "id": "s-01",
                "label": "생성",
                "instruction": "산출물을 만든다",
                "status": "active",
            },
            {
                "type": "decision",
                "id": "d-01",
                "label": "진행 분기",
                "status": "active",
                "decision_subject": "user",
                "owner": "wmjoon",
            },
            {
                "type": "oracle",
                "id": "o-01",
                "label": "품질 평가",
                "status": "active",
                "oracle_type": "agent",
                "target": "p",
                "criteria": ["quality score passes"],
            },
        ],
    }]}
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "roles.yaml", doc))
    task = wf_to_ttl._node_uri("s-01")
    decision = wf_to_ttl._node_uri("d-01")
    eval_node = wf_to_ttl._node_uri("o-01")

    assert (task, wf_to_ttl.RDF.type, wf_to_ttl.WF.Task) in g
    assert (decision, wf_to_ttl.RDF.type, wf_to_ttl.WF.Decision) in g
    assert (decision, wf_to_ttl.RDF.type, wf_to_ttl.WF.Eval) not in g
    assert (eval_node, wf_to_ttl.RDF.type, wf_to_ttl.WF.Eval) in g
    assert str(next(g.objects(eval_node, wf_to_ttl.WF.oracleType))) == "agent"


def test_event_node_projects_as_node_not_task(tmp_path):
    """scheduler 같은 진입 이벤트는 wf:Event + wf:Node 이며 wf:Task가 아니다."""
    doc = {"workflow": {"id": "wf"}, "phases": [{
        "id": "p",
        "name": "P",
        "status": "active",
        "steps": [
            {
                "type": "event",
                "id": "e-01",
                "label": "정기 실행 스케줄러",
                "status": "active",
                "event_kind": "scheduler",
                "source": ".github/workflows/weekly.yml",
            },
            {
                "type": "step",
                "id": "s-01",
                "label": "생성",
                "instruction": "산출물을 만든다",
                "status": "active",
            },
        ],
    }]}
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "event.yaml", doc))
    event = wf_to_ttl._node_uri("e-01", "wf")
    step = wf_to_ttl._node_uri("s-01", "wf")

    assert (event, wf_to_ttl.RDF.type, wf_to_ttl.WF.Event) in g
    assert (event, wf_to_ttl.RDF.type, wf_to_ttl.WF.Node) in g
    assert (event, wf_to_ttl.RDF.type, wf_to_ttl.WF.Task) not in g
    assert str(next(g.objects(event, wf_to_ttl.WF.eventKind))) == "scheduler"
    assert (event, wf_to_ttl.WF.next, step) in g


def test_eval_node_type_projected(tmp_path):
    """v0.5.0 현행 YAML eval 노드는 wf:Eval로 투영된다."""
    doc = {"phases": [{
        "id": "p",
        "name": "P",
        "status": "active",
        "steps": [{
            "type": "eval",
            "id": "e-01",
            "label": "품질 평가",
            "status": "active",
            "oracle_type": "metric",
            "target": "p",
            "criteria": ["score >= 0.8"],
            "target_artifact": "out/",
            "order_target": "s-02",
            "order_artifact": "out/report.csv",
        }],
    }]}
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "eval.yaml", doc))
    eval_node = wf_to_ttl._node_uri("e-01")

    assert (eval_node, wf_to_ttl.RDF.type, wf_to_ttl.WF.Eval) in g
    assert (eval_node, wf_to_ttl.WF.target, wf_to_ttl._workflow_uri("p")) in g
    assert str(next(g.objects(eval_node, wf_to_ttl.WF.targetArtifact))) == "out/"
    assert str(next(g.objects(eval_node, wf_to_ttl.WF.orderTarget))) == "s-02"
    assert str(next(g.objects(eval_node, wf_to_ttl.WF.orderArtifact))) == "out/report.csv"


def test_eval_without_workflow_target_measured_artifact_and_evolution_fails_shape(tmp_path):
    """모든 Eval은 target workflow와 측정 artifact를 선언해야 한다."""
    doc = {"phases": [{
        "id": "p",
        "name": "P",
        "status": "active",
        "steps": [{
            "type": "eval",
            "id": "e-01",
            "label": "품질 평가",
            "status": "active",
            "oracle_type": "metric",
            "criteria": ["score >= 0.8"],
        }],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "eval-missing-measurement.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False
    assert "Eval은 평가 대상 workflow를 wf:target으로 선언해야 함" in res["shacl_report"]
    assert "Eval은 측정 대상 artifact를 wf:targetArtifact로 선언해야 함" in res["shacl_report"]


def test_eval_without_downstream_evolves_target_fails_shape(tmp_path):
    """Eval 이후 task는 Eval target workflow를 wf:evolves로 선언해야 한다."""
    doc = {"phases": [{
        "id": "p",
        "name": "P",
        "status": "active",
        "steps": [
            {
                "type": "eval",
                "id": "e-01",
                "label": "품질 평가",
                "status": "active",
                "oracle_type": "metric",
                "target": "p",
                "target_artifact": "out/",
                "criteria": ["score >= 0.8"],
                "branches": [{"on": "fail", "goto": "s-fix"}, {"on": "pass"}],
            },
            {
                "type": "step",
                "id": "s-fix",
                "label": "개선 반영",
                "status": "active",
            },
        ],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "eval-missing-evolves.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False
    assert "Eval은 wf:next 대신 on=fail branch로 Task에 진입하고, 그 Task가 wf:target workflow를 wf:evolves로 선언해야 함" in res["shacl_report"]


def test_node_feedback_loop_without_eval_fails(tmp_path):
    """agent decision 이 만드는 재귀 branch loop는 Eval 개입점이 아니므로 실패한다."""
    doc = {"phases": [{
        "id": "p",
        "name": "P",
        "status": "active",
        "steps": [
            {
                "type": "step",
                "id": "s-01",
                "label": "생성",
                "instruction": "산출물을 만든다",
                "status": "active",
                "directories": [{"role": "output", "path": "out/"}],
                "evolves": "p",
            },
            {
                "type": "decision",
                "id": "d-01",
                "label": "자동 재시도",
                "status": "active",
                "decision_subject": "agent",
                "branches": [{"on": "fail", "goto": "s-01"}, {"on": "pass"}],
            },
        ],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "node-loop.yaml", doc))
    assert res["ok"] is False
    assert any(uri.endswith("node/s-01") or uri.endswith("node/d-01") for uri in res["uncontrolled_loops"])


def test_node_feedback_loop_with_eval_gate_conforms(tmp_path):
    doc = {"phases": [{
        "id": "p",
        "name": "P",
        "status": "active",
        "steps": [
            {
                "type": "step",
                "id": "s-01",
                "label": "생성",
                "instruction": "산출물을 만든다",
                "status": "active",
                "directories": [{"role": "output", "path": "out/"}],
                "evolves": "p",
            },
            {
                "type": "oracle",
                "id": "o-01",
                "label": "품질 평가",
                "status": "active",
                "oracle_type": "metric",
                "target": "p",
                "target_artifact": "out/",
                "criteria": ["score >= 0.8"],
                "branches": [{"on": "fail", "goto": "s-01"}, {"on": "pass"}],
            },
        ],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "node-loop-controlled.yaml", doc))
    assert res["ok"], res
    assert res["uncontrolled_loops"] == []


def test_eval_tool_revision_target_must_be_remediation_step(tmp_path):
    doc = {"phases": [{
        "id": "p",
        "name": "P",
        "status": "active",
        "steps": [
            {
                "type": "step",
                "id": "s-label",
                "label": "라벨링",
                "instruction": "라벨링 엔진을 실행한다",
                "status": "active",
                "uses_tool": "[[nlu engine process]]",
                "directories": [{"role": "input", "path": "scripts/"}],
                "deliverables": ["data/labeling.db#labels"],
            },
            {
                "type": "eval",
                "id": "e-review",
                "label": "엔진 평가",
                "status": "active",
                "oracle_type": "user",
                "target": "p",
                "criteria": ["labels table 기반으로 엔진 개선 여부 판단"],
                "target_artifact": "[[nlu engine process]]",
                "order_target": "d-route",
                "branches": [{"on": "fail", "goto": "d-route"}, {"on": "pass"}],
            },
            {
                "type": "decision",
                "id": "d-route",
                "label": "라우팅",
                "status": "active",
                "decision_subject": "user",
                "branches": [{"on": "approved", "goto": "s-label"}, {"on": "rejected", "goto": "s-label"}],
            },
        ],
    }]}

    res = wf_to_ttl.validate(_write(tmp_path, "bad-eval-order-target.yaml", doc))

    assert res["ok"] is False
    assert "eval revision shape" in res["shacl_report"]


def test_eval_tool_revision_target_accepts_targeted_remediation_step(tmp_path):
    doc = {"phases": [{
        "id": "p",
        "name": "P",
        "status": "active",
        "steps": [
            {
                "type": "step",
                "id": "s-label",
                "label": "라벨링",
                "instruction": "라벨링 엔진을 실행한다",
                "status": "active",
                "uses_tool": "[[nlu engine process]]",
                "directories": [{"role": "input", "path": "scripts/"}],
                "deliverables": ["data/labeling.db#labels"],
            },
            {
                "type": "eval",
                "id": "e-review",
                "label": "엔진 평가",
                "status": "active",
                "oracle_type": "user",
                "target": "p",
                "criteria": ["labels table 기반으로 엔진 개선 여부 판단"],
                "target_artifact": "[[nlu engine process]]",
                "order_target": "s-fix",
                "branches": [{"on": "fail", "goto": "s-fix"}, {"on": "pass"}],
            },
            {
                "type": "step",
                "id": "s-fix",
                "label": "엔진 개선",
                "instruction": "평가 결과에 따라 프롬프트 또는 라벨링 처리 로직을 개선한다",
                "status": "active",
                "target_artifact": "[[nlu engine process]]",
                "evolves": "p",
            },
        ],
    }]}

    res = wf_to_ttl.validate(_write(tmp_path, "good-eval-order-target.yaml", doc))

    assert res["ok"], res


def test_multi_workflow_and_node_uris_are_workflow_scoped(tmp_path):
    """서로 다른 workflow의 동명 sub-workflow/node가 RDF 병합에서 충돌하지 않는다."""
    doc_a = {
        "workflow": {"id": "workflow-a"},
        "generation": {
            "id": "generation",
            "label": "Generation A",
            "status": "active",
            "steps": [{
                "type": "step",
                "id": "s-010",
                "label": "Generate A",
                "instruction": "A를 생성하라",
                "status": "active",
            }],
        },
    }
    doc_b = {
        "workflow": {"id": "workflow-b"},
        "generation": {
            "id": "generation",
            "label": "Generation B",
            "status": "pending",
            "steps": [{
                "type": "step",
                "id": "s-010",
                "label": "Generate B",
                "instruction": "B를 생성하라",
                "status": "pending",
            }],
        },
    }
    g1, _ = wf_to_ttl.build_graph(_write(tmp_path, "a.yaml", doc_a))
    g2, _ = wf_to_ttl.build_graph(_write(tmp_path, "b.yaml", doc_b))
    combined = g1 + g2

    workflows = {str(s) for s in combined.subjects(wf_to_ttl.RDF.type, wf_to_ttl.WF.Workflow)}
    nodes = {str(s) for s in combined.subjects(wf_to_ttl.RDF.type, wf_to_ttl.WF.Step)}

    assert any(uri.endswith("workflow/workflow-a/generation") for uri in workflows)
    assert any(uri.endswith("workflow/workflow-b/generation") for uri in workflows)
    assert any(uri.endswith("node/workflow-a/s-010") for uri in nodes)
    assert any(uri.endswith("node/workflow-b/s-010") for uri in nodes)
    assert len([uri for uri in workflows if uri.endswith("/generation")]) == 2
    assert len([uri for uri in nodes if uri.endswith("/s-010")]) == 2


def test_has_subworkflow_undeclared_target_fails_range(tmp_path):
    """has_subWorkflow 타깃이 Workflow 타입이 아니면 sh:class wf:Workflow 위반."""
    doc = {"workflow": {"id": "root"}, "workflows": [
        {"id": "a", "name": "A", "status": "active", "steps": [
            {"type": "step", "id": "a-s-01", "label": "A", "status": "active"}
        ]},
    ]}
    p = _write(tmp_path, "dangling.yaml", doc)
    g, _ = wf_to_ttl.build_graph(p)
    root = wf_to_ttl.WF["workflow/root"]
    ghost = wf_to_ttl.WF["workflow/ghost"]
    g.add((root, wf_to_ttl.WF.has_subWorkflow, ghost))
    conforms, _ = wf_to_ttl.run_shacl(g)
    assert conforms is False


def test_legacy_phase_input_warns_but_conforms(tmp_path):
    doc = {"phases": [
        {"id": "a", "name": "A", "status": "active", "steps": [
            {"type": "step", "id": "a-s-01", "label": "A", "instruction": "A 수행", "status": "active"}
        ]},
    ]}
    res = wf_to_ttl.validate(_write(tmp_path, "dangling.yaml", doc))
    assert res["ok"] is True
    assert res["legacy_warnings"]


def test_bad_decision_subject_enum_fails(tmp_path):
    """decision_subject 가 user|agent 밖이면 위반."""
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "decision", "id": "p-d-01", "label": "분기",
                   "status": "active", "decision_subject": "system"}],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "subject.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False


def test_good_decision_subject_conforms(tmp_path):
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "decision", "id": "p-d-01", "label": "분기",
                   "status": "active", "decision_subject": "agent",
                   "decision_criteria": "F1 < 0.87",
                   "branches": [{"on": "low_confidence"}, {"on": "enough_confidence"}]}],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "subject_ok.yaml", doc))
    assert res["ok"], res


def test_decision_single_outgoing_fails_shape(tmp_path):
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [
            {"type": "decision", "id": "p-d-01", "label": "분기",
             "status": "active", "decision_subject": "agent",
             "branches": [{"on": "retry", "goto": "p-s-01"}]},
            {"type": "step", "id": "p-s-01", "label": "후속", "status": "active"},
        ],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "decision-single-outgoing.yaml", doc))
    assert res["ok"] is False
    assert "Decision은 최소 2개 이상의 wf:hasBranch" in res["shacl_report"]


def test_eval_single_outgoing_fails_shape(tmp_path):
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [
            {"type": "eval", "id": "p-v-01", "label": "평가",
             "status": "active", "oracle_type": "metric", "target": "p",
             "target_artifact": "out/", "criteria": ["score >= 0.8"],
             "branches": [{"on": "fail", "goto": "p-s-01"}]},
            {"type": "step", "id": "p-s-01", "label": "개선",
             "status": "active", "instruction": "평가 결과를 반영한다", "evolves": "p"},
        ],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "eval-single-outgoing.yaml", doc))
    assert res["ok"] is False
    assert "Eval은 최소 2개 이상의 outgoing branch" in res["shacl_report"]


def test_eval_target_cannot_be_own_container_workflow(tmp_path):
    ttl = tmp_path / "eval-self-target.ttl"
    ttl.write_text(
        """
@prefix wf: <https://mso.dev/ontology/workflow#> .

<https://mso.dev/ontology/workflow#workflow/p> a wf:Workflow ;
    wf:hasNode <https://mso.dev/ontology/workflow#node/p/s-01>,
        <https://mso.dev/ontology/workflow#node/p/e-01>,
        <https://mso.dev/ontology/workflow#node/p/s-fix> .

<https://mso.dev/ontology/workflow#node/p/s-01> a wf:Step, wf:Task, wf:Node ;
    wf:label "생산" ;
    wf:instruction "평가 대상 artifact를 생산한다" ;
    wf:status "active" ;
    wf:deliverables "out" .

<https://mso.dev/ontology/workflow#node/p/e-01> a wf:Eval, wf:Node ;
    wf:label "검수" ;
    wf:criteria "out artifact가 검수 기준을 만족한다" ;
    wf:status "active" ;
    wf:oracleType "metric" ;
    wf:target <https://mso.dev/ontology/workflow#workflow/p> ;
    wf:targetArtifact "out" ;
    wf:hasBranch <https://mso.dev/ontology/workflow#node/p/e-01_branch_fail_s-fix>,
        <https://mso.dev/ontology/workflow#node/p/e-01_branch_pass> .

<https://mso.dev/ontology/workflow#node/p/e-01_branch_fail_s-fix> a wf:Branch ;
    wf:on "fail" ;
    wf:gotoNode <https://mso.dev/ontology/workflow#node/p/s-fix> .

<https://mso.dev/ontology/workflow#node/p/e-01_branch_pass> a wf:Branch ;
    wf:on "pass" .

<https://mso.dev/ontology/workflow#node/p/s-fix> a wf:Step, wf:Task, wf:Node ;
    wf:label "수정" ;
    wf:instruction "검수 실패 내용을 반영한다" ;
    wf:status "active" ;
    wf:evolves <https://mso.dev/ontology/workflow#workflow/p> .
""",
        encoding="utf-8",
    )
    conforms, _, report = shacl_validate(
        str(ttl),
        shacl_graph=str(wf_to_ttl.SHAPES),
        ont_graph=str(wf_to_ttl.TBOX),
        inference="rdfs",
        abort_on_first=False,
    )
    assert not conforms
    assert "Eval은 자기 자신을 포함하는 workflow를 wf:target으로 삼을 수 없음" in report


def test_eval_cannot_be_artifact_consumer(tmp_path):
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [
            {"type": "eval", "id": "p-v-01", "label": "평가",
             "status": "active", "oracle_type": "metric", "target": "p",
             "target_artifact": "out/", "criteria": ["score >= 0.8"],
             "branches": [{"on": "fail", "goto": "p-s-01"}, {"on": "pass"}]},
            {"type": "step", "id": "p-s-01", "label": "개선",
             "status": "active", "instruction": "평가 결과를 반영한다", "evolves": "p"},
        ],
    }]}
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "eval-consumes.yaml", doc))
    artifact = wf_to_ttl.WF["artifact/p/out"]
    eval_node = wf_to_ttl._node_uri("p-v-01")
    g.add((artifact, wf_to_ttl.RDF.type, wf_to_ttl.WF.Artifact))
    g.add((artifact, wf_to_ttl.WF.consumes, eval_node))
    g.add((artifact, wf_to_ttl.WF.measures, eval_node))
    conforms, report = wf_to_ttl.run_shacl(g)
    assert conforms is False
    assert "Eval은 artifact consume/check 대상이 아니며 Artifact는 wf:measures로 Eval에 연결해야 함" in report


def test_project_owner_and_decision_on_fail_do_not_infer_eval(tmp_path):
    ttl = tmp_path / "metadata-domain.ttl"
    ttl.write_text(
        """
@prefix wf: <https://mso.dev/ontology/workflow#> .

<https://mso.dev/ontology/workflow#project/demo> a wf:Project ;
    wf:label "Demo" ;
    wf:owner "wmjoon" .

<https://mso.dev/ontology/workflow#workflow/demo/root> a wf:Workflow ;
    wf:hasNode <https://mso.dev/ontology/workflow#node/demo/v-001> .

<https://mso.dev/ontology/workflow#node/demo/v-001> a wf:Node, wf:Decision ;
    wf:label "schema validation" ;
    wf:decisionSubject "agent" ;
    wf:harness "validator" ;
    wf:onFail "block" ;
    wf:passCriteria "schema validates" ;
    wf:hasBranch <https://mso.dev/ontology/workflow#node/demo/v-001_branch_failed>,
        <https://mso.dev/ontology/workflow#node/demo/v-001_branch_passed> ;
    wf:status "pending" .

<https://mso.dev/ontology/workflow#node/demo/v-001_branch_failed> a wf:Branch ;
    wf:on "failed" .

<https://mso.dev/ontology/workflow#node/demo/v-001_branch_passed> a wf:Branch ;
    wf:on "passed" .
""",
        encoding="utf-8",
    )
    conforms, _, report = shacl_validate(
        str(ttl),
        shacl_graph=str(wf_to_ttl.SHAPES),
        ont_graph=str(wf_to_ttl.TBOX),
        inference="rdfs",
        abort_on_first=False,
    )
    assert conforms, report


def test_decision_next_duplicate_with_branch_target_fails_shape(tmp_path):
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [
            {"type": "decision", "id": "p-d-01", "label": "분기",
             "status": "active", "decision_subject": "agent",
             "branches": [{"on": "ok", "goto": "p-s-01"}]},
            {"type": "step", "id": "p-s-01", "label": "후속", "status": "active"},
        ],
    }]}
    p = _write(tmp_path, "duplicate-decision-next.yaml", doc)
    g, _ = wf_to_ttl.build_graph(p)
    decision = wf_to_ttl._node_uri("p-d-01")
    target = wf_to_ttl._node_uri("p-s-01")
    g.add((decision, wf_to_ttl.WF.next, target))
    conforms, report = wf_to_ttl.run_shacl(g)
    assert conforms is False
    assert "Decision의 wf:next가 branch gotoNode와 같으면 중복이므로 제거해야 함" in report


def test_decision_missing_subject_fails(tmp_path):
    """decision_subject 누락은 위반."""
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "decision", "id": "p-d-01", "label": "분기",
                   "status": "active"}],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "subject_bad.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False


# ─── Step instruction (지시격) ───

def test_step_without_instruction_fails(tmp_path):
    """label 만 있고 instruction 없는 Step 은 비실행 노드 → StepShape 위반."""
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "step", "id": "p-s-01", "label": "데이터 정제", "status": "active"}],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "noinstr.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False
    assert "instruction" in res["shacl_report"]


def test_step_with_instruction_conforms(tmp_path):
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{
            "type": "step", "id": "p-s-01", "label": "데이터 정제", "status": "active",
            "instruction": "raw/*.jsonl 을 읽어 PII 마스킹 후 clean/ 에 기록하라",
        }],
    }]}
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "instr.yaml", doc))
    nu = wf_to_ttl._node_uri("p-s-01")
    instrs = [str(o) for o in g.objects(nu, wf_to_ttl.WF.instruction)]
    assert instrs and "마스킹" in instrs[0]
    res = wf_to_ttl.validate(_write(tmp_path, "instr.yaml", doc))
    assert res["ok"], res


def test_tool_delegation_requires_target_input_and_output(tmp_path):
    """uses_tool step은 delegates_to edge와 consumes/produces spine을 만들 수 있어야 한다."""
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{
            "type": "step", "id": "p-s-01", "label": "도구 실행", "status": "active",
            "instruction": "tool로 입력 artifact를 처리하라",
            "uses_tool": "[[nlu engine process]]",
        }],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "bad_tool.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False
    assert "tool delegation shape" in res["shacl_report"]


def test_tool_delegation_shape_conforms(tmp_path):
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{
            "type": "step", "id": "p-s-01", "label": "도구 실행", "status": "active",
            "instruction": "tool로 입력 artifact를 처리해 labels table을 생산하라",
            "uses_tool": "[[nlu engine process]]",
            "directories": [{"role": "input", "path": "scripts/"}],
            "deliverables": ["data/labeling.db#labels"],
        }],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "good_tool.yaml", doc))
    assert res["ok"], res


def test_eval_tool_target_requires_produced_artifact(tmp_path):
    """Eval target이 tool/process면 해당 tool의 produced artifact가 있어야 한다."""
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{
            "type": "eval", "id": "p-e-01", "label": "도구 검수",
            "status": "active", "oracle_type": "user",
            "target": "p",
            "target_artifact": "[[nlu engine process]]",
            "criteria": ["tool 산출 품질 확인"],
        }],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "bad_eval_tool.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False
    assert "eval tool target shape" in res["shacl_report"]


def test_eval_tool_target_with_produced_artifact_conforms(tmp_path):
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [
            {
                "type": "step", "id": "p-s-01", "label": "도구 실행",
                "status": "active", "instruction": "tool로 labels를 생산하라",
                "uses_tool": "[[nlu engine process]]",
                "directories": [{"role": "input", "path": "scripts/"}],
                "deliverables": ["data/labeling.db#labels"],
            },
            {
                "type": "eval", "id": "p-e-01", "label": "도구 검수",
                "status": "active", "oracle_type": "user",
                "target": "p",
                "target_artifact": "[[nlu engine process]]",
                "criteria": ["tool 산출 품질 확인"],
                "branches": [{"on": "fail", "goto": "p-s-02"}, {"on": "pass"}],
            },
            {
                "type": "step", "id": "p-s-02", "label": "도구 개선 반영",
                "status": "active", "instruction": "평가 결과를 바탕으로 도구 실행 workflow를 개선한다",
                "evolves": "p",
            },
        ],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "good_eval_tool.yaml", doc))
    assert res["ok"], res


def test_eval_target_artifact_must_be_produced_by_target_workflow(tmp_path):
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [
            {
                "type": "step", "id": "p-s-01", "label": "정산",
                "status": "active", "instruction": "정산 산출물을 생산한다",
                "deliverables": ["campaign SETTLED (trajectory 로그 append, 원장 대사 완료)"],
            },
            {
                "type": "eval", "id": "p-o-01", "label": "정산 Oracle",
                "status": "active", "oracle_type": "metric",
                "target": "p",
                "target_artifact": "campaign SETTLED trajectory and ledger reconciliation",
                "criteria": ["정산 상태와 원장 대사 결과가 일치해야 한다"],
                "branches": [{"on": "fail", "goto": "p-s-02"}, {"on": "pass"}],
            },
            {
                "type": "step", "id": "p-s-02", "label": "재정산",
                "status": "active", "instruction": "정산 workflow를 보정한다",
                "evolves": "p",
            },
        ],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "bad_eval_artifact.yaml", doc))
    assert res["ok"] is False
    assert res["eval_target_artifact_mismatches"]
    assert "eval targetArtifact shape" in res["eval_target_artifact_mismatches"][0]
    assert "campaign SETTLED (trajectory 로그 append, 원장 대사 완료)" in res["eval_target_artifact_mismatches"][0]


def test_eval_target_artifact_can_measure_target_workflow_deliverable(tmp_path):
    deliverable = "campaign SETTLED (trajectory 로그 append, 원장 대사 완료)"
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [
            {
                "type": "step", "id": "p-s-01", "label": "정산",
                "status": "active", "instruction": "정산 산출물을 생산한다",
                "deliverables": [deliverable],
            },
            {
                "type": "eval", "id": "p-o-01", "label": "정산 Oracle",
                "status": "active", "oracle_type": "metric",
                "target": "p",
                "target_artifact": deliverable,
                "criteria": ["정산 상태와 원장 대사 결과가 일치해야 한다"],
                "branches": [{"on": "fail", "goto": "p-s-02"}, {"on": "pass"}],
            },
            {
                "type": "step", "id": "p-s-02", "label": "재정산",
                "status": "active", "instruction": "정산 workflow를 보정한다",
                "evolves": "p",
            },
        ],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "good_eval_artifact.yaml", doc))
    assert res["ok"], res


def test_eval_measured_artifact_must_be_produced_by_target_workflow(tmp_path):
    ttl = tmp_path / "bad-measured-artifact.ttl"
    ttl.write_text(
        """
@prefix wf: <https://mso.dev/ontology/workflow#> .

<https://mso.dev/ontology/workflow#workflow/p> a wf:Workflow ;
    wf:hasNode <https://mso.dev/ontology/workflow#node/p/e-01>,
        <https://mso.dev/ontology/workflow#node/p/s-fix> .

<https://mso.dev/ontology/workflow#node/p/e-01> a wf:Eval, wf:Node ;
    wf:label "검수" ;
    wf:status "active" ;
    wf:oracleType "metric" ;
    wf:target <https://mso.dev/ontology/workflow#workflow/p> ;
    wf:targetArtifact "out" ;
    wf:hasBranch <https://mso.dev/ontology/workflow#node/p/e-01_branch_fail_s-fix>,
        <https://mso.dev/ontology/workflow#node/p/e-01_branch_pass> .

<https://mso.dev/ontology/workflow#node/p/e-01_branch_fail_s-fix> a wf:Branch ;
    wf:on "fail" ;
    wf:gotoNode <https://mso.dev/ontology/workflow#node/p/s-fix> .

<https://mso.dev/ontology/workflow#node/p/e-01_branch_pass> a wf:Branch ;
    wf:on "pass" .

<https://mso.dev/ontology/workflow#node/p/s-fix> a wf:Step, wf:Task, wf:Node ;
    wf:label "수정" ;
    wf:status "active" ;
    wf:evolves <https://mso.dev/ontology/workflow#workflow/p> .

<https://mso.dev/ontology/workflow#artifact/p/out> a wf:Artifact ;
    wf:label "out" ;
    wf:measures <https://mso.dev/ontology/workflow#node/p/e-01> .
""",
        encoding="utf-8",
    )
    conforms, _, report = shacl_validate(
        str(ttl),
        shacl_graph=str(wf_to_ttl.SHAPES),
        ont_graph=str(wf_to_ttl.TBOX),
        inference="rdfs",
        abort_on_first=False,
    )
    assert not conforms
    assert "Eval measured_by artifact는 Eval의 wf:target workflow 안의 Task/Decision node가 wf:produces한 Artifact여야 함" in report


def test_eval_measured_artifact_produced_by_target_workflow_conforms(tmp_path):
    ttl = tmp_path / "good-measured-artifact.ttl"
    ttl.write_text(
        """
@prefix wf: <https://mso.dev/ontology/workflow#> .

<https://mso.dev/ontology/workflow#workflow/p> a wf:Workflow ;
    wf:hasNode <https://mso.dev/ontology/workflow#node/p/s-01>,
        <https://mso.dev/ontology/workflow#node/p/s-fix> .

<https://mso.dev/ontology/workflow#workflow/p/oracle> a wf:Workflow ;
    wf:hasNode <https://mso.dev/ontology/workflow#node/p/e-01> .

<https://mso.dev/ontology/workflow#node/p/s-01> a wf:Step, wf:Task, wf:Node ;
    wf:label "생산" ;
    wf:instruction "평가 대상 artifact를 생산한다" ;
    wf:status "active" ;
    wf:produces <https://mso.dev/ontology/workflow#artifact/p/out> .

<https://mso.dev/ontology/workflow#node/p/e-01> a wf:Eval, wf:Node ;
    wf:label "검수" ;
    wf:criteria "out artifact가 검수 기준을 만족한다" ;
    wf:status "active" ;
    wf:oracleType "metric" ;
    wf:target <https://mso.dev/ontology/workflow#workflow/p> ;
    wf:targetArtifact "out" ;
    wf:hasBranch <https://mso.dev/ontology/workflow#node/p/e-01_branch_fail_s-fix>,
        <https://mso.dev/ontology/workflow#node/p/e-01_branch_pass> .

<https://mso.dev/ontology/workflow#node/p/e-01_branch_fail_s-fix> a wf:Branch ;
    wf:on "fail" ;
    wf:gotoNode <https://mso.dev/ontology/workflow#node/p/s-fix> .

<https://mso.dev/ontology/workflow#node/p/e-01_branch_pass> a wf:Branch ;
    wf:on "pass" .

<https://mso.dev/ontology/workflow#node/p/s-fix> a wf:Step, wf:Task, wf:Node ;
    wf:label "수정" ;
    wf:instruction "검수 실패 내용을 반영한다" ;
    wf:status "active" ;
    wf:evolves <https://mso.dev/ontology/workflow#workflow/p> .

<https://mso.dev/ontology/workflow#artifact/p/out> a wf:Artifact ;
    wf:label "out" ;
    wf:measures <https://mso.dev/ontology/workflow#node/p/e-01> .
""",
        encoding="utf-8",
    )
    conforms, _, report = shacl_validate(
        str(ttl),
        shacl_graph=str(wf_to_ttl.SHAPES),
        ont_graph=str(wf_to_ttl.TBOX),
        inference="rdfs",
        abort_on_first=False,
    )
    assert conforms, report


# ─── 교차-스킬 join: directories.path ∈ scaffold(index) ───

def _scaffold_fixture(tmp_path):
    """index.yaml(모듈 m1/) + 그 안에 sub/ 디렉토리 생성."""
    (tmp_path / "m1" / "sub").mkdir(parents=True)
    idx = tmp_path / "index.yaml"
    idx.write_text(yaml.safe_dump({
        "project": {"id": "proj"},
        "modules": [{"id": "m1", "path": "m1/", "subdirs": [{"path": "sub/", "role": "data"}]}],
    }, allow_unicode=True), encoding="utf-8")
    return idx


def test_scaffold_registered_path_no_warning(tmp_path):
    idx = _scaffold_fixture(tmp_path)
    wf = _write(tmp_path, "wf.yaml", {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "step", "id": "p-s-01", "label": "작업",
                   "instruction": "처리하라", "status": "active",
                   "directories": [{"role": "data", "path": "m1/sub"}]}],
    }]})
    res = wf_to_ttl.validate(wf, index_yaml=idx)
    assert res["scaffold_warnings"] == [], res["scaffold_warnings"]


def test_scaffold_unregistered_path_warns(tmp_path):
    idx = _scaffold_fixture(tmp_path)
    wf = _write(tmp_path, "wf.yaml", {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "step", "id": "p-s-01", "label": "작업",
                   "instruction": "처리하라", "status": "active",
                   "directories": [{"role": "data", "path": "outside/x"}]}],
    }]})
    res = wf_to_ttl.validate(wf, index_yaml=idx)
    assert len(res["scaffold_warnings"]) == 1
    assert "p-s-01" in res["scaffold_warnings"][0]


def test_directory_projected_structured(tmp_path):
    """directories[] → wf:directory blank node(dirRole+dirPath) 구조 투영."""
    wf = _write(tmp_path, "wf.yaml", {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "step", "id": "p-s-01", "label": "작업",
                   "instruction": "처리하라", "status": "active",
                   "directories": [{"role": "data", "path": "m1/sub"}]}],
    }]})
    g, _ = wf_to_ttl.build_graph(wf)
    dns = list(g.objects(wf_to_ttl._node_uri("p-s-01"), wf_to_ttl.WF.directory))
    assert len(dns) == 1
    assert str(next(g.objects(dns[0], wf_to_ttl.WF.dirPath))) == "m1/sub"
    assert str(next(g.objects(dns[0], wf_to_ttl.WF.dirRole))) == "data"


# ─── CLI 계약 ───

def test_x_extension_namespace_ignored(tmp_path):
    """top-level x_* 확장 키(소비자 도메인 필드, 예: MSM 실행 계약)는 phase 로 오인되지 않는다."""
    import wf_node
    doc = {
        "collect": {"id": "collect", "label": "C", "status": "active",
                    "steps": [{"type": "step", "id": "c-s-01", "label": "작업",
                               "instruction": "하라", "status": "active"}]},
        "x_msm": {"kind": "pipeline", "inputs": [{"path": "a"}],
                  "governance": {"hitl_required": True}},
    }
    p = _write(tmp_path, "ext.yaml", doc)
    # wf_node: x_msm 이 phase 로 안 잡힘
    phases = {k for k, _ in wf_node._collect_phases(doc)}
    assert "collect" in phases and "x_msm" not in phases
    # wf_to_ttl: 정합 통과 (x_msm 무시)
    res = wf_to_ttl.validate(p)
    assert res["ok"], res


def test_generated_ttl_in_sync_with_schemas():
    """TBox/SHACL 가 schemas 에서 생성된 현재 상태와 일치(drift 가드). 불일치면 재생성 필요."""
    out = subprocess.run(
        [sys.executable, str(_SCRIPTS / "schemas_to_tbox.py"), "--check"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, f"schemas↔TTL drift:\n{out.stderr}"


def test_unquoted_on_branch_normalized(tmp_path):
    """미인용 'on:' 은 YAML 이 True 키로 파싱 → 도구가 정규화해 wf:on 으로 투영."""
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "decision", "id": "p-d-01", "label": "분기", "status": "active",
                   "decision_subject": "agent", "branches": [{True: "passed", "goto": "n2"}]}],
    }]}
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "wf.yaml", doc))
    nu = wf_to_ttl._node_uri("p-d-01")
    bn = list(g.objects(nu, wf_to_ttl.WF.hasBranch))
    assert len(bn) == 1
    assert str(next(g.objects(bn[0], wf_to_ttl.WF.on))) == "passed"


def test_cli_validate_exit_code_on_uncontrolled_loop(tmp_path):
    doc = {"workflows": [
        {"id": "a", "name": "A", "status": "active", "steps": [
            {"type": "step", "id": "s-01", "label": "작업", "status": "active"},
            {"type": "decision", "id": "d-01", "label": "분기", "status": "active",
             "decision_subject": "agent", "branches": [{"on": "again", "goto": "s-01"}]},
        ]},
    ]}
    p = _write(tmp_path, "c.yaml", doc)
    out = subprocess.run(
        [sys.executable, str(_SCRIPTS / "wf_to_ttl.py"), "validate", str(p)],
        capture_output=True, text=True,
    )
    assert out.returncode == 1
    assert "uncontrolled feedback loop" in out.stdout
