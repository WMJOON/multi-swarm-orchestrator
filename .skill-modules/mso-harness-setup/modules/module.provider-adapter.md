# Module: Provider Adapter

## Goal

Provider adapter는 native event를 canonical event로 변환하는 얇은 translation layer다.

```text
Provider Runtime -> Native Event -> Adapter -> Canonical Event -> Harness Runtime
```

---

## Adapter Contract

Adapter는 다음 책임만 가진다.

1. native event type을 보존한다.
2. canonical lifecycle phase를 부여한다.
3. native tool/action을 capability category로 정규화한다.
4. provider-specific metadata를 `provider.native_payload_ref` 또는 `provider.native_payload`에 격리한다.
5. canonical event schema를 만족하는 event를 반환한다.

Adapter는 다음 책임을 갖지 않는다.

- policy decision
- model escalation
- workflow graph mutation
- hidden reasoning reconstruction

---

## Initial Provider Mapping

| Provider | Native signal examples | Canonical mapping focus |
|------|------|------|
| Claude Code | Hook events, tool use lifecycle | `execution.pre`, `execution.post`, `checkpoint.created` |
| Codex | tool events, shell/apply_patch/browser events | capability normalization, audit correlation |
| OpenClaw | computer-use actions, channel events | `ui.interaction`, observation feedback |
| Hermes | agent runtime messages, task execution events | lifecycle + handoff mapping |
| LangGraph | node transitions, graph state updates | `workflow.transition`, topology stability |
| OpenAI Agents SDK | tool calls, handoffs, tracing events | model/tool invocation mapping |
| Google ADK | agent/tool/session events | adapter and policy boundary mapping |
| MCP-based systems | tool request/response envelopes | capability boundary and resource risk mapping |

---

## Adapter Output Pattern

```yaml
event:
  lifecycle:
    phase: execution.post
    state_transition: tool_completed
provider:
  name: codex
  native_event: tool_result
capability:
  category: filesystem.write
  risk_level: medium
execution:
  tool_name: apply_patch
  status: success
governance:
  policy_decision: allow
```

---

## when_unsure

If native event semantics are incomplete:

1. Preserve raw provider fields.
2. Set `lifecycle.phase: observation.received`.
3. Set `capability.category: unknown`.
4. Set `governance.policy_decision: review`.
5. Add `adapter.requires_sample: true` in planning output.
