---
name: mso-workflow-topology-design
description: |
  Goal → Workflow Topology 설계 또는 Graph Search로 기존 워크플로우 로딩.
  Mode A: Goal → DQ 분해 → RSV 추정 → Motif 식별 → Vertex Composition → Task Graph 설계 (신규).
  Mode B: Intent → Graph Search → Topology Retrieval → Vertex Binding (기존 워크플로우 로딩).
  Use when a goal must be translated into an executable task graph with explicit outputs,
  or when an intent needs to be matched to an existing workflow from the registry.
---

# mso-workflow-topology-design

> 이 스킬은 리포트를 생성하지 않는다.
> **"그래프 구조(Topology) + 노드 명세"**를 설계하거나 기존 워크플로우 레지스트리에서 로딩하여
> `{workspace}/.mso-context/active/<run_id>/10_topology/workflow_topology_spec.json`으로 반환한다.

---

## 실행 모드 선택

| 조건 | 모드 |
|------|------|
| 유사한 워크플로우가 레지스트리에 있고 similarity ≥ 0.6 | **Mode B: Graph Search Loader** |
| 레지스트리 없음 / 유사 워크플로우 없음 / 신규 설계 명시 | **Mode A: 신규 설계 (5-Phase)** |

**when_unsure**: 레지스트리 존재 시 Mode B를 먼저 시도하고, 실패하면 Mode A로 fallback.

---

## 핵심 정의

| 개념 | 정의 |
|------|------|
| **Task Node** | 외부에서 관측 가능한 Explicit Output으로 정의되는 작업 단위 |
| **θ_GT band** | 노드 출력이 허용하는 의미적 분산도 (narrow/moderate/wide) |
| **RSV** | Goal 달성에 필요한 의미 기여 총량 = Σ(DQ_weight) |
| **DQ** | Decision Question. RSV의 기본 단위. 닫히면 Goal에 의미 기여 완료 |
| **Topology Motif** | 반복적으로 나타나는 구조 패턴 (Chain/Star/Fork-Join/Loop/Diamond/Switch) |
| **Vertex** | Task Node의 실행 단위 유형 (Agent/Skill/Tool/Model) |

---

## Mode B: Graph Search Loader (기존 워크플로우 로딩)

> 워크플로우를 직접 설계하지 않고 레지스트리 검색으로 불러온다. 결과는 Mode A와 동일한 스키마로 반환.

### Phase G1: Intent Embedding + Graph Search

1. Intent 문장과 domain_tags를 받는다
2. Intent를 임베딩하여 레지스트리에서 유사도 검색 수행
3. search_results 상위 K개 반환 (코사인 유사도 + domain_tag 일치 + success_rate 가중치)

**검색 스크립트:**
```
python3 {mso-workflow-topology-design}/scripts/graph_search.py \
  --intent "<intent>" --domain-tags "<tag1,tag2>" --top-k 3 \
  --registry ~/.mso-registry/workflows/workflow_registry.json \
  --fallback-registry {workspace}/.mso-context/workflow_registry.json
```

**Registry 해석 순서:**
1. `~/.mso-registry/workflows/workflow_registry.json` (글로벌)
2. `{workspace}/.mso-context/workflow_registry.json` (워크스페이스 로컬)

**선택 점수:** `score = similarity_score × 0.6 + success_rate × 0.4`

**when_unsure**: 상위 2개 score 차이 < 0.05 → 두 후보를 사용자에게 제시.

**산출물**: `search_results[{ workflow_id, motif, similarity_score, metrics }]`

---

### Phase G2: Vertex Binding

1. 검색된 Topology의 각 노드에 실제 실행 가능한 Vertex 매핑
   - `agent` → 현재 환경 사용 가능한 Agent
   - `skill` → `{workspace}/.mso-context/available_skills.json`
   - `tool` → 현재 세션 Tool 목록
   - `model` → `configs/model-catalog.yaml`
2. 바인딩 실패 Vertex는 `unbound_vertices[]`로 기록

**Fallback 조건 (→ Mode A 진입):**
- `unbound_vertices` 존재
- similarity_score < 0.6

**산출물**: `bound_workflow { nodes[], edges[], unbound_vertices[] }`

---

### Phase G3: Executable Workflow 반환

Mode A와 동일한 스키마로 반환. `source: graph_search_loader` 필드로 구분.

```json
{
  "source": "graph_search_loader",
  "source_workflow_id": "<retrieved_workflow_id>",
  "metadata": {
    "motif": "...",
    "retrieved_at": "",
    "similarity_score": 0.0,
    "original_intent": ""
  }
}
```

**레지스트리 등록 (신규 워크플로우):**
```
python3 {mso-workflow-topology-design}/scripts/registry_upsert.py \
  --workflow-spec <path> --intent "<intent>" \
  --registry ~/.mso-registry/workflows/workflow_registry.json \
  --fallback-registry {workspace}/.mso-context/workflow_registry.json
```

---

## Mode A: 신규 설계 (5-Phase)

### Phase 1: Goal → DQ 분해 → RSV_total

1. Goal 문장을 받는다
2. "이 Goal을 달성하려면 어떤 질문들에 답해야 하는가?" → DQ 목록 도출
3. 각 DQ에 weight 부여 → **RSV_total = Σ(weight)**
4. 제약 조건/컨텍스트 확인

**when_unsure**: Goal이 모호하면 핵심 DQ 3개를 예시로 제안하고 사용자에게 구체화 요청.

**산출물**: `decision_questions[]`, `rsv_total`

### Phase 2: Topology 선택 (3-Signal 규칙)

**Topology Motif 식별:**

Topology 선택 전 해당 워크플로우가 어느 Motif(Chain/Star/Fork-Join/Loop/Diamond/Switch)에 해당하는지 먼저 식별하고 `topology_type`으로 변환한다.
→ Motif 정의·매핑·구분 기준: [modules/module.motif-vocabulary.md](modules/module.motif-vocabulary.md)

**5가지 Topology 유형:**

| type | 구조 | 적합 상황 |
|------|------|----------|
| `linear` | A→B→C | 사실확인, 정답 좁음, RSV 작음 |
| `fan_out` | A→{B1,B2,B3} | 다각도 독립 조사 |
| `fan_in` | {B1,B2,B3}→C | 의도적 발산→합성 |
| `dag` | 비선형 다중 의존 | 복합 의존 관계, 재귀 분해 |
| `loop` | A→B→C→A (조건부) | 반복 개선, HITL 피드백 |

**Signal 1 — Goal 성격 → 기본 후보:**
- 사실확인/규정준수 → `linear`
- 다각도 조사 → `fan_out`
- 발산→합성 → `fan_in`
- 상위→하위 재귀 분해 → `dag`
- 반복 개선 → `loop`

**Signal 2 — SE(Semantic Entropy) 분포 → 보정:**
- 고SE 초반 집중 → `fan_out` 보강
- 고SE 합류 집중 → `fan_in`
- 중간 분기 → `dag`

**Signal 3 — RSV 크기 → 병렬성/계층성 보정:**
- RSV 작음 → `linear`로 충분
- RSV 중간 → `fan_out` + 1회 synthesis
- RSV 큼 → `dag` + 다단 synthesis

**when_unsure**: 후보 2개 이상 동점 → 트레이드오프를 `selection_rationale`에 기록하고 사용자 선택 요청.

**산출물**: `topology_type`, `rationale[]`

### Phase 3: Task Graph 설계

**노드 분리 3-규칙:**

| 규칙 | 판단 |
|------|------|
| **Explicit Output 단위** | Output을 외부에서 독립 검증 가능? → 노드 정당 |
| **합치기** | 두 Output이 항상 함께 생성? → 합치기 |
| **분리 유지** | Output이 다른 노드의 Input? → 분리 유지 |

**θ_GT band 설정:**

| SE 예상 | θ_GT | 비고 |
|---------|------|------|
| 해석 자유도 큼 | wide (0.4~0.9) | 다양성 허용 |
| 기준 명확 | narrow (0.0~0.2) | 수렴 보장 |
| 중복 증산 위험 | narrow + Output 스키마 강화 | 구조로 통제 |

**RSV 분배:**
- 각 노드는 "어떤 DQ를 닫는가" 명시 (`assigned_dqs`)
- Σ(rsv_target) ≈ RSV_total (±10% 허용)

**Vertex Composition:**

각 노드에 실행 단위 유형(`vertex_type`: agent/skill/tool/model)을 지정한다.
→ 유형별 선택 기준: [modules/module.vertex-composition.md](modules/module.vertex-composition.md)

**when_unsure**: θ_GT 추정이 불확실 → band를 넓게 + "첫 반복 후 보정 권장" 기록.

**산출물**: `nodes[]`, `edges[]`

### Phase 4: 위험 분석 + Hand-off

**병리적 루프 5종:**

| 유형 | 신호 | mitigation |
|------|------|-----------|
| Redundancy Accumulation | Output 길이↑, 새 DQ 없음 | Output 스키마 강화, 길이 cap |
| Semantic Dependency Cycle | 순환 의존 | DAG 검증 → 합치기 또는 Synthesis 삽입 |
| RSV Inflation | 전 노드 완료 후 RSV 미충족 | DQ 재정의, Goal 분할 |
| Human-Deferral Loop | 판단 계속 미뤄짐 | gate에 판단 기준 명시 |
| Exploration Spiral | diverge 후 수렴 불가 | max_axes 5, 직교성 체크 |

**Hand-off 원칙:**
- 넘기는 것은 "요약"이 아니라 **"결정 가능한 구조"**
- 허용: Decision Memo, Constraint List, DQ Status
- 금지: 산문형 요약, "참고용" 리포트

**산출물**: `loop_risk_assessment[]`, hand-off 포맷 결정

### Phase 5: Workflow Spec JSON 산출

Phase 1~4를 통합하여 `{workspace}/.mso-context/active/<run_id>/10_topology/workflow_topology_spec.json` 생성.

**필수 top-level 키** (스키마 준수):

- `run_id`, `nodes[]` (id, label, vertex_type, theta_gt_band, rsv_target, assigned_dqs, stop_condition, explicit_output), `edges[]`
- `topology_type`, `rsv_total`, `strategy_gate`
- `metadata` (created_at, goal_preview, motif, motif_composition)
- `decision_questions[]`, `loop_risk_assessment[]`, `execution_policy`

상세 필드 정의: [schemas/workflow_topology_spec.schema.json](schemas/workflow_topology_spec.schema.json)

**산출물 경로**: `{workspace}/.mso-context/active/<run_id>/10_topology/workflow_topology_spec.json`

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| ↔ | `mso-mental-model-design` | 상호보완: topology가 노드 구조를 결정하면 mental-model이 chart를 매핑하고, 반대로 domain constraint가 노드 경계를 정제 |
| → | `mso-execution-design` | CC-01: topology_spec.nodes[].id가 exec의 node_chart_map key로 사용됨 |
| ← | `mso-observability` | 환류: loop risk 개선 제안 반영 대상 (사용자 승인 필요) |
| ← | `mso-task-context-management` | 선택적 참조: 반복/가시화 필요 시 topology 참조 |
| ← | `mso-workflow-optimizer` | Level 변경 시 Mode B 레지스트리 execution_metrics 갱신 |

---

## 상세 파일 참조 (필요 시에만)

대부분의 설계 작업은 위 5-Phase만으로 완료 가능하다.

| 상황 | 파일 |
|------|------|
| Topology 유형별 상세 비교 | [modules/module.topology-selection.md](modules/module.topology-selection.md) |
| 노드 분리/Output 스키마 강화 | [modules/module.node_design.md](modules/module.node_design.md) |
| 루프 위험 분석 상세 | [modules/module.loop_risk.md](modules/module.loop_risk.md) |
| Hand-off 포맷/패턴 | [modules/module.handoff.md](modules/module.handoff.md) |
| 출력 스키마 검증 | [schemas/workflow_topology_spec.schema.json](schemas/workflow_topology_spec.schema.json) |
| Topology 자동 생성 | `python3 {mso-workflow-topology-design}/scripts/generate_topology.py --goal "..." --output {workspace}/.mso-context/active/<run_id>/10_topology/workflow_topology_spec.json` |
| 런타임 수렴 측정 | `python3 {mso-workflow-topology-design}/scripts/estimator.py --prev prev.json --curr curr.json` → `theta_gt_actual`, `delta_entropy`, `delta_rsv`, `redundancy` |
| **[Mode B]** 레지스트리 검색 | `python3 {mso-workflow-topology-design}/scripts/graph_search.py --intent "..." --top-k 3 --registry ~/.mso-registry/workflows/workflow_registry.json --fallback-registry {workspace}/.mso-context/workflow_registry.json` |
| **[Mode B]** 레지스트리 등록/갱신 | `python3 {mso-workflow-topology-design}/scripts/registry_upsert.py --workflow-spec <path> --intent "..." --registry ~/.mso-registry/workflows/workflow_registry.json --fallback-registry {workspace}/.mso-context/workflow_registry.json` |
| **[Mode B]** Graph Search 상세 | [modules/module.graph-search-loader.md](modules/module.graph-search-loader.md) |

---

## Quick Example

### Mode A (신규 설계)

**Input**: "MSO v0.0.1 품질 개선 작업 워크플로우 설계"

**Phase 1** → DQ 7개 (CC 정합, schema 중복, SKILL format, runbook, 가시화, SoT, 통합테스트), RSV_total = 11.0
**Phase 2** → Signal 1: 순차 정비 → `linear`. Signal 3: RSV 중간 → linear 충분 → **linear** (Chain motif)
**Phase 3** → T1(CC)→T2(schema)→T3(runbook)→T4(format)→T5(viz)→T6(dedup)→T7(cleanup)→T8(test), vertex_type 지정
**Phase 4** → T5에 RSV Inflation 위험 → scope cap "최소 1개 경로 동작"
**Phase 5** → `workflow_topology_spec.json` 생성

### Mode B (Graph Search Loader)

**Input**: "시장 조사 보고서 작성"

**Phase G1** → 레지스트리 검색 → Chain motif (similarity: 0.87, success_rate: 0.95), score: 0.902 → 선택
**Phase G2** → `PlannerAgent → ResearchAgent → Summarizer → Writer` 바인딩 완료
**Phase G3** → `workflow_topology_spec.json` 반환 (source: graph_search_loader)
