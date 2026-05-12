# Module: Workflow Design

## Goal

Workflow design은 실행 계획이 아니라 repository가 보존해야 할 workflow boundary를 정의한다.

---

## Required Fields

| Field | Meaning |
|------|------|
| `workflow.id` | stable workflow id |
| `workflow.objective` | workflow가 해결하는 목적 |
| `workflow.scope` | project-local / reusable / global candidate |
| `workflow.lifecycle_states` | draft, active, paused, archived 등 |
| `workflow.entrypoints` | 사람이 호출하는 시작점 |
| `workflow.outputs` | workflow가 남기는 명시 산출물 |

---

## Boundary Rules

- workflow는 provider runtime을 소유하지 않는다.
- workflow는 tool name보다 capability boundary를 우선 기록한다.
- workflow repository는 실행 로그를 직접 쓰지 않는다.
- execution DAG가 필요하면 harness/task-execution 쪽에서 runtime state로 해석한다.
