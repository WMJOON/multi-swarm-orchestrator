---
name: mso-harness-setup
description: |
  Runtime Harness Toolkit setup skill for MSO v0.2.2 planning.
  Use when designing a provider-free runtime harness layer, canonical runtime event ontology,
  provider adapters, YAML runtime configuration, policy injection, runtime evaluation,
  escalation routing, audit logging, or semantic stabilization for agent runtimes.
  Triggers: "harness-setup", "runtime harness", "canonical event", "provider adapter",
  "policy injection", "semantic runtime", "event ontology", "runtime governance".
---

# mso-harness-setup

> 이 스킬은 v0.2.2의 Runtime Harness Toolkit을 설계·초기화하기 위한 planning/spec 스킬이다.
> 목적은 새 agent framework를 만드는 것이 아니라, 서로 다른 provider runtime 위에서 동작하는 가벼운 runtime governance layer를 정의하는 것이다.

---

## 핵심 원칙

| 원칙 | 정의 |
|------|------|
| Provider-free | Claude Code, Codex, OpenClaw, Hermes, LangGraph, OpenAI Agents SDK 등 특정 provider에 종속되지 않는다 |
| Observable-only | chain-of-thought나 hidden latent state가 아니라 관측 가능한 action, invocation, observation, state transition만 다룬다 |
| Canonical semantics | provider-native event를 공통 lifecycle, capability, governance, evaluation 의미로 정규화한다 |
| YAML-first | provider adapter, policy, evaluation, routing, checkpoint, audit 설정은 YAML로 선언한다 |
| Lightweight harness | workflow logic을 소유하지 않고 runtime event normalize, guard, evaluate, route에 집중한다 |

---

## 책임 범위

### 이 스킬이 하는 일

- Canonical Event Schema 설계
- YAML Runtime Spec 설계
- Provider Adapter Interface 설계
- Capability taxonomy 설계
- Policy Engine 규칙 설계
- Runtime Evaluator 지표 설계
- Escalation Router 규칙 설계
- Audit Logger 이벤트 계약 설계
- Example adapter/config 산출
- MSO 기존 스킬(`mso-task-execution`, `mso-agent-audit-log`, `mso-observability`)과의 연결면 정의

### 이 스킬이 하지 않는 일

- 새로운 monolithic agent orchestration framework 구현
- provider별 workflow logic hardcoding
- model 내부 reasoning 추론
- UI 설계
- 특정 provider tool name에 직접 결합

---

## 입력

| 입력 | 필수 | 설명 |
|------|------|------|
| target_runtime | 선택 | `claude_code`, `codex`, `openclaw`, `hermes`, `langgraph`, `openai_agents_sdk`, `google_adk`, `mcp` 등 |
| native_event_samples | 권장 | provider별 hook/tool/action/node transition 이벤트 샘플 |
| governance_requirements | 권장 | review, policy injection, escalation, audit 요구사항 |
| stability_requirements | 선택 | entropy, topology stability, loop detection, bounded traversal 요구사항 |
| output_dir | 선택 | 기본값: `{workspace}/.mso-context/active/<run_id>/25_harness_setup/` |

**when_unsure**: provider event 샘플이 없으면 example adapter 수준으로 설계하고, native mapping은 `requires_sample: true`로 표시한다.

---

## 실행 프로세스

### Phase 1: Runtime Boundary 정의

1. harness가 관측할 event source를 식별한다.
2. provider-native semantics와 canonical semantics의 경계를 분리한다.
3. workflow orchestration 책임과 runtime governance 책임을 분리한다.
4. capability boundary를 tool name보다 우선하는 정규화 축으로 확정한다.

### Phase 2: Canonical Event Ontology 설계

1. lifecycle phase 목록을 확정한다.
2. event envelope 필드를 정의한다.
3. provider, capability, execution, semantic, governance, audit block을 분리한다.
4. schema required/optional 필드를 명확히 한다.

참조: [schemas/canonical_event.schema.json](schemas/canonical_event.schema.json), [modules/module.canonical-event-ontology.md](modules/module.canonical-event-ontology.md)

### Phase 3: Provider Adapter 설계

1. provider-native event type을 수집한다.
2. native event를 canonical lifecycle phase로 매핑한다.
3. tool/action name을 capability class로 정규화한다.
4. adapter output은 canonical event schema를 만족해야 한다.

참조: [modules/module.provider-adapter.md](modules/module.provider-adapter.md)

### Phase 4: YAML Runtime Spec 작성

1. provider adapter config를 선언한다.
2. policy injection 규칙을 capability/risk/lifecycle 기준으로 정의한다.
3. evaluator와 escalation trigger를 선언한다.
4. checkpoint, retry, audit logging 설정을 포함한다.

참조: [schemas/runtime_harness_config.schema.json](schemas/runtime_harness_config.schema.json), [configs/runtime-harness.example.yaml](configs/runtime-harness.example.yaml)

### Phase 5: Stabilization & Governance 설계

1. semantic entropy, relevance, topology stability 평가 기준을 정의한다.
2. loop detection, bounded traversal, ontology boundary enforcement 규칙을 정의한다.
3. escalation route는 model/provider name이 아니라 route capability와 policy class로 우선 표현한다.
4. 감사 로그는 canonical event를 보존하되 provider-native payload는 별도 block으로 격리한다.

참조: [modules/module.policy-engine.md](modules/module.policy-engine.md), [modules/module.runtime-evaluator.md](modules/module.runtime-evaluator.md)

---

## 산출물

| 산출물 | 경로 | 설명 |
|------|------|------|
| harness_plan.md | `{output_dir}/harness_plan.md` | provider-free runtime harness 설계 요약 |
| canonical_event.schema.json | `schemas/canonical_event.schema.json` | canonical event JSON Schema |
| runtime_harness_config.schema.json | `schemas/runtime_harness_config.schema.json` | YAML runtime config 검증 스키마 |
| runtime-harness.example.yaml | `configs/runtime-harness.example.yaml` | 예시 runtime config |
| adapter_mapping.md | `{output_dir}/adapter_mapping.md` | provider-native event → canonical event mapping |
| policy_matrix.md | `{output_dir}/policy_matrix.md` | capability/risk/lifecycle별 policy matrix |

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| → | `mso-task-execution` | 실행 전후 event emission/checkpoint hook 설계 입력 제공 |
| → | `mso-agent-audit-log` | canonical event와 provider-native payload를 audit DB에 적재하는 계약 제공 |
| → | `mso-observability` | semantic entropy, topology stability, loop signal을 관측 지표로 제공 |
| → | `mso-workflow-optimizer` | escalation/automation level 판단에 runtime stability signal 제공 |
| ← | `mso-skill-governance` | 스키마, 정책, adapter 계약 검증 대상 |

---

## 상세 파일 참조

| 상황 | 파일 |
|------|------|
| Canonical event ontology | [modules/module.canonical-event-ontology.md](modules/module.canonical-event-ontology.md) |
| Provider adapter 설계 | [modules/module.provider-adapter.md](modules/module.provider-adapter.md) |
| Policy engine 설계 | [modules/module.policy-engine.md](modules/module.policy-engine.md) |
| Runtime evaluator 설계 | [modules/module.runtime-evaluator.md](modules/module.runtime-evaluator.md) |
| 모듈 목록 | [modules/modules_index.md](modules/modules_index.md) |
| 출처/근거 맵 | [references/source_map.md](references/source_map.md) |
