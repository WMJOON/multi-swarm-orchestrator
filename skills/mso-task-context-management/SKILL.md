---
name: mso-task-context-management
description: |
  Creates and manages task-context nodes and ticket lifecycle.
  Use when tasks need to be tracked, prioritized, and transitioned through states within a run context.
disable-model-invocation: true
---

# mso-task-context-management

## 실행 프로세스

### Phase 1) 노드 부트스트랩
- `workspace/.mso-context/active/<Run ID>/40_collaboration/task-context/`가 없으면 생성
- `tickets/` 폴더와 `rules.md` 생성

### Phase 2) 티켓 작성
- 제목에서 ID 정규화 (`TKT-xxxx`)
- frontmatter에 필수 키 채우기

### Phase 3) 상태 전이
- 허용 전이만 허용
- `done/cancelled`는 terminal

### Phase 4) 검증/아카이브
- 의존성 해상도 확인
- `done`/`cancelled` 티켓 종료: frontmatter 파싱 → `ticket_closure_log.md` append → 티켓+companion json 삭제
- `python3 scripts/archive_tasks.py --path <task-context-root>`

### when_unsure
- 의존성이 불명하면 사용자가 확인하도록 warning + `blocked`로 남긴다.

## Templates

템플릿 SoT: `mso-process-template/templates/`

| 템플릿 | 파일 | 용도 |
|--------|------|------|
| **PRD** | [../mso-process-template/templates/PRD.md](../mso-process-template/templates/PRD.md) | "왜 지금 이 방식이어야 하는가"를 설명하는 문서 |
| **SPEC** | [../mso-process-template/templates/SPEC.md](../mso-process-template/templates/SPEC.md) | 실행 계획 + 정책 + 티켓 리스트 + 체크리스트 |
| **ADR** | [../mso-process-template/templates/ADR.md](../mso-process-template/templates/ADR.md) | 아키텍처 의사결정 기록. 결정·대안·기각 사유·영향 추적 |

## Scripts

- `python3 scripts/bootstrap_node.py --path workspace/.mso-context/active/<Run ID>/40_collaboration/task-context`
- `python3 scripts/create_ticket.py "..." --path workspace/.mso-context/active/<Run ID>/40_collaboration/task-context`
- `python3 scripts/update_status.py --ticket ... --status in_progress`
- `python3 scripts/validate_task_node.py --path workspace/.mso-context/active/<Run ID>/40_collaboration/task-context`
- `python3 scripts/archive_tasks.py --path workspace/.mso-context/active/<Run ID>/40_collaboration/task-context`
