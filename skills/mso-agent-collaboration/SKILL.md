---
name: mso-agent-collaboration
description: >
  Adapts ticket inputs to ai-collaborator and integrates run output.
  Use when a ticket requires multi-agent execution.
  v0.0.3: Supports 6-agent role model with branching and merge dispatch.
disable-model-invocation: true
---

# mso-agent-collaboration

## 에이전트 역할 참조 (v0.0.3)

| Agent Role | Phase | 핵심 업무 |
|---|---|---|
| Provisioning | 1 | Worktree 초기화, Base Commit 생성 |
| Execution | 2 | 태스크 수행, 산출물 해싱(SHA-256) |
| Handoff | 2-3 | 노드 간 상태/해시 전달 |
| Branching | 3 | 분기 탐지/생성, 실험 경로 포크 |
| Critic/Judge | 3 | 머지 합의, 품질 평가 |
| Sentinel | 4 | 에러 식별, Checkout 복구, HITL 에스컬레이션 |

## 실행 프로세스

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
- 외부 `ai-collaborator`를 호출하여 실행한다 (`run`/`batch`/`swarm`).
- `ai-collaborator` 미설치 또는 실행 실패 시 `fallback` 결과를 생성하고 `requires_manual_confirmation=true` 반환

### Phase 4) 결과 반영
- `output-report`의 `status`를 ticket 상태로 반영
- `run-manifest`는 audit payload로 변환 저장
- node_snapshots에 실행 결과 기록 (node_type, tree_hash_ref 포함)

---

## Scripts

- `python3 scripts/dispatch.py --ticket workspace/.mso-context/active/<Run ID>/40_collaboration/task-context/tickets/TKT-0001-xxx.md`

### when_unsure
- dispatch_mode 판별이 불명확하면 `run`(단일 실행)을 기본값으로 사용하고, 판단 근거를 audit payload에 기록한다.
- 외부 런타임 탐색 실패 시 내장 번들로 fallback하고 `requires_manual_confirmation=true`를 반환한다.

---

## 상세 파일 참조

| 상황 | 파일 |
|------|------|
| dispatch 실행 | `python3 scripts/dispatch.py --ticket <ticket.md>` |
| 상세 규칙 | [core.md](core.md) |
| 모듈 목록 | [modules/modules_index.md](modules/modules_index.md) |
