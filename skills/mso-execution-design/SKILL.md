---
name: mso-execution-design
description: |
  Transforms topology and mental model into a versioned execution graph (v0.0.3).
  Produces execution_graph with commit/branch/merge node types,
  handoff contracts, fallback rules (error taxonomy), and lifecycle policy.
  Use when an execution plan needs to be built from topology_spec and mental_model_bundle.
disable-model-invocation: true
---

# mso-execution-design

## 에이전트 역할 매핑

| Agent Role | Phase | 핵심 업무 |
|---|---|---|
| Provisioning | 1 | Worktree 초기화, Base Commit 생성 |
| Execution | 2 | 태스크 수행, 산출물 해싱(SHA-256) |
| Handoff | 2-3 | 노드 간 상태/해시 전달 |
| Branching | 3 | 분기 탐지/생성, 실험 경로 포크 |
| Critic/Judge | 3 | 머지 합의, 품질 평가 |
| Sentinel | 4 | 에러 식별, Checkout 복구, HITL 에스컬레이션 |

## 실행 프로세스

### Phase 1) 입력 정합성
- topology와 bundle을 읽어 기본 키 존재 확인
- CC-01/CC-02에 필요한 mapping 기본 구조 확인

### Phase 2) execution_graph DAG 구성
- topology nodes + edges 분석으로 노드 타입 분류 (commit/branch/merge)
- 각 노드에 parent_refs, tree_hash_type, tree_hash_ref(null), bundle_ref, model_selection, chart_ids, mode, handoff_contract 할당
- 엣지 수 기반 자동 분류: incoming ≥ 2 → merge, outgoing ≥ 2 → branch, 그 외 → commit

### Phase 3) 브랜칭/머지 정책
- type=merge 노드에 merge_policy 기본값 삽입 (strategy, scoring_weights, quorum, manual_review_required)
- scoring_weights 합계 = 1.0 검증

### Phase 4) 폴백 규칙 정의
- fallback_rules를 에러 분류 체계 배열로 구성
- 에러 유형: schema_validation_error, hallucination, timeout, hitl_block
- 각 항목에 severity, action(retry/checkout/escalate), target_commit(절대 SHA), max_retry, requires_human
- lifecycle_policy 블록 출력

### when_unsure
- 모델 선택이 불명하면 `default`로 기록하고 근거를 note에 남긴다.

**산출물**: `workspace/.mso-context/active/<Run ID>/30_execution/execution_plan.json`

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| ← | `mso-workflow-topology-design` | CC-01: topology_spec를 입력으로 소비 |
| ← | `mso-mental-model-design` | CC-02: mental_model_bundle를 입력으로 소비 |
| → | `mso-agent-audit-log` | CC-06: execution_graph 노드 → 스냅샷 기록 |

---

## Templates

| 템플릿 | 파일 | 용도 |
|--------|------|------|
| **Design Handoff Summary** | [templates/DESIGN_HANDOFF_SUMMARY.md](templates/DESIGN_HANDOFF_SUMMARY.md) | Design Swarm 산출물을 Ops Swarm에 전달하는 요약 문서 |

---

## 상세 파일 참조

| 상황 | 파일 |
|------|------|
| 실행계획 생성 | `python3 scripts/build_plan.py --topology <topology.json> --bundle <bundle.json>` |
| 출력 스키마 검증 | [schemas/execution_plan.schema.json](schemas/execution_plan.schema.json) |
| 상세 규칙 | [core.md](core.md) |
| 모듈 목록 | [modules/modules_index.md](modules/modules_index.md) |
| execution_graph DAG 구성 규칙 | [modules/module.execution-graph.md](modules/module.execution-graph.md) |
| merge 정책 규칙 | [modules/module.merge-policy.md](modules/module.merge-policy.md) |
