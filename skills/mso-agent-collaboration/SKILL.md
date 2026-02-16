---
name: mso-agent-collaboration
description: >
  Adapt ticket inputs to ai-collaborator and integrate run output.
  Use when a ticket requires multi-agent execution.
disable-model-invocation: true
---

# mso-agent-collaboration

## 실행 프로세스

### Phase 1) Ticket ingestion
- ticket frontmatter를 파싱한다.
- 상태가 `todo`/`in_progress`가 아니면 skip.

### Phase 2) Handoff 생성
- `dispatch_mode` 결정(기본 `run`, 긴급/다중 태그일 때 `batch`/`swarm`).
- `handoff_payload`를 생성한다.

### Phase 3) 실행
- ai-collaborator 존재 시 호출 (`run`/`batch`)
- 미존재 시 `fallback` 결과를 생성하고 `requires_manual_confirmation=true` 반환

### Phase 4) 결과 반영
- `output-report`의 `status`를 ticket 상태로 반영
- `run-manifest`는 audit payload로 변환 저장

---

## Scripts

- `python3 scripts/dispatch.py --ticket task-context/tickets/TKT-0001-xxx.md`
