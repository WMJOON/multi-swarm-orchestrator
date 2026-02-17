---
name: mso-agent-collaboration
---

# mso-agent-collaboration — Core Rules

## Purpose
티켓을 `ai-collaborator` 입력 형식(`task-handoff.schema.json`)으로 변환하고,
실행 결과를 ticket frontmatter와 감사 로그 입력 규격에 통합한다.

## Required output schema additions (required by plan)
- `dispatch_mode`: `run`/`batch`/`swarm`
- `handoff_payload`: 생성된 협업 요청 정보
- `requires_manual_confirmation`: 수동 승인 필요 여부
- `fallback_reason`: 미설치/헬스체크 실패 시 이유

## Invariants
- `ticket.status`는 `todo` 또는 `in_progress`만 dispatch 대상
- 실패 시 `requires_manual_confirmation=true` 반환
- ai-collaborator 미설치면 즉시 실패가 아닌 fallback 결과 반환

## when_unsure
- provider mapping이 모호하면 `codex` 기본, `requires_manual_confirmation=true` 표시.
