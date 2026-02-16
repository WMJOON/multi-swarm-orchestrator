# mso-task-context-management — Core Rules

## Purpose
작업 트래킹을 위한 범용 티켓 레이어를 제공한다.

## Terminology
- `task_context_id`: 01에서 실행 단위를 구분하는 식별자
- `ticket`: 상태/우선순위/태그/의존성이 있는 작업 항목
- `frontmatter`: 티켓 메타데이터 영역

## Input Interface
- 티켓 제목, 우선순위, 상태, 태그, 의존성, 소유자, 마감일

## Output Interface
- `task-context/tickets/<id>.md`
- 아카이브: `task-context/archive/<year>/...`

## Invariants
- 상태 enum: `todo`, `in_progress`, `blocked`, `done`, `cancelled`
- 상태 전이는 idempotent(동일 전이는 no-op)
- `done`/`cancelled`에서 하향 전이는 허용하지 않음.
- 의존성은 존재하는 티켓 파일명 stem과 일치해야 함.

## when_unsure
- 경로를 못 찾으면 `task-context` 기준 경로로 새 노드를 부트스트랩한다.
- 의존성 missing은 warning으로 노출하고 강제 실패 대신 보류 상태를 반환한다.
