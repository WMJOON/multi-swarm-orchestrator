# Workflow Repository Setup Core

## 1. 목적

Workflow Repository Setup은 workflow-design을 단발성 설계 산출물이 아니라 재사용 가능한 repository contract로 승격한다.

기존 설계 흐름은 실행 그래프를 만드는 데 집중했다. v0.2.2 구조에서는 먼저 workflow repository를 만든 뒤, harness가 그 repository contract를 runtime governance contract로 변환한다.

---

## 2. Core Flow

```text
workflow-design
  + scaffolding-design
  + optional mental-model enrichment
  -> workflow_repository.yaml
  -> harness_setup_input.yaml
  -> runtime_harness_config.yaml
```

---

## 3. Repository Contract

`workflow_repository.yaml`은 다음 정보를 가져야 한다.

| Block | Role |
|------|------|
| `workflow` | id, objective, scope, lifecycle states |
| `scaffolding` | directories, artifact slots, templates |
| `memory` | memory classes, owners, read/write boundaries |
| `governance` | hooks, state triggers, audit boundaries |
| `optimizer` | trigger inputs, feedback outputs |
| `harness_input` | lifecycle/capability/policy seed |

---

## 4. Memory Layer

메모리 레이어는 필수다. 단, 하나의 memory store로 통합하지 않는다.

| Memory class | Owner | Write boundary | Read boundary |
|------|------|------|------|
| runtime_state | harness / task-execution | active run only | harness, observability |
| audit_memory | agent-audit-log | append-only | governance, observability, optimizer |
| retrieval_memory | workflow repository | curated update | workflow-design, mental-model |
| optimizer_memory | workflow-optimizer | proposal/decision only | workflow repository, governance |

---

## 5. Governance Hooks

| Hook | Meaning | Target |
|------|------|------|
| `PreCompact` | context가 압축되기 전 state snapshot 기록 | `mso-agent-audit-log` |
| `Stop` | 실행 종료 시 terminal summary 기록 | `mso-agent-audit-log` |
| `state-trigger` | audit-log.db 상태 변화가 optimizer를 깨우는 조건 | `mso-workflow-optimizer` |

---

## 6. Acceptance Criteria

| Criteria | Check |
|------|------|
| workflow-design/scaffolding-design 분리 | 각각 독립 block으로 존재 |
| mental-model optional | 없으면 pending enrichment로 표시 |
| memory layer explicit | memory class, owner, boundary 정의 |
| harness-ready | `harness_setup_input` block 존재 |
| governance-ready | PreCompact/Stop/state-trigger 정의 |
