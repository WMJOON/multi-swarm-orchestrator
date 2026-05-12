# Module: Memory Layer

## Goal

Memory layer는 workflow repository, runtime harness, audit log, optimizer가 같은 상태를 서로 다른 방식으로 덮어쓰지 않도록 write/read boundary를 나눈다.

---

## Memory Classes

| Class | Description | Owner |
|------|------|------|
| `runtime_state` | 현재 실행의 ephemeral state | `mso-harness-setup`, `mso-task-execution` |
| `audit_memory` | append-only event/state history | `mso-agent-audit-log` |
| `retrieval_memory` | workflow 재사용을 위한 curated knowledge | `mso-workflow-repository-setup`, optional `mso-mental-model` |
| `optimizer_memory` | optimization proposal, decision, feedback | `mso-workflow-optimizer` |

---

## Hook Mapping

```yaml
governance_hooks:
  PreCompact:
    target: mso-agent-audit-log
    action: append_context_snapshot
  Stop:
    target: mso-agent-audit-log
    action: append_terminal_summary
  state_trigger:
    source: audit-log.db
    target: mso-workflow-optimizer
    action: evaluate_optimization_signal
```

---

## Invariants

- audit memory is append-only.
- optimizer memory may propose repository changes but must not apply them automatically.
- retrieval memory is curated; raw runtime logs do not flow into it directly.
- runtime state can be compacted, but PreCompact must leave an audit snapshot.
