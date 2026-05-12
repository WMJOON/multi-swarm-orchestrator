# Runtime Harness Toolkit Core

## 1. 목적

Runtime Harness Toolkit은 provider runtime 위에 얇게 올라가는 semantic runtime governance layer다.

핵심 목적은 다음 네 가지다.

1. 서로 다른 provider-native event를 canonical event로 정규화한다.
2. tool name 대신 capability class를 기준으로 policy를 적용한다.
3. 실행 안정성 신호를 평가하여 escalation, retry, checkpoint를 제어한다.
4. provider 독립적인 auditability와 observability를 제공한다.

이 toolkit은 agent framework가 아니다. agent의 planning, reasoning, workflow logic을 대체하지 않는다. 대신 runtime에서 관측 가능한 행동과 상태 전이를 안정적으로 해석하고 통제한다.

---

## 2. Runtime Event Flow

```text
Provider Runtime
  -> Native Event
  -> Provider Adapter
  -> Canonical Event
  -> Policy Engine
  -> Event Bus
  -> Runtime Evaluator
  -> Escalation Router / Audit Logger / Checkpoint Store
```

---

## 3. Canonical Lifecycle

| Phase | 의미 |
|------|------|
| `session.start` | provider runtime 세션 시작 |
| `intent.received` | 사용자 또는 upstream system intent 수신 |
| `planning.start` | 계획 수립 시작 |
| `planning.complete` | 계획 수립 완료 |
| `execution.pre` | capability invocation 직전 |
| `execution.post` | capability invocation 직후 |
| `observation.received` | 실행 결과 또는 환경 관측 수신 |
| `evaluation.start` | runtime signal 평가 시작 |
| `evaluation.complete` | runtime signal 평가 완료 |
| `checkpoint.created` | 복구 가능한 상태 스냅샷 생성 |
| `escalation.triggered` | 정책 또는 평가 결과로 escalation 발생 |
| `termination` | 세션 또는 branch 종료 |

---

## 4. Capability Taxonomy

Capability는 provider tool name보다 안정적인 runtime abstraction이다.

| Capability | 포함 예시 |
|------|------|
| `filesystem.read` | read_file, cat, open resource |
| `filesystem.write` | apply_patch, write_file, edit_file |
| `filesystem.execute` | bash, terminal_exec, shell_run |
| `ui.interaction` | browser_click, mouse_action, ui_click |
| `network.fetch` | web fetch, HTTP request, API call |
| `memory.read` | vector search, memory lookup, context load |
| `memory.write` | memory append, audit insert, checkpoint write |
| `model.invoke` | LLM call, judge call, embedding call |
| `workflow.transition` | node transition, branch enter, branch merge |
| `governance.review` | HITL gate, approval request, policy review |

---

## 5. Evaluation Signals

| Signal | 정의 | 기본 처리 |
|------|------|------|
| `semantic_entropy` | event stream의 의미적 불안정성 또는 drift proxy | threshold 초과 시 evaluation warning |
| `relevance_score` | 현재 intent/objective와 event의 관련도 | 낮으면 branch termination 후보 |
| `topology_stability` | workflow graph/node transition 안정성 | unstable이면 checkpoint + review |
| `loop_risk` | 반복 invocation/state transition 위험 | threshold 초과 시 bounded traversal |
| `ontology_boundary` | 허용된 domain/capability boundary 준수 여부 | violation이면 policy block 또는 review |

---

## 6. Governance Boundary

Harness는 다음 판단을 할 수 있다.

- capability risk level 산정
- pre_action context injection
- post_action evaluation
- checkpoint 생성 요청
- escalation route 선택
- audit event 기록
- retry/termination 후보 제안

Harness는 다음 판단을 하지 않는다.

- model 내부 사고 과정 해석
- hidden state 추론
- provider-specific workflow 재작성
- 사용자 승인 없이 topology 자동 변경
- provider credential 또는 auth flow 직접 소유

---

## 7. v0.2.2 Planning Acceptance Criteria

v0.2.2 planning은 다음이 충족되면 완료로 본다.

| 항목 | 기준 |
|------|------|
| Canonical Event Schema | provider/native/canonical/governance/evaluation block 분리 |
| YAML Runtime Spec | adapter, policy, evaluator, escalation, audit 설정 포함 |
| Provider Adapter Interface | Claude Code, Codex, OpenClaw, Hermes example mapping 작성 |
| Capability Taxonomy | tool name이 아닌 capability class 중심 |
| Governance Flow | pre_action, post_action, review, escalation 경로 정의 |
| MSO Integration | audit-log, observability, task-execution 연결면 정의 |
