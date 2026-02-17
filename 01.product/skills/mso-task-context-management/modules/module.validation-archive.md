# module.validation-archive

## Purpose
티켓 무결성 검증 + 완료 항목 아카이브 규칙.

## Validation
- `dependencies`가 없는 티켓 참조면 warning
- `done` 상태 티켓만 archive
