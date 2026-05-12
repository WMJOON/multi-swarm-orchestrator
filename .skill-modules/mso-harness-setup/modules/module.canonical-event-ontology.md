# Module: Canonical Event Ontology

## Goal

Provider-native event를 provider 독립적인 runtime semantic event로 정규화한다.

---

## Event Envelope

Canonical event는 다음 block을 분리해야 한다.

| Block | Responsibility |
|------|------|
| `event` | event id, timestamp, lifecycle phase, state transition |
| `provider` | provider name, runtime id, native event type, native payload reference |
| `capability` | capability category, operation, target, risk level |
| `execution` | tool/action name, duration, status, error |
| `semantic` | entropy, relevance, topology stability, ontology boundary |
| `governance` | review requirement, policy decision, escalation state |
| `audit` | correlation id, run id, trace id, checkpoint id |

---

## Lifecycle Phase Rules

| Native signal type | Canonical phase |
|------|------|
| session/runtime init | `session.start` |
| user message / task intake | `intent.received` |
| plan generation starts | `planning.start` |
| plan finalized | `planning.complete` |
| before tool/action invocation | `execution.pre` |
| after tool/action invocation | `execution.post` |
| result/environment observation | `observation.received` |
| evaluator begins | `evaluation.start` |
| evaluator finishes | `evaluation.complete` |
| durable state snapshot | `checkpoint.created` |
| model/provider/human route change | `escalation.triggered` |
| session/branch end | `termination` |

---

## Capability Normalization

Do not couple policy to provider tool names.

| Native examples | Capability |
|------|------|
| apply_patch, EditFile, write_file | `filesystem.write` |
| bash, terminal_exec, shell_run | `filesystem.execute` |
| browser_click, mouse_action, ui_click | `ui.interaction` |
| web_fetch, http_request, api_call | `network.fetch` |
| node_transition, workflow_activity | `workflow.transition` |
| vector_search, memory_lookup | `memory.read` |
| audit_insert, checkpoint_write | `memory.write` |

---

## Required Invariants

- `provider.native_event` must not be overwritten by canonical labels.
- `capability.category` must be available before policy evaluation.
- `governance.policy_decision` must be explicit: `allow`, `review`, `block`, or `escalate`.
- `semantic` fields may be null when evaluator is not enabled.
- `audit.correlation_id` should be stable across derived events from the same runtime action.
