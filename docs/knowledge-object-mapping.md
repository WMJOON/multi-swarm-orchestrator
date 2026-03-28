# Knowledge Object 매핑 — 기존 산출물의 명시지 분류

> v0.1.1에서 정의한 명시지 분류 체계(결정형/실행형/연결형)를 기존 MSO 산출물에 시범 적용한 매핑표.
> 각 산출물이 어떤 KO 유형에 해당하고, 어떤 필수 요소가 누락되어 있는지를 식별한다.

---

## 분류 기준 (knowledge_object.schema.json)

| 유형 | 핵심 질문 | 필수 요소 |
|------|-----------|-----------|
| **결정형(Decisional)** | "왜 이렇게 했는가?" | purpose, rationale, alternatives, constraints |
| **실행형(Operational)** | "어떻게 하는가?" | input_spec, output_spec, execution_steps |
| **연결형(Relational)** | "무엇과 관련되는가?" | upstream, downstream, contracts, dependencies |

---

## 매핑표

### 설계 파이프라인 산출물

| 산출물 | 경로 | KO 유형 | 충족 요소 | 누락 요소 | 명시지/암묵지 |
|--------|------|---------|-----------|-----------|--------------|
| `workflow_topology_spec.json` | `10_topology/` | **혼합** | 실행형: nodes, edges 구조 정의 | 결정형: decision_questions는 있으나 alternatives 부재 | **혼합** — decision_questions만 투영 |
| `chart.json` | `20_mental-model/` | 실행형 | 임베딩 좌표, 축 정의 | — | 암묵지 |
| `ontology.json` | `20_mental-model/` | 실행형 + 연결형 | morphisms(연결), composition_table | 결정형: 왜 이 사상 유형을 선택했는지 | 암묵지 |
| `directive_binding.json` | `20_mental-model/` | 연결형 | bindings(upstream→downstream) | 결정형: 바인딩 선택 근거 | 암묵지 |
| `execution_plan.json` | `30_execution/` | 실행형 | execution_graph, fallback_rules | 연결형: 어떤 topology에서 파생되었는지 | 암묵지 |

### 운영 파이프라인 산출물

| 산출물 | 경로 | KO 유형 | 충족 요소 | 누락 요소 | 명시지/암묵지 |
|--------|------|---------|-----------|-----------|--------------|
| `TKT-*.md` | `40_collaboration/` | 실행형 + 연결형 | frontmatter(status, owner, dependencies) | 결정형: 왜 이 티켓이 생성되었는지 | **명시지** |
| `goal.json` | `optimizer/` | 결정형 + 실행형 | next_automation_level, optimization_directives | 연결형: carry_over_issues의 출처 | **명시지** |
| `level{10,20,30}_report.md` | `optimizer/` | 결정형 | 분석 결과, 권고 사항 | 연결형: 어떤 audit 데이터에 기반했는지 | **명시지** |
| `deploy_spec.json` | `model-optimizer/` | **실행형 + 결정형** | reproducibility, evaluation, rollback | 결정형: **alternatives_considered 누락** — 왜 이 모델/전략을 선택했는지 기록 없음 | **명시지** |
| `*_eval_report.md` | `model-optimizer/` | 결정형 | F1, latency, LLM baseline 비교 | 연결형: 어떤 deploy_spec으로 이어지는지 | **명시지** |
| `handoff_payload.json` | `optimizer/` | **연결형** | trigger_type, target, escalation | **self_assessment 누락** (v0.1.1에서 추가됨) | 암묵지 |

### 인프라 파이프라인 산출물

| 산출물 | 경로 | KO 유형 | 충족 요소 | 누락 요소 | 명시지/암묵지 |
|--------|------|---------|-----------|-----------|--------------|
| `audit_global.db` | `.mso-context/` | 실행형 | 구조화된 실행 로그 | — | 암묵지 |
| `callback-*.json` | `60_observability/` | **혼합** | event_type, severity, message | 연결형: 이 이벤트가 유발하는 다음 행동 약함 | **혼합** — hitl_request만 투영 |
| `tool_registry.json` | `.mso-context/` | **3유형 모두** (v0.1.1) | knowledge 블록(decisional+operational+relational) | — | 암묵지 (knowledge 블록 투영 가능) |
| `manifest.json` | Smart Tool 내 | 실행형 | slots, version, lifecycle_state | **결정형 부재** — 왜 이 tool을 만들었는지 | 암묵지 |

### 거버넌스 산출물

| 산출물 | 경로 | KO 유형 | 충족 요소 | 누락 요소 | 명시지/암묵지 |
|--------|------|---------|-----------|-----------|--------------|
| `cc_contract_validation.json` | `70_governance/` | 실행형 | status, findings, schema_version | 결정형: 검증 기준의 근거 | 암묵지 |
| `HITL_ESCALATION_BRIEF.md` | 템플릿 | **결정형** | Trigger, Options, Deadline | **선택지의 expected_outcome/risk 구조화 부족** (v0.1.1 Gate Output Schema로 보완) | **명시지** |
| `gate_output_*.json` (v0.1.1) | `60_observability/` | 결정형 | situation, evidence, options, recommended | — | **명시지** |

---

## 개선 우선순위

### P0 — v0.1.1에서 해결됨

| 산출물 | 누락 | 해결 |
|--------|------|------|
| `tool_registry.json` | 결정형/실행형/연결형 전체 | `knowledge` 블록 추가 (tool_registry.schema.json) |
| `handoff_payload.json` | 행동 가능성 자기 진단 | `self_assessment` 블록 추가 |
| HITL Gate | 선택지 구조화 부족 | `gate_output.schema.json` 도입 |

### P1 — v0.2.0에서 해결 예정

| 산출물 | 누락 | 예정 |
|--------|------|------|
| `deploy_spec.json` | `alternatives_considered` | reproducibility 블록에 결정형 요소 추가 |
| `manifest.json` | 결정형 요소 전체 | Smart Tool manifest에 `purpose`, `creation_rationale` 필드 추가 |
| `callback-*.json` | 연결형(다음 행동 유발) | 이벤트에 `expected_consumer_action` 필드 추가 |

### P2 — v0.2.0 이후

| 산출물 | 누락 | 비고 |
|--------|------|------|
| `workflow_topology_spec.json` | 결정형의 alternatives | topology 설계 시 비교한 대안 motif 기록 |
| `directive_binding.json` | 결정형의 바인딩 근거 | 왜 이 directive를 이 노드에 바인딩했는지 |
| `execution_plan.json` | 연결형의 파생 관계 | 어떤 topology에서 생성되었는지 추적 |

---

## Convention에 따른 투영 분류 요약

```
mso-outputs/{run_id}/
├── decisions/           ← 결정형 KO
│   ├── decision_questions.md    (from 10_topology)
│   └── level20_report.md        (from optimizer)
├── reports/             ← 실행형 KO
│   ├── deploy_spec.json          (from model-optimizer)
│   └── tl20_eval_report.md       (from model-optimizer)
├── gates/               ← Gate Output
│   ├── gate_output_*.md          (from 60_observability, rendered)
│   └── hitl_request_*.md         (from 60_observability, rendered)
├── collaboration/       ← 연결형 KO
│   └── TKT-*.md                  (from 40_collaboration)
└── topology/            ← 구조 시각화
    └── *.mermaid                  (from 10_topology)
```
