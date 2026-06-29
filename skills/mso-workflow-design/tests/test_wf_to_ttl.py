"""wf_to_ttl 테스트 — YAML→TTL 투영 + feedback-loop(SPARQL) + 로컬 shape(SHACL).

실행: python3 -m pytest tests/ -q   (rdflib + pyshacl 필요)
"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))
import wf_to_ttl  # noqa: E402

_ASSETS = Path(__file__).resolve().parent.parent / "assets"


def _write(tmp_path, name, doc):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return p


# ─── 투영 ────────────────────────────────────────────────────────────────────

def test_projects_phase_dependency_edges(tmp_path):
    doc = {
        "phases": [
            {"id": "a", "name": "A", "status": "completed", "dependencies": []},
            {"id": "b", "name": "B", "status": "active", "dependencies": ["a"]},
        ]
    }
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "wf.yaml", doc))
    deps = list(g.triples((None, wf_to_ttl.WF.dependsOn, None)))
    assert len(deps) == 1
    assert str(deps[0][0]).endswith("phase/b")
    assert str(deps[0][2]).endswith("phase/a")


def test_real_root_template_feedback_control_and_shape_conform():
    """배포 root-workflow 템플릿은 feedback-loop control + 로컬 shape 를 통과해야 한다."""
    res = wf_to_ttl.validate(_ASSETS / "root-workflow-template.yaml")
    assert res["ok"], res
    assert res["cycles"] == []
    assert res["shacl_conforms"]


# ─── Feedback loop control (cycle 자체가 아니라 Eval 개입점 유무를 검증) ───

def test_phase_feedback_loop_without_eval_fails(tmp_path):
    doc = {
        "phases": [
            {"id": "a", "name": "A", "status": "active", "dependencies": ["c"]},
            {"id": "b", "name": "B", "status": "active", "dependencies": ["a"]},
            {"id": "c", "name": "C", "status": "active", "dependencies": ["b"]},
        ]
    }
    res = wf_to_ttl.validate(_write(tmp_path, "cyclic.yaml", doc))
    assert res["ok"] is False
    assert len(res["uncontrolled_loops"]) >= 1
    assert any(u.endswith(("phase/a", "phase/b", "phase/c")) for u in res["uncontrolled_loops"])


def test_phase_feedback_loop_with_eval_gate_conforms(tmp_path):
    """순환은 허용하되 loop 안에 별도 Eval gate 가 있어야 한다."""
    doc = {
        "phases": [
            {"id": "a", "name": "A", "status": "active", "dependencies": ["c"]},
            {
                "id": "b",
                "name": "B",
                "status": "active",
                "dependencies": ["a"],
                "steps": [{
                    "type": "oracle",
                    "id": "b-o-01",
                    "label": "Output quality oracle",
                    "status": "active",
                    "oracle_type": "user",
                    "criteria": ["human accepted"],
                }],
            },
            {"id": "c", "name": "C", "status": "active", "dependencies": ["b"]},
        ]
    }
    res = wf_to_ttl.validate(_write(tmp_path, "controlled.yaml", doc))
    assert res["ok"], res
    assert res["uncontrolled_loops"] == []


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

def test_validation_node_missing_harness_fails_shacl(tmp_path):
    doc = {
        "phases": [{
            "id": "t", "name": "T", "status": "active",
            "steps": [{
                "type": "validation", "id": "t-v-01", "label": "스키마 검증",
                "status": "active", "pass_criteria": ["schema valid"],
                # harness 누락 → ValidationShape 위반
            }],
        }]
    }
    res = wf_to_ttl.validate(_write(tmp_path, "badv.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False
    assert "harness" in res["shacl_report"]


def test_bad_status_enum_fails_shacl(tmp_path):
    doc = {"phases": [{"id": "x", "name": "X", "status": "done"}]}  # done ∉ enum
    res = wf_to_ttl.validate(_write(tmp_path, "badstatus.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False


def test_wellformed_validation_node_conforms(tmp_path):
    doc = {
        "phases": [{
            "id": "t", "name": "T", "status": "active",
            "steps": [{
                "type": "validation", "id": "t-v-01", "label": "스키마 검증",
                "status": "active", "harness": "schema_validator",
                "pass_criteria": ["schema valid"],
            }],
        }]
    }
    res = wf_to_ttl.validate(_write(tmp_path, "okv.yaml", doc))
    assert res["ok"], res


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
            "criteria": ["score >= 0.8"],
            "target_artifact": "out/",
            "order_target": "s-02",
            "order_artifact": "out/report.csv",
        }],
    }]}
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "eval.yaml", doc))
    eval_node = wf_to_ttl._node_uri("e-01")

    assert (eval_node, wf_to_ttl.RDF.type, wf_to_ttl.WF.Eval) in g
    assert str(next(g.objects(eval_node, wf_to_ttl.WF.targetArtifact))) == "out/"
    assert str(next(g.objects(eval_node, wf_to_ttl.WF.orderTarget))) == "s-02"
    assert str(next(g.objects(eval_node, wf_to_ttl.WF.orderArtifact))) == "out/report.csv"


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
            },
            {
                "type": "decision",
                "id": "d-01",
                "label": "자동 재시도",
                "status": "active",
                "decision_subject": "agent",
                "branches": [{"on": "failed", "goto": "s-01"}],
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
            },
            {
                "type": "oracle",
                "id": "o-01",
                "label": "품질 평가",
                "status": "active",
                "oracle_type": "metric",
                "criteria": ["score >= 0.8"],
                "branches": [{"on": "failed", "goto": "s-01"}],
            },
        ],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "node-loop-controlled.yaml", doc))
    assert res["ok"], res
    assert res["uncontrolled_loops"] == []


def test_multi_workflow_phase_and_node_uris_are_workflow_scoped(tmp_path):
    """서로 다른 workflow의 동명 phase/node가 RDF 병합에서 충돌하지 않는다."""
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

    phases = {str(s) for s in combined.subjects(wf_to_ttl.RDF.type, wf_to_ttl.WF.Phase)}
    nodes = {str(s) for s in combined.subjects(wf_to_ttl.RDF.type, wf_to_ttl.WF.Step)}

    assert any(uri.endswith("phase/workflow-a/generation") for uri in phases)
    assert any(uri.endswith("phase/workflow-b/generation") for uri in phases)
    assert any(uri.endswith("node/workflow-a/s-010") for uri in nodes)
    assert any(uri.endswith("node/workflow-b/s-010") for uri in nodes)
    assert len([uri for uri in phases if uri.endswith("/generation")]) == 2
    assert len([uri for uri in nodes if uri.endswith("/s-010")]) == 2


def test_depends_on_undeclared_phase_fails_range(tmp_path):
    """dependsOn 타깃이 선언된 Phase 가 아니면 sh:class wf:Phase 위반(dangling ref)."""
    doc = {"phases": [
        {"id": "a", "name": "A", "status": "active", "dependencies": ["ghost"]},
    ]}
    res = wf_to_ttl.validate(_write(tmp_path, "dangling.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False


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
                   "decision_criteria": "F1 < 0.87"}],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "subject_ok.yaml", doc))
    assert res["ok"], res


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
            "deliverables": ["table:labels"],
        }],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "good_tool.yaml", doc))
    assert res["ok"], res


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
    doc = {"phases": [
        {"id": "a", "name": "A", "status": "active", "dependencies": ["b"]},
        {"id": "b", "name": "B", "status": "active", "dependencies": ["a"]},
    ]}
    p = _write(tmp_path, "c.yaml", doc)
    out = subprocess.run(
        [sys.executable, str(_SCRIPTS / "wf_to_ttl.py"), "validate", str(p)],
        capture_output=True, text=True,
    )
    assert out.returncode == 1
    assert "uncontrolled feedback loop" in out.stdout
