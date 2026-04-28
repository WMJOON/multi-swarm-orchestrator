---
name: mso-agent-collaboration
---

# mso-agent-collaboration — Core Rules

## Purpose
티켓 frontmatter를 파싱하여 dispatch 모드(`run`/`batch`/`swarm`)를 결정하고,
handoff payload를 생성하여 실행 결과를 ticket 상태와 감사 로그에 통합한다.

## Required output schema additions (required by plan)
- `dispatch_mode`: `run`/`batch`/`swarm`
- `handoff_payload`: 생성된 협업 요청 정보
- `requires_manual_confirmation`: 수동 승인 필요 여부
- `fallback_reason`: 실행 실패 시 이유

## Harness Convention v0.1.2 (MUST)

### initial_context 포맷

에이전트 소환 시 반드시 이 포맷을 따른다. 전체 실행 히스토리는 포함하지 않는다(MUST NOT).

```yaml
initial_context:
  run_id: <run_id>
  phase: <phase_name>
  role: <role>           # execution | critic | sentinel 등

  objective: "<이 에이전트가 달성해야 할 목표 1줄>"

  policy:
    allowed_transitions: [...]
    forbidden: [...]
    completion_condition: "<완료 조건>"

  state_summary:
    reasoning_state: "<직전 에이전트의 마지막 상태 1~2줄>"
    completed_phases: [...]
    audit_ref: "<run_id>#<step>"

  handoff_from:
    agent_id: <이전 에이전트 ID>
    output_summary: "<이전 에이전트 결과 요약 1줄>"
```

### handoff_context 포맷

에이전트 완료 시 반드시 이 포맷으로 결과를 반환한다.

```yaml
handoff_context:
  agent_id: <agent_id>
  phase_completed: <phase_name>
  status: done                         # done | failed | hold

  output:
    summary: "<결과 요약 1줄>"
    artifacts: [...]

  state_updates:
    reasoning_state: "<갱신된 상태 1~2줄>"
    audit_ref: "<run_id>#<step>"

  next_phase_suggestion: <phase_name>  # 선택 (SHOULD)
```

### dispatch_mode 규약

- `dispatch_mode: swarm` = bus 패턴으로 처리 (MUST)
- 에이전트 완료 시 `execution_event`를 `audit_global.db`에 기록 (MUST)

### 소환 트리거

| 트리거 | 설명 |
|--------|------|
| `phase_enter` | topology의 다음 노드 진입 |
| `eval_point` | `eval_point: true` 노드 완료 후 |
| `drift_detected` | 현재 에이전트 output에서 drift 신호 감지 |
| `guard_escalate` | Guard가 ESCALATE 판정 |
| `fan_out` | bus 패턴의 worker 병렬 소환 |

## Invariants
- `ticket.status`는 `todo` 또는 `in_progress`만 dispatch 대상
- 실패 시 `requires_manual_confirmation=true` 반환
- `initial_context`에 전체 히스토리 포함 금지 (MUST NOT)

## when_unsure
- `dispatch_mode` 판별이 불명확하면 `run`(단일 실행)을 기본값으로 사용하고, 판단 근거를 audit payload에 기록한다.
- handoff_payload 필수 키(`run_id`, `task_id`, `owner_agent`, `role`, `objective`, `workflow_name`) 누락 시 `requires_manual_confirmation=true` 반환.
