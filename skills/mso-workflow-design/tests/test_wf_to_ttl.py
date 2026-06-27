"""wf_to_ttl 테스트 — YAML→TTL 투영 + 비순환성(SPARQL) + 로컬 shape(SHACL).

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


def test_real_root_template_is_acyclic_and_conforms():
    """배포 root-workflow 템플릿은 비순환 + 로컬 shape 통과해야 한다(회귀 가드)."""
    res = wf_to_ttl.validate(_ASSETS / "root-workflow-template.yaml")
    assert res["ok"], res
    assert res["cycles"] == []
    assert res["shacl_conforms"]


# ─── 비순환성 (헤드라인: 다운스트림 재참조 = 오류) ───

def test_cycle_is_detected(tmp_path):
    doc = {
        "phases": [
            {"id": "a", "name": "A", "status": "active", "dependencies": ["c"]},
            {"id": "b", "name": "B", "status": "active", "dependencies": ["a"]},
            {"id": "c", "name": "C", "status": "active", "dependencies": ["b"]},
        ]
    }
    res = wf_to_ttl.validate(_write(tmp_path, "cyclic.yaml", doc))
    assert res["ok"] is False
    assert len(res["cycles"]) >= 1
    assert any(u.endswith(("phase/a", "phase/b", "phase/c")) for u in res["cycles"])


def test_critical_dep_cycle_detected(tmp_path):
    """critical_dependencies 의 from→to 도 비순환성 검사 대상."""
    doc = {
        "phases": [{"id": "p", "name": "P", "status": "active"}],
        "critical_dependencies": [
            {"from": "m1", "to": "m2"},
            {"from": "m2", "to": "m1"},
        ],
    }
    res = wf_to_ttl.validate(_write(tmp_path, "cd.yaml", doc))
    assert res["ok"] is False
    assert len(res["cycles"]) >= 1


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


def test_bad_judge_enum_fails(tmp_path):
    """decision judge 가 4-level 통제어휘 밖이면 위반."""
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "decision", "id": "p-d-01", "label": "분기",
                   "status": "active", "judge": "MAYBE"}],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "judge.yaml", doc))
    assert res["ok"] is False
    assert res["shacl_conforms"] is False


def test_good_decision_judge_conforms(tmp_path):
    # HITLFE → owner(required_when HITL/HITLFE) + threshold(required_when HITLFE) 필수
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "decision", "id": "p-d-01", "label": "분기",
                   "status": "active", "judge": "HITLFE",
                   "owner": "team@x", "threshold": "F1 < 0.87"}],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "judge_ok.yaml", doc))
    assert res["ok"], res


def test_decision_hitlfe_missing_owner_threshold_fails(tmp_path):
    """required_when: HITLFE 인데 owner/threshold 없으면 위반(생성된 조건부 shape)."""
    doc = {"phases": [{
        "id": "p", "name": "P", "status": "active",
        "steps": [{"type": "decision", "id": "p-d-01", "label": "분기",
                   "status": "active", "judge": "HITLFE"}],
    }]}
    res = wf_to_ttl.validate(_write(tmp_path, "judge_bad.yaml", doc))
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
                   "judge": "HOTL", "branches": [{True: "passed", "goto": "n2"}]}],
    }]}
    g, _ = wf_to_ttl.build_graph(_write(tmp_path, "wf.yaml", doc))
    nu = wf_to_ttl._node_uri("p-d-01")
    bn = list(g.objects(nu, wf_to_ttl.WF.hasBranch))
    assert len(bn) == 1
    assert str(next(g.objects(bn[0], wf_to_ttl.WF.on))) == "passed"


def test_cli_validate_exit_code_on_cycle(tmp_path):
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
    assert "사이클" in out.stdout
