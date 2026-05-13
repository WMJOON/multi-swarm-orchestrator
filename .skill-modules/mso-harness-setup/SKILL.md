---
name: mso-harness-setup
description: |
  Runtime Harness Toolkit for MSO v0.2.2. 두 가지 역할을 담당한다.
  (1) Harness Design: provider-free runtime harness layer 설계 — canonical event ontology,
  provider adapter, YAML runtime spec, policy engine, runtime evaluator, escalation routing.
  (2) Execution Orchestration: execution_graph.json + directive_binding.json을 소비하여
  스킬 호출 순서를 결정하고, Fallback Policy를 적용하며, node snapshot을 audit log에 적재.
  Triggers: "harness-setup", "runtime harness", "canonical event", "provider adapter",
  "policy injection", "semantic runtime", "event ontology", "runtime governance",
  "execution graph 실행", "노드 실행", "fallback policy".
---

# mso-harness-setup

> v0.2.2 Runtime Harness Toolkit. Harness 설계(Phase 1–5)와 Execution Orchestration(Phase 6–7)을 통합한다.
> 설계 목표: 특정 provider에 종속되지 않는 가벼운 runtime governance layer + 실행 조율.

---

## 핵심 원칙

| 원칙 | 정의 |
|------|------|
| Provider-free | Claude Code, Codex, OpenClaw, LangGraph, OpenAI Agents SDK 등에 종속되지 않는다 |
| Observable-only | 관측 가능한 action, invocation, observation, state transition만 다룬다 |
| Canonical semantics | provider-native event를 공통 lifecycle/capability/governance/evaluation 의미로 정규화한다 |
| YAML-first | adapter, policy, evaluation, routing, checkpoint, audit 설정은 YAML로 선언한다 |
| Lightweight harness | workflow logic을 소유하지 않고 normalize, guard, evaluate, route에 집중한다 |

---

## 책임 범위

### Harness Design (Phase 1–5)
- Canonical Event Schema 설계
- YAML Runtime Spec 설계
- Provider Adapter Interface 설계
- Policy Engine 규칙 설계
- Runtime Evaluator 지표 설계
- Escalation Router 규칙 설계
- Audit Logger 이벤트 계약 설계

### Execution Orchestration (Phase 6–7)
- `execution_graph.json` + `directive_binding.json` 소비
- 위상 정렬(topological sort) 기반 노드 실행 순서 결정
- 각 노드 실행 + wrapper 호출 + node_snapshot 적재
- Fallback Policy Registry 기반 에러 처리

---

## 입력

| 입력 | 필수 | 설명 |
|------|------|------|
| target_runtime | 선택 | `claude_code`, `codex`, `openclaw`, `hermes`, `langgraph`, `openai_agents_sdk` 등 |
| native_event_samples | 권장 | provider별 hook/tool/action/node transition 이벤트 샘플 |
| governance_requirements | 권장 | review, policy injection, escalation, audit 요구사항 |
| execution_graph.json | Phase 6 필수 | `mso-workflow-topology-design` 산출물 (CC-01) |
| directive_binding.json | Phase 6 필수 | `mso-mental-model` 산출물 (CC-02) |

---

## 실행 프로세스

### Phase 1: Runtime Boundary 정의

1. harness가 관측할 event source를 식별한다.
2. provider-native semantics와 canonical semantics의 경계를 분리한다.
3. workflow orchestration 책임과 runtime governance 책임을 분리한다.

### Phase 2: Canonical Event Ontology 설계

1. lifecycle phase 목록을 확정한다.
2. event envelope 필드 및 provider/capability/governance/audit block을 정의한다.

참조: [schemas/canonical_event.schema.json](schemas/canonical_event.schema.json), [modules/module.canonical-event-ontology.md](modules/module.canonical-event-ontology.md)

### Phase 3: Provider Adapter 설계

1. provider-native event type을 수집하여 canonical lifecycle phase로 매핑한다.
2. tool/action name을 capability class로 정규화한다.

참조: [modules/module.provider-adapter.md](modules/module.provider-adapter.md)

### Phase 4: YAML Runtime Spec 작성

1. provider adapter config, policy injection 규칙, evaluator, escalation trigger를 선언한다.
2. checkpoint, retry, audit logging 설정을 포함한다.

참조: [schemas/runtime_harness_config.schema.json](schemas/runtime_harness_config.schema.json), [configs/runtime-harness.example.yaml](configs/runtime-harness.example.yaml)

### Phase 5: Stabilization & Governance 설계

1. semantic entropy, topology stability, loop detection 평가 기준을 정의한다.
2. escalation route는 capability와 policy class로 표현한다.

참조: [modules/module.policy-engine.md](modules/module.policy-engine.md), [modules/module.runtime-evaluator.md](modules/module.runtime-evaluator.md)

### Phase 6: 입력 검증 (Execution)

1. `execution_graph.json` 필수 필드 확인 (`graph_id`, `schema_version`, `nodes[]`)
2. `directive_binding.json` 바인딩 완료 여부 확인 (`unbound_nodes[]` 존재 시 경고 후 계속)
3. `schema_version` 불일치 시 즉시 중단

참조: [schemas/execution_plan.schema.json](schemas/execution_plan.schema.json)

### Phase 7: 노드 실행 & 에러 처리

각 노드에 대해 순서대로 실행:

```
1. wrapper.otel.before(node_id)          → span_context  [spec-only]
2. directive_binding에서 directive 로드
3. bundle_ref 스킬/에이전트 호출
4. wrapper.otel.after(span_context)                       [spec-only]
5. wrapper.guardrails.validate(output)  → pass/fail       [spec-only]
6. node_snapshot → mso-agent-audit-log 적재 (CC-06)
```

**Fallback Policy Registry**

| 에러 유형 | severity | action | max_retry | requires_human |
|-----------|----------|--------|-----------|----------------|
| `schema_validation_error` | high | checkout | 2 | false |
| `hallucination` | medium | retry | 1 | false |
| `timeout` | low | retry | 3 | false |
| `hitl_block` | critical | escalate | 0 | true |

- `retry`: 동일 프롬프트 + 에러 메시지 첨부 후 재요청
- `checkout`: 절대 SHA로 마지막 정상 커밋 복구
- `escalate`: Sentinel Agent에 `hitl_request` 이벤트 전달
- `max_retry` 소진 후 미해소 시 severity 한 단계 상향 → `escalate`

참조: [modules/module.fallback-handoff.md](modules/module.fallback-handoff.md), [modules/module.execution-graph.md](modules/module.execution-graph.md)

---

## 산출물

| 산출물 | 경로 | 설명 |
|--------|------|------|
| harness_plan.md | `{output_dir}/harness_plan.md` | runtime harness 설계 요약 |
| canonical_event.schema.json | `schemas/canonical_event.schema.json` | canonical event JSON Schema |
| runtime_harness_config.schema.json | `schemas/runtime_harness_config.schema.json` | YAML runtime config 검증 스키마 |
| adapter_mapping.md | `{output_dir}/adapter_mapping.md` | provider-native → canonical event 매핑 |
| policy_matrix.md | `{output_dir}/policy_matrix.md` | capability/risk/lifecycle별 policy matrix |
| execution_result.json | `{output_dir}/30_execution/execution_result.json` | 전체 실행 요약 |
| node_snapshots | `mso-agent-audit-log` DB | 각 노드 실행 결과 스냅샷 |

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| ← | `mso-workflow-topology-design` | CC-01: execution_graph.json 소비 |
| ← | `mso-mental-model` | CC-02: directive_binding.json 소비 |
| → | `mso-agent-audit-log` | CC-06: node_snapshot 적재 |
| → | `mso-observability` | semantic entropy, topology stability signal 제공 |
| → | `mso-workflow-optimizer` | escalation/automation level 판단에 runtime signal 제공 |
| ← | `mso-skill-governance` | 스키마, 정책, adapter 계약 검증 대상 |

---

## 상세 파일 참조

| 상황 | 파일 |
|------|------|
| Canonical event ontology | [modules/module.canonical-event-ontology.md](modules/module.canonical-event-ontology.md) |
| Provider adapter 설계 | [modules/module.provider-adapter.md](modules/module.provider-adapter.md) |
| Policy engine 설계 | [modules/module.policy-engine.md](modules/module.policy-engine.md) |
| Runtime evaluator 설계 | [modules/module.runtime-evaluator.md](modules/module.runtime-evaluator.md) |
| Execution graph 구조 | [modules/module.execution-graph.md](modules/module.execution-graph.md) |
| Fallback/Handoff 규칙 | [modules/module.fallback-handoff.md](modules/module.fallback-handoff.md) |
| 노드 매핑 | [modules/module.node-mapping.md](modules/module.node-mapping.md) |
| 실행 계획 빌드 | `python3 scripts/build_plan.py` |
| 모듈 목록 | [modules/modules_index.md](modules/modules_index.md) |
