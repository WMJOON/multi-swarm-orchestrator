# mso-harness-setup Modules Index

| Module | Purpose | Status |
|------|------|------|
| [module.canonical-event-ontology.md](module.canonical-event-ontology.md) | Canonical lifecycle/event envelope/capability ontology 정의 | spec |
| [module.provider-adapter.md](module.provider-adapter.md) | Provider-native event를 canonical event로 변환하는 adapter contract | spec |
| [module.policy-engine.md](module.policy-engine.md) | YAML 기반 policy injection, guard, retry, escalation 규칙 | spec |
| [module.runtime-evaluator.md](module.runtime-evaluator.md) | entropy, relevance, topology stability, loop risk 평가 규칙 | spec |

---

## Loading Policy

1. Harness 전체 설계 요청이면 `SKILL.md`와 `core.md`를 먼저 읽는다.
2. Event schema 작업이면 `module.canonical-event-ontology.md`와 `schemas/canonical_event.schema.json`을 읽는다.
3. Provider mapping 작업이면 `module.provider-adapter.md`를 읽는다.
4. Governance/policy 작업이면 `module.policy-engine.md`와 `configs/runtime-harness.example.yaml`을 읽는다.
5. Stability/evaluation 작업이면 `module.runtime-evaluator.md`를 읽는다.
