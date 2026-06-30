#!/usr/bin/env python3
"""schemas_to_tbox — references/schemas/*.yaml 에서 TBox 온톨로지 + SHACL shapes 생성.

설계 (§ schemas = SSOT, 2026-06-17):
  노드 구조의 단일 진실원은 references/schemas/*.yaml 이다. TBox(workflow-tbox.ttl)와
  SHACL(workflow-shapes.ttl)은 그로부터 *생성*된 파생물 — 손으로 동기화하지 않는다(drift 0).
  schemas 의 기계가독 부분만 변환한다:
    type            → owl:Class (step/decision/group/eval ⊂ Node)
    required:true   → sh:minCount 1
    type:enum       → sh:in (values)
    type:string|bool→ sh:datatype xsd:string|boolean
    items:node      → sh:class (object property)
    required_when   → sh:or ( [sh:not 조건] [필드 present] )  조건부 제약

생성 불가 → 별도 유지:
  - 산문 structural_invariants(예: "id unique", "steps 또는 workflows 필수")
  - branch.on 의 domain-specific routing vocabulary — TODO 주석만
  - feedback loop 통제(Eval 개입점)·교차-스킬(scaffold)·anchor 정합 → wf_to_ttl.py/SHACL-SPARQL

schema 없는 root-그래프 층(root-workflow 템플릿 개념: workflows[], critical_dependencies,
milestones)은 _GRAPH_OVERLAY 에 명시한다 — 정직하게 "스키마 없음" 표기.

사용:  python schemas_to_tbox.py           # 두 파일 생성(덮어쓰기)
       python schemas_to_tbox.py --check  # 생성결과가 현재 파일과 같은지만 확인(CI drift 가드)
"""
import argparse
import sys
from pathlib import Path

import yaml

_DIR = Path(__file__).resolve().parent
SCHEMAS = _DIR.parent / "references" / "schemas"
TBOX_OUT = _DIR.parent / "references" / "tbox" / "workflow-tbox.ttl"
SHAPES_OUT = _DIR.parent / "references" / "shapes" / "workflow-shapes.ttl"

NS = "https://mso.dev/ontology/workflow#"

# type → 클래스명. Node 하위 = 실행 노드. branch 는 독립.
_CLASS = {"step": "Step", "decision": "Decision",
          "eval": "Eval",
          "group": "Group", "branch": "Branch"}
_NODE_SUB = {"Step", "Decision", "Group", "Eval"}

# 직접 property 로 만들지 않는 필드(클래스 타입·식별자·컨테이너·복합).
#   type → rdf:type / id → URI 자체 / steps·workflows → 그래프 층(hasNode/has_subWorkflow)
#   directories → wf:directory bnode(특수, wf_to_ttl 투영) / branches → wf:Branch 특수 투영
_SKIP_FIELDS = {"type", "id", "steps", "workflows", "directories", "branches"}

XSD = {"string": "xsd:string", "bool": "xsd:boolean"}


def _camel(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _load_schemas() -> dict:
    out = {}
    for p in sorted(SCHEMAS.glob("*.schema.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        t = doc.get("type")
        if t in _CLASS:
            out[t] = doc
    return out


# ─── TBox 생성 ────────────────────────────────────────────────────────────────

_TBOX_HEADER = f"""@prefix wf:   <{NS}> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

# ═══════════════════════════════════════════════════════════════════════════════
# !!! 생성물 — 직접 편집 금지. 소스: references/schemas/*.yaml
# !!! 재생성: python scripts/schemas_to_tbox.py
# ═══════════════════════════════════════════════════════════════════════════════

wf: a owl:Ontology ;
    rdfs:label "MSO Workflow Ontology"@ko ;
    rdfs:comment "schemas/*.yaml 에서 생성된 TBox. ABox 는 이 타입에 정합해야 한다."@ko ;
    owl:versionInfo "0.5.0" .
"""

# schema 없는 root-그래프 층(root-workflow 템플릿). 정직하게 분리 표기.
_GRAPH_OVERLAY = """
# ─── 그래프 층 (root-workflow 템플릿 개념 — schema 없음, 여기서 정의) ──────────────
wf:Task a owl:Class ; rdfs:label "Task"@ko ;
    rdfs:comment "실행·생성·검증을 수행하는 업무 노드 관측 상위 개념. Step/Group/WorkflowRef가 task 성격을 가진다. (schema 없음)"@ko .
wf:Module    a owl:Class ; rdfs:label "Module"@ko ;
    rdfs:comment "critical_dependencies 의 from/to 단위. (schema 없음)"@ko .
wf:Milestone a owl:Class ; rdfs:label "Milestone"@ko ;
    rdfs:comment "특정 Workflow/sub-workflow 를 가리키는 마일스톤. (schema 없음)"@ko .

wf:criticalDep a owl:ObjectProperty ; rdfs:label "criticalDep"@ko ;
    rdfs:domain wf:Module ; rdfs:range wf:Module ;
    rdfs:comment "critical_dependencies from→to. 구조 의존 관측 edge."@ko .
wf:milestoneOf a owl:ObjectProperty ; rdfs:label "milestoneOf"@ko ;
    rdfs:domain wf:Milestone ; rdfs:range wf:Workflow .
wf:hasNode a owl:ObjectProperty ; rdfs:label "hasNode"@ko ;
    rdfs:domain wf:Workflow ; rdfs:range wf:Node ;
    rdfs:comment "workflow.steps[] 평탄화 에지. v0.6.1 phase-less 정본 membership."@ko .
wf:inWorkflow a owl:ObjectProperty ; rdfs:label "inWorkflow"@ko ;
    rdfs:domain wf:Node ; rdfs:range wf:Workflow ;
    rdfs:comment "hasNode 의 역방향 membership. self-ref 및 관측 쿼리 편의를 위해 emit."@ko .
wf:next a owl:ObjectProperty ; rdfs:label "next"@ko ;
    rdfs:domain wf:Node ; rdfs:range wf:Node ;
    rdfs:comment "process edge. workflow.steps[] 의 기본 순차 실행 에지. decision branch goto 가 없을 때도 이 edge가 다음 실행 노드를 나타낸다."@ko .
wf:directory a owl:ObjectProperty ; rdfs:label "directory"@ko ;
    rdfs:domain wf:Node ;
    rdfs:comment "step.directories[] 항목. dirRole + dirPath 필수. wf:dirNote 선택. validate_abox.py 검증 대상."@ko .
wf:dirRole a owl:DatatypeProperty ; rdfs:label "dirRole"@ko ; rdfs:range xsd:string ;
    rdfs:comment "directory.role. 필수. 프로젝트 자유 어휘. 일반값: input | output | input_output | reference | instruction. implementation/tool_internal/internal 계열은 artifact stream edge로 해석하지 않는다."@ko .
wf:dirPath a owl:DatatypeProperty ; rdfs:label "dirPath"@ko ; rdfs:range xsd:string ;
    rdfs:comment "directory.path. 필수. 교차-스킬(scaffold) 멤버십 대상."@ko .
wf:dirNote a owl:DatatypeProperty ; rdfs:label "dirNote"@ko ; rdfs:range xsd:string ;
    rdfs:comment "directory 설명 주석. cross-workflow 의존·보안·TTL 힌트 등. 선택."@ko .

# ─── Eval slot-filling 프로퍼티 (schema 없음 — 여기서 직접 정의) ──────────────
wf:EntitySlot a owl:Class ; rdfs:label "EntitySlot"@ko ;
    rdfs:comment "Eval의 개별 슬롯 정의. hasSlot 이 선언된 Eval이 슬롯을 하나씩 채워가며 누적 평가한다. slotFilled 는 null(미평가) → false(미충족) → true(충족) 전이를 갖는다."@ko .
wf:hasSlot a owl:ObjectProperty ; rdfs:label "hasSlot"@ko ;
    rdfs:domain wf:Eval ; rdfs:range wf:EntitySlot ;
    rdfs:comment "Eval → EntitySlot 링크. hasSlot이 선언된 Eval은 slot-filling 방식으로 동작한다."@ko .
wf:slotName a owl:DatatypeProperty ; rdfs:label "slotName"@ko ;
    rdfs:domain wf:EntitySlot ; rdfs:range xsd:string ;
    rdfs:comment "슬롯 식별자 (예: cluster_terms, quality_gate)."@ko .
wf:slotConstraint a owl:DatatypeProperty ; rdfs:label "slotConstraint"@ko ;
    rdfs:domain wf:EntitySlot ; rdfs:range xsd:string ;
    rdfs:comment "슬롯 충족 조건."@ko .
wf:slotFilled a owl:DatatypeProperty ; rdfs:label "slotFilled"@ko ;
    rdfs:domain wf:EntitySlot ; rdfs:range xsd:boolean ;
    rdfs:comment "슬롯 채움 여부. ABox 초기값 false. 평가자가 충족 확인 시 true로 갱신."@ko .

# ─── 구조화 링크 (컨테이너 관계 — schema 필드 아님) ──────────────────────────────
wf:hasBranch a owl:ObjectProperty ; rdfs:label "hasBranch"@ko ;
    rdfs:domain wf:Decision ; rdfs:range wf:Branch ;
    rdfs:comment "decision.branches[] → Branch 노드(라운드트립)."@ko .
wf:gotoNode a owl:ObjectProperty ; rdfs:label "gotoNode"@ko ;
    rdfs:domain wf:Branch ; rdfs:range wf:Node ;
    rdfs:comment "process edge. branch.goto 문자열을 같은 workflow scope의 Node URI로 해석한 조건부 실행 에지."@ko .
# ─── Oracle graph layer (v0.6.0) — workflow 통일 + self-improvement edge ──────
# [[system]] = wf:Workflow. 레이어(base/oracle)는 edge 종류로 파생(노드 type 없음).
wf:Workflow a owl:Class ; rdfs:label "Workflow"@ko ;
    rdfs:comment "graph/sub-graph 단위. v0.6.1 phase-less 정본 컨테이너. sub-workflow(object)·oracle-workflow(meta)=대칭 sub-graph, 역할은 edge 로 파생."@ko .
wf:has_subWorkflow a owl:ObjectProperty ; rdfs:label "has_subWorkflow"@ko ;
    rdfs:domain wf:Workflow ; rdfs:range wf:Workflow ;
    rdfs:comment "workflow 계층 (v0.6.1): 부모 workflow → sub-workflow. lifecycle·모듈·oracle 계층을 모두 이 단일 재귀 edge 로 표현한다."@ko .
wf:delegatesTo a owl:ObjectProperty ; rdfs:label "delegatesTo"@ko ;
    rdfs:domain wf:Task ; rdfs:range wf:Workflow ;
    rdfs:comment "base(수단화): task 가 workflow 에 업무 위임·실행."@ko .
wf:exercises a owl:ObjectProperty ; rdfs:label "exercises"@ko ;
    rdfs:range wf:Workflow ;
    rdfs:comment "oracle(대상): 평가 목적 실행. 대상 불변이라 self-ref 무관."@ko .
wf:evolves a owl:ObjectProperty ; rdfs:label "evolves"@ko ;
    rdfs:domain wf:Workflow ; rdfs:range wf:Workflow ;
    rdfs:comment "oracle-workflow → 대상 workflow 개선/변경. C·W disjoint 강제(EvolvesStratificationShape: 자기/조상/자손 evolve 금지)."@ko .
wf:target a owl:ObjectProperty ; rdfs:label "target"@ko ;
    rdfs:domain wf:Eval ; rdfs:range wf:Workflow ;
    rdfs:comment "oracle: eval 이 가리키는 평가 대상 workflow(참조)."@ko .

# ─── Artifact stream (v0.6.0 SPEC §4①) — supply chain 노드화 ──────────────────
# artifact 를 노드로 승격(기존 targetArtifact string 과 병존) — orphan artifact 탐지·
# supply-chain view 용. workflow 가 produces/consumes 하고, eval 이 measures 한다.
wf:Artifact a owl:Class ; rdfs:label "Artifact"@ko ;
    rdfs:comment "공급망 산출물 노드. produces/consumes/check/measures 의 대상. 기존 targetArtifact(string)와 병존 — 노드 식별이 필요한 supply-chain/orphan 분석용."@ko .
wf:produces a owl:ObjectProperty ; rdfs:label "produces"@ko ;
    rdfs:domain wf:Workflow ; rdfs:range wf:Artifact ;
    rdfs:comment "base(공급망): workflow 가 artifact 생산."@ko .
wf:consumes a owl:ObjectProperty ; rdfs:label "consumes"@ko ;
    rdfs:domain wf:Artifact ; rdfs:range wf:Workflow ;
    rdfs:comment "base(공급망): artifact 가 workflow 입력으로 소비됨."@ko .
wf:check a owl:ObjectProperty ; rdfs:label "check"@ko ;
    rdfs:domain wf:Artifact ; rdfs:range wf:Task ;
    rdfs:comment "base(spine): artifact 가 task 입력으로 진입."@ko .
wf:measures a owl:ObjectProperty ; rdfs:label "measures"@ko ;
    rdfs:domain wf:Artifact ; rdfs:range wf:Eval ;
    rdfs:comment "경계 전환: artifact/result 가 eval 로 측정됨(base→oracle 진입)."@ko .

# ─── narrative/meta 층 (root-workflow 템플릿 개념 — schema 없음, 여기서 정의) ──────
wf:Project a owl:Class ; rdfs:label "Project"@ko ;
    rdfs:comment "root-workflow 메타(project:). name/version/description/owner/created. (schema 없음)"@ko .
wf:KeyDecision a owl:Class ; rdfs:label "KeyDecision"@ko ;
    rdfs:comment "key_decisions[] 항목. decisionText/rationale/impactModule. (schema 없음)"@ko .
wf:SuccessCriterion a owl:Class ; rdfs:label "SuccessCriterion"@ko ;
    rdfs:comment "top-level success_criteria[] (scKey→scValue) 항목. (schema 없음)"@ko .
wf:CriticalDependency a owl:Class ; rdfs:label "CriticalDependency"@ko ;
    rdfs:comment "critical_dependencies[] 항목(서술 포함). from/to 는 wf:criticalDep 에지로도 투영(dual-rep). (schema 없음)"@ko .
wf:MetaBlock a owl:Class ; rdfs:label "MetaBlock"@ko ;
    rdfs:comment "top-level non-workflow 메타 블록(workflow/module/meta/metadata + 소비자 x_* 확장). 임의 중첩 구조를 canonical JSON literal(rawJson)로 무손실 보존. (schema 없음)"@ko .

wf:blockKey a owl:DatatypeProperty ; rdfs:label "blockKey"@ko ; rdfs:domain wf:MetaBlock ; rdfs:range xsd:string ;
    rdfs:comment "메타 블록의 원본 top-level 키(workflow/module/meta/x_msm 등)."@ko .
wf:rawJson a owl:DatatypeProperty ; rdfs:label "rawJson"@ko ; rdfs:domain wf:MetaBlock ; rdfs:range xsd:string ;
    rdfs:comment "메타 블록 원본을 sort_keys canonical JSON 으로 직렬화(무손실·결정적)."@ko .

wf:version a owl:DatatypeProperty ; rdfs:label "version"@ko ; rdfs:domain wf:Project ; rdfs:range xsd:string .
wf:created a owl:DatatypeProperty ; rdfs:label "created"@ko ; rdfs:domain wf:Project ; rdfs:range xsd:string .
wf:decisionText a owl:DatatypeProperty ; rdfs:label "decisionText"@ko ; rdfs:domain wf:KeyDecision ; rdfs:range xsd:string .
wf:rationale a owl:DatatypeProperty ; rdfs:label "rationale"@ko ; rdfs:domain wf:KeyDecision ; rdfs:range xsd:string .
wf:impactModule a owl:DatatypeProperty ; rdfs:label "impactModule"@ko ; rdfs:domain wf:KeyDecision ; rdfs:range xsd:string ;
    rdfs:comment "key_decision.impact_modules[] 항목."@ko .
wf:scKey a owl:DatatypeProperty ; rdfs:label "scKey"@ko ; rdfs:domain wf:SuccessCriterion ; rdfs:range xsd:string .
wf:scValue a owl:DatatypeProperty ; rdfs:label "scValue"@ko ; rdfs:domain wf:SuccessCriterion ; rdfs:range xsd:string .
wf:cdFrom a owl:DatatypeProperty ; rdfs:label "cdFrom"@ko ; rdfs:domain wf:CriticalDependency ; rdfs:range xsd:string .
wf:cdTo a owl:DatatypeProperty ; rdfs:label "cdTo"@ko ; rdfs:domain wf:CriticalDependency ; rdfs:range xsd:string .
wf:milestoneDate a owl:DatatypeProperty ; rdfs:label "milestoneDate"@ko ; rdfs:domain wf:Milestone ; rdfs:range xsd:string .

# 통제어휘 (skos)
wf:DecisionSubjectScheme a skos:ConceptScheme ; skos:prefLabel "Decision Subjects"@ko .
wf:user a skos:Concept ; skos:inScheme wf:DecisionSubjectScheme ; skos:notation "user" .
wf:agent a skos:Concept ; skos:inScheme wf:DecisionSubjectScheme ; skos:notation "agent" .
"""


def gen_tbox(schemas: dict) -> str:
    lines = [_TBOX_HEADER]
    lines.append("\n# ─── 클래스 (schema type) ──────────────────────────────────────────────────────")
    lines.append("wf:Node a owl:Class ; rdfs:label \"Node\"@ko ; rdfs:comment \"실행 노드 상위.\"@ko .")
    # 속성→사용 클래스 집계 (domain 결정: 유일 클래스면 domain, 공유면 생략)
    prop_classes: dict[str, set] = {}
    prop_range: dict[str, str] = {}
    for t, doc in schemas.items():
        for fname, spec in (doc.get("fields") or {}).items():
            if fname in _SKIP_FIELDS or not isinstance(spec, dict):
                continue
            pname = _camel(fname)
            prop_classes.setdefault(pname, set()).add(_CLASS[t])
            items = spec.get("items")
            if items in ("node",):
                prop_range[pname] = "wf:Node"
            else:
                prop_range[pname] = XSD.get(spec.get("type"), "xsd:string")

    for t in sorted(schemas, key=lambda x: _CLASS[x]):
        cls = _CLASS[t]
        doc = schemas[t]
        sub = " ; rdfs:subClassOf wf:Node" if cls in _NODE_SUB else ""
        inv = doc.get("structural_invariants") or []
        invc = " ".join(str(i).replace('"', "'") for i in inv)
        lines.append(f'wf:{cls} a owl:Class{sub} ; rdfs:label "{cls}"@ko ;')
        lines.append(f'    rdfs:comment "{doc.get("description","").strip().replace(chr(10)," ")} | invariants: {invc}"@ko .')

    lines.append("\n# ─── Property (schema fields) ──────────────────────────────────────────────────")
    for pname in sorted(prop_classes):
        rng = prop_range[pname]
        is_obj = rng.startswith("wf:")
        ptype = "owl:ObjectProperty" if is_obj else "owl:DatatypeProperty"
        classes = sorted(prop_classes[pname])
        dom = f" ; rdfs:domain wf:{classes[0]}" if len(classes) == 1 else ""
        usedby = "" if len(classes) == 1 else f' ; rdfs:comment "used by: {", ".join(classes)}"@ko'
        lines.append(f"wf:{pname} a {ptype} ; rdfs:label \"{pname}\"@ko{dom} ; rdfs:range {rng}{usedby} .")

    lines.append(_GRAPH_OVERLAY)
    return "\n".join(lines).rstrip() + "\n"


# ─── SHACL 생성 ───────────────────────────────────────────────────────────────

_SHAPES_HEADER = """@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix wf:   <{ns}> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

# ═══════════════════════════════════════════════════════════════════════════════
# !!! 생성물 — 직접 편집 금지. 소스: references/schemas/*.yaml
# !!! 재생성: python scripts/schemas_to_tbox.py
# feedback loop control 은 SHACL-SPARQL constraint, 교차-스킬·branch.on 유효성은 wf_to_ttl.py SPARQL/prose.
# ═══════════════════════════════════════════════════════════════════════════════
""".format(ns=NS)

# 그래프 층 range-class 제약(schema 없음).
_SHAPES_OVERLAY = """
# ─── 그래프 층 range (schema 없음) ──────────────────────────────────────────────
wf:WorkflowGraphShape a sh:NodeShape ; sh:targetClass wf:Workflow ;
    sh:property [ sh:path wf:hasNode ; sh:class wf:Node ;
                  sh:message "hasNode 타깃은 wf:Node 여야 함" ] ;
    sh:property [ sh:path wf:has_subWorkflow ; sh:class wf:Workflow ;
                  sh:message "has_subWorkflow 타깃은 wf:Workflow 여야 함" ] .
wf:NodeGraphShape a sh:NodeShape ; sh:targetClass wf:Node ;
    sh:property [ sh:path wf:next ; sh:class wf:Node ;
                  sh:message "next 타깃은 wf:Node 여야 함" ] ;
    sh:property [ sh:path wf:inWorkflow ; sh:class wf:Workflow ;
                  sh:message "inWorkflow 타깃은 wf:Workflow 여야 함" ] .
wf:ToolDelegationShape a sh:NodeShape ; sh:targetClass wf:Step ;
    sh:sparql [
        sh:message "tool delegation shape: wf:usesTool step needs a consumable input/reference artifact so artifact --consumes--> tool can be rendered" ;
        sh:select \"\"\"
            PREFIX wf: <https://mso.dev/ontology/workflow#>
            SELECT $this WHERE {
              $this wf:usesTool ?tool .
              FILTER NOT EXISTS {
                $this wf:directory ?dir .
                ?dir wf:dirPath ?path .
                OPTIONAL { ?dir wf:dirRole ?role . }
                FILTER(
                  !BOUND(?role)
                  || CONTAINS(LCASE(STR(?role)), "input")
                  || CONTAINS(LCASE(STR(?role)), "reference")
                  || CONTAINS(LCASE(STR(?role)), "instruction")
                  || LCASE(STR(?role)) IN ("staging", "read")
                )
              }
            }
        \"\"\" ;
    ] ;
    sh:sparql [
        sh:message "tool delegation shape: wf:usesTool step needs an output/deliverable artifact so tool --produces--> artifact can be rendered" ;
        sh:select \"\"\"
            PREFIX wf: <https://mso.dev/ontology/workflow#>
            SELECT $this WHERE {
              $this wf:usesTool ?tool .
              FILTER NOT EXISTS {
                { $this wf:deliverables ?deliverable . }
                UNION
                {
                  $this wf:directory ?dir .
                  ?dir wf:dirPath ?path .
                  ?dir wf:dirRole ?role .
                  FILTER(
                    CONTAINS(LCASE(STR(?role)), "output")
                    || LCASE(STR(?role)) IN ("staging", "generated", "write")
                  )
                }
              }
            }
        \"\"\" ;
    ] .
wf:EvalToolTargetShape a sh:NodeShape ; sh:targetClass wf:Eval ;
    sh:sparql [
        sh:message "eval tool target shape: tool/process target must have a producer step with output/deliverable artifacts so produced artifact --validated_by--> Eval can be rendered" ;
        sh:select \"\"\"
            PREFIX wf: <https://mso.dev/ontology/workflow#>
            SELECT $this WHERE {
              $this wf:targetArtifact ?tool .
              FILTER(
                CONTAINS(LCASE(STR(?tool)), "process")
                || CONTAINS(LCASE(STR(?tool)), "tool")
                || CONTAINS(LCASE(STR(?tool)), "processing artifact")
              )
              FILTER NOT EXISTS {
                ?producer a wf:Step ;
                          wf:usesTool ?tool .
                {
                  ?producer wf:deliverables ?deliverable .
                }
                UNION
                {
                  ?producer wf:directory ?dir .
                  ?dir wf:dirPath ?path .
                  ?dir wf:dirRole ?role .
                  FILTER(
                    CONTAINS(LCASE(STR(?role)), "output")
                    || LCASE(STR(?role)) IN ("staging", "generated", "write")
                  )
                }
              }
            }
        \"\"\" ;
    ] .
wf:EvalRevisionTargetShape a sh:NodeShape ; sh:targetClass wf:Eval ;
    sh:sparql [
        sh:message "eval revision shape: tool/process Eval.orderTarget must point to a remediation Step with the same wf:targetArtifact" ;
        sh:select \"\"\"
            PREFIX wf: <https://mso.dev/ontology/workflow#>
            SELECT $this WHERE {
              $this wf:targetArtifact ?tool ;
                    wf:orderTarget ?order .
              FILTER(
                CONTAINS(LCASE(STR(?tool)), "process")
                || CONTAINS(LCASE(STR(?tool)), "tool")
                || CONTAINS(LCASE(STR(?tool)), "processing artifact")
              )
              FILTER NOT EXISTS {
                ?targetStep a wf:Step ;
                            wf:targetArtifact ?tool .
                FILTER(REPLACE(STR(?targetStep), "^.*/", "") = STR(?order))
              }
            }
        \"\"\" ;
    ] .
wf:DecisionGraphShape a sh:NodeShape ; sh:targetClass wf:Decision ;
    sh:property [ sh:path wf:hasBranch ; sh:class wf:Branch ;
                  sh:message "hasBranch 타깃은 wf:Branch 여야 함" ] .
wf:BranchGraphShape a sh:NodeShape ; sh:targetClass wf:Branch ;
    sh:property [ sh:path wf:gotoNode ; sh:class wf:Node ;
                  sh:message "gotoNode 타깃은 wf:Node 여야 함" ] .
wf:ModuleGraphShape a sh:NodeShape ; sh:targetClass wf:Module ;
    sh:property [ sh:path wf:criticalDep ; sh:class wf:Module ;
                  sh:message "criticalDep 타깃은 wf:Module 여야 함" ] .
wf:MilestoneGraphShape a sh:NodeShape ; sh:targetClass wf:Milestone ;
    sh:property [ sh:path wf:milestoneOf ; sh:class wf:Workflow ;
                  sh:message "milestoneOf 타깃은 wf:Workflow(sub-workflow) 여야 함" ] .

# ─── Feedback loop control constraints (SHACL-SPARQL) ────────────────────────
wf:NodeFeedbackLoopShape a sh:NodeShape ; sh:targetClass wf:Node ;
    sh:sparql [
        sh:message "uncontrolled node feedback loop: wf:next/branch cycle has no Eval gate in the loop" ;
        sh:select \"\"\"
            PREFIX wf: <https://mso.dev/ontology/workflow#>
            SELECT $this WHERE {
              $this (wf:next|wf:hasBranch/wf:gotoNode)+ $this .
              FILTER NOT EXISTS {
                $this (wf:next|wf:hasBranch/wf:gotoNode)* ?eval .
                ?eval a wf:Eval .
                ?eval (wf:next|wf:hasBranch/wf:gotoNode)* $this .
              }
            }
        \"\"\" ;
    ] .

# ─── Oracle self-improvement constraint (v0.6.0 oracle graph invariant I) ─────
# evolves 는 system 을 변경하므로 self-reference 위험이 있다(exercises/delegatesTo 는
# system 불변이라 무관). 행위 주체가 자기 소속 workflow 를 직접 evolves 하면 위반.
# TODO(v0.6.0): workflowRef 조상 체인까지 확장 — 현재 wf:ref 는 file#anchor 문자열이라
#   그래프 edge resolve(wf_to_ttl 의 cross-skill 단계)가 선행돼야 transitive 검사가 된다.
# I-stratification: oracle-workflow C 와 대상 W 는 disjoint 여야 한다.
# C 가 자기(zero-length)·조상·자손 workflow 를 evolve 하면 위반. has_subWorkflow* 가
# 양방향(C→W, W→C)으로 연결되면 disjoint 가 아니다. (직접 self-ref 는 zero-length 로 포함.)
wf:EvolvesStratificationShape a sh:NodeShape ; sh:targetSubjectsOf wf:evolves ;
    sh:sparql [
        sh:message "evolves stratification 위반: oracle-workflow 와 evolve 대상은 disjoint 여야 함(자기/조상/자손 evolve 금지)" ;
        sh:select \"\"\"
            PREFIX wf: <https://mso.dev/ontology/workflow#>
            SELECT $this ?w WHERE {
              $this wf:evolves ?w .
              { $this wf:has_subWorkflow+ ?w } UNION { ?w wf:has_subWorkflow+ $this }
            }
        \"\"\" ;
    ] .
wf:EvolvesSelfShape a sh:NodeShape ; sh:targetSubjectsOf wf:evolves ;
    sh:sparql [
        sh:message "self-evolve 위반: workflow 가 자기 자신을 evolve 함 (C∩W=∅ 위배, 직접 케이스)" ;
        sh:select \"\"\"
            PREFIX wf: <https://mso.dev/ontology/workflow#>
            SELECT $this WHERE { $this wf:evolves $this }
        \"\"\" ;
    ] .
# I-partition: has_subWorkflow 형제는 disjoint — 한 workflow 는 부모가 최대 1개.
# (이로써 W_i/W_j 및 그 oracle C_i/C_j 노드 disjoint 가 강제된다.)
wf:SubWorkflowPartitionShape a sh:NodeShape ; sh:targetObjectsOf wf:has_subWorkflow ;
    sh:sparql [
        sh:message "has_subWorkflow 파티션 위반: 한 workflow 가 둘 이상의 부모에 속함(형제 disjoint 위배)" ;
        sh:select \"\"\"
            PREFIX wf: <https://mso.dev/ontology/workflow#>
            SELECT $this ?p1 ?p2 WHERE {
              ?p1 wf:has_subWorkflow $this .
              ?p2 wf:has_subWorkflow $this .
              FILTER(?p1 != ?p2)
            }
        \"\"\" ;
    ] .
"""


def _prop_shape(fname: str, spec: dict) -> str:
    pname = _camel(fname)
    parts = [f"sh:path wf:{pname}"]
    if spec.get("required") is True:
        parts.append("sh:minCount 1")
    if spec.get("type") == "enum" and spec.get("values"):
        vals = " ".join(f'"{v}"' for v in spec["values"])
        parts.append(f"sh:in ( {vals} )")
    elif spec.get("type") in XSD and spec.get("type") != "enum":
        parts.append(f"sh:datatype {XSD[spec['type']]}")
    elif spec.get("items") == "node":
        parts.append("sh:class wf:Node")
    msg = f'sh:message "{pname}: schema 제약 위반"'
    parts.append(msg)
    return "[ " + " ; ".join(parts) + " ]"


def _required_when(fname: str, spec: dict) -> str | None:
    """required_when:{field,values} → sh:or ( [sh:not(field in values)] [thisfield present] )."""
    rw = spec.get("required_when")
    if not rw or "field" not in rw or "values" not in rw:
        return None
    pname = _camel(fname)
    cond_field = _camel(rw["field"])
    vals = " ".join(f'"{v}"' for v in rw["values"])
    return (
        "sh:or (\n"
        f"        [ sh:not [ sh:property [ sh:path wf:{cond_field} ; sh:in ( {vals} ) ; sh:minCount 1 ] ] ]\n"
        f"        [ sh:property [ sh:path wf:{pname} ; sh:minCount 1 ] ]\n"
        "    )"
    )


def gen_shapes(schemas: dict) -> str:
    lines = [_SHAPES_HEADER]
    # status enum 은 여러 클래스 공통 → targetSubjectsOf 한 번.
    lines.append("""
wf:StatusShape a sh:NodeShape ; sh:targetSubjectsOf wf:status ;
    sh:property [ sh:path wf:status ; sh:minCount 1 ;
                  sh:in ( "completed" "active" "pending" ) ;
                  sh:message "status 는 completed|active|pending 중 하나" ] .""")
    for t in sorted(schemas, key=lambda x: _CLASS[x]):
        cls = _CLASS[t]
        doc = schemas[t]
        props, ors = [], []
        for fname, spec in (doc.get("fields") or {}).items():
            if fname in _SKIP_FIELDS or not isinstance(spec, dict):
                continue
            if fname == "status":
                continue  # StatusShape 가 전담
            # 단순 제약이 하나도 없으면(선택+무타입) 생략
            has_constraint = (spec.get("required") is True or spec.get("type") == "enum"
                              or spec.get("type") in XSD or spec.get("items") in ("node",))
            if has_constraint:
                props.append(_prop_shape(fname, spec))
            ow = _required_when(fname, spec)
            if ow:
                ors.append(ow)
        if not props and not ors:
            continue
        lines.append(f"\nwf:{cls}Shape a sh:NodeShape ; sh:targetClass wf:{cls} ;")
        body = []
        for p in props:
            body.append(f"    sh:property {p}")
        for o in ors:
            body.append(f"    {o}")
        lines.append(" ;\n".join(body) + " .")
    lines.append(_SHAPES_OVERLAY)
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="schemas_to_tbox")
    ap.add_argument("--check", action="store_true",
                    help="생성결과가 현재 파일과 동일한지만 확인(다르면 exit 1, drift 가드)")
    args = ap.parse_args(argv)

    schemas = _load_schemas()
    tbox, shapes = gen_tbox(schemas), gen_shapes(schemas)

    if args.check:
        drift = []
        for path, gen in ((TBOX_OUT, tbox), (SHAPES_OUT, shapes)):
            cur = path.read_text(encoding="utf-8") if path.exists() else ""
            if cur != gen:
                drift.append(path.name)
        if drift:
            print(f"✗ drift: {drift} — schemas 와 불일치. `python schemas_to_tbox.py` 재생성 필요", file=sys.stderr)
            return 1
        print("✓ TBox/SHACL 가 schemas 와 동기 상태")
        return 0

    TBOX_OUT.write_text(tbox, encoding="utf-8")
    SHAPES_OUT.write_text(shapes, encoding="utf-8")
    print(f"생성: {TBOX_OUT.name}, {SHAPES_OUT.name} (소스 {len(schemas)} schemas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
