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

## Invariants
- `ticket.status`는 `todo` 또는 `in_progress`만 dispatch 대상
- 실패 시 `requires_manual_confirmation=true` 반환

## when_unsure
- provider mapping이 모호하면 `requires_manual_confirmation=true` 표시.
