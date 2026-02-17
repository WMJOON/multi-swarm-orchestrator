# module.ticket-lifecycle

## Purpose
티켓 frontmatter 상태 전이를 제어한다.

## Invariants
- `todo -> in_progress -> done|blocked` 기본 경로
- `blocked -> in_progress`
- `done`/`cancelled`는 터미널 상태

## Idempotency
- 동일 전이는 오류가 아닌 no-op.
