---
name: mso-agent-collaboration
description: |
  Manages ticket lifecycle and dispatches tickets for multi-agent execution.
  Use when tasks need to be created/tracked (TKT-xxxx), state transitions are required
  (todo → in_progress → done/blocked/cancelled), or multi-agent dispatch,
  branching/merge orchestration, or Jewels-pattern teammate coordination is needed.
---

# mso-agent-collaboration

## 에이전트 역할 참조

| Agent Role | Phase | 핵심 업무 |
|---|---|---|
| Provisioning | 1 | Worktree 초기화, Base Commit 생성 |
| Execution | 2 | 태스크 수행, 산출물 해싱(SHA-256) |
| Handoff | 2-3 | 노드 간 상태/해시 전달 |
| Branching | 3 | 분기 탐지/생성, 실험 경로 포크 |
| Critic/Judge | 3 | 머지 합의, 품질 평가 |
| Sentinel | 4 | 에러 식별, Checkout 복구, HITL 에스컬레이션 |

## 티켓 관리 (Ticket Lifecycle)

### Bootstrap
- `{workspace}/.mso-context/active/<run_id>/40_collaboration/task-context/`가 없으면 생성
- `tickets/` 폴더와 `rules.md` 생성
- `python3 {mso-agent-collaboration}/scripts/bootstrap_node.py --path {workspace}/.mso-context/active/<run_id>/40_collaboration/task-context`

### 티켓 작성 / 상태 전이
- ID 정규화: `TKT-xxxx`
- 상태 enum: `todo → in_progress → done | blocked → in_progress`; `done`/`cancelled`는 terminal
- `python3 {mso-agent-collaboration}/scripts/create_ticket.py "..." --path <task-context-root>`
- `python3 {mso-agent-collaboration}/scripts/update_status.py --ticket TKT-xxxx --status in_progress`
- `python3 {mso-agent-collaboration}/scripts/validate_task_node.py --path <task-context-root>`
- `python3 {mso-agent-collaboration}/scripts/archive_tasks.py --path <task-context-root>`

### 템플릿

| 템플릿 | 파일 | 용도 |
|--------|------|------|
| PRD | [templates/PRD.md](templates/PRD.md) | "왜 지금 이 방식인가" — Scenario 단위 요구사항 |
| SPEC | [templates/SPEC.md](templates/SPEC.md) | 실행 계획 + 정책 + 티켓 리스트 |
| ADR | [templates/ADR.md](templates/ADR.md) | 아키텍처 의사결정 기록 |
| HITL Escalation Brief | [templates/HITL_ESCALATION_BRIEF.md](templates/HITL_ESCALATION_BRIEF.md) | H1/H2 Gate 에스컬레이션 판단 요청서 |
| Run Retrospective | [templates/RUN_RETROSPECTIVE.md](templates/RUN_RETROSPECTIVE.md) | Run 완료 후 회고 문서 |
| Design Handoff Summary | [templates/DESIGN_HANDOFF_SUMMARY.md](templates/DESIGN_HANDOFF_SUMMARY.md) | Design → Ops Swarm 인수인계 요약 |

---

## 멀티에이전트 디스패치

### Phase 1) Ticket ingestion
- ticket frontmatter를 파싱한다.
- 상태가 `todo`/`in_progress`가 아니면 skip.

### Phase 2a) Handoff 생성
- `dispatch_mode` 결정(기본 `run`, 긴급/다중 태그일 때 `batch`/`swarm`).
- `handoff_payload`를 생성한다.

### Phase 2b) Branching & Merge Dispatch (v0.0.3)
- execution_graph에서 `type=branch` 노드 감지 시:
  - 부모 Commit의 `tree_hash_ref` 상태를 각 브랜치 워크스페이스로 복사
  - 브랜치별 독립적 dispatch 실행 (Branching Agent)
- execution_graph에서 `type=merge` 노드 감지 시:
  - 모든 parent 브랜치 결과 수집
  - `merge_policy`에 따라 Critic/Judge Agent가 합의 평가
  - quorum 충족 시 merge commit 생성, 미달 시 HITL 에스컬레이션

### Phase 3) 실행
- `dispatch_mode`에 따라 직접 실행한다 (`run`/`batch`/`swarm`).
- 실행 실패 시 `fallback` 결과를 생성하고 `requires_manual_confirmation=true` 반환

### Phase 4) 결과 반영
- `output-report`의 `status`를 ticket 상태로 반영
- `run-manifest`는 audit payload로 변환 저장
- node_snapshots에 실행 결과 기록 (node_type, tree_hash_ref 포함)

---

## Scripts

- `python3 {mso-agent-collaboration}/scripts/dispatch.py --ticket {workspace}/.mso-context/active/<run_id>/40_collaboration/task-context/tickets/TKT-0001-xxx.md`

### when_unsure
- dispatch_mode 판별이 불명확하면 `run`(단일 실행)을 기본값으로 사용하고, 판단 근거를 audit payload에 기록한다.

---

## 상세 파일 참조

| 상황 | 파일 |
|------|------|
| dispatch 실행 | `python3 {mso-agent-collaboration}/scripts/dispatch.py --ticket <ticket.md>` |
| 상세 규칙 | [core.md](core.md) |
| 모듈 목록 | [modules/modules_index.md](modules/modules_index.md) |
