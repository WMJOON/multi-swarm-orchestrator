---
name: mso-orchestrator-rule
description: Multi-swarm orchestrator policy and execution contract for v0.0.3 runtime workspace.
type: cursor-rule
version: 0.0.3
always_apply: false
---

# Multi-Swarm Orchestrator Rule (v0.0.3)

> 이 문서는 실행 가능한 스킬이 아니라 `multi-swarm-orchestrator`의 오케스트레이션 룰 문서다.
> Runtime Workspace(`workspace/.mso-context`)를 기준으로 단계·경로·체크포인트를 규정한다.

## 1) 기본 실행 모델
- 기본 모드: 문서 가이드 기반 수동 오케스트레이션
- 스킬 간 데이터 전달: Runtime Workspace 파일 아티팩트
- 감사/추적: `workspace/.mso-context/active/<Run ID>/`의 `manifest.json` + phase 산출물

### 1b) Git-Metaphor 상태 모델 (v0.0.3)

v0.0.3은 실행 계획을 **버전화된 상태 전이 그래프(Versioned State Transition Graph)**로 취급한다.
실제 Git CLI에 의존하지 않으며, 파일시스템 분리 + SQLite DB 해싱 에뮬레이션 방식을 채택한다.

| Git 개념 | MSO v0.0.3 런타임 | 설명 |
|----------|-------------------|------|
| **Worktree** | **Run Workspace** | 매 실행(Run)마다 격리된 작업 디렉토리. `.mso-context/active/{Run ID}` |
| **Commit** | **Node Snapshot** | 노드 실행 완료 시점의 불변 기록. DB 내 `node_snapshots` 테이블 |
| **Tree** | **Handoff Contract Context** | 단일 노드의 디렉토리/토큰 상태. `tree_hash_ref`(SHA-256) 포인터 |
| **Branch** | **Dynamic Execution 분기** | 동일 부모에서 파생된 탐색 경로. 자율 Branch 생성 가능 |
| **Merge** | **Fan-in Consensus** | 브랜치 결과 취합. merge_policy 기반 Critic/Judge 노드 |
| **Checkout** | **Fallback / Rollback** | 절대 SHA 참조로 안정 상태 복원 후 대안 경로 재시작 |

## 2) 단계 라우팅
### 2.1 Design pipeline
- `mso-workflow-topology-design`
- `mso-mental-model-design`
- `mso-execution-design`

경로:
`workspace/.mso-context/active/<Run ID>/10_topology/workflow_topology_spec.json`
`→ workspace/.mso-context/active/<Run ID>/20_mental-model/mental_model_bundle.json`
`→ workspace/.mso-context/active/<Run ID>/30_execution/execution_plan.json`

### 2.2 Ops pipeline
- `mso-task-context-management` → 티켓 생성/상태 관리
- `mso-agent-collaboration` → 선택적 실행 레이어 (`run`/`batch`/`swarm`)

경로:
`workspace/.mso-context/active/<Run ID>/40_collaboration/task-context/tickets/TKT-0001.md`
`→ mso-agent-collaboration`
`→ *.agent-collaboration.json`

### 2.3 Infra pipeline
- `mso-agent-audit-log`(로그 소스)
- `mso-observability`(관측/feedback)

경로:
`workspace/.mso-context/active/<Run ID>/50_audit/agent_log.db`
`→ workspace/.mso-context/active/<Run ID>/60_observability/callback-*.json`
`→ mso-observability`

### 2.4 Governance pipeline
- `mso-skill-governance`

경로:
`workspace/.mso-context/active/<Run ID>/70_governance/`

### 2.5 런타임 Phase (v0.0.3)

4단계 × 6 에이전트 역할 매핑:

| Phase | 단계 | 에이전트 역할 | 핵심 업무 |
|-------|------|-------------|----------|
| 1 | Worktree Initialization | Provisioning Agent | 폴더 격리, Base Commit 생성 |
| 2 | Node Execution & Commit | Execution Agent, Handoff Agent | 태스크 수행, SHA-256 해싱, Handoff |
| 3 | Dynamic Branching & Merge | Branching Agent, Handoff Agent, Critic/Judge Agent | 분기/합류, 합의 평가 |
| 4 | Fallback Checkout | Sentinel Agent | 에러 식별, 절대 SHA 기반 복구 |

## 3) 콜백/이벤트 계약
오케스트레이션 이벤트는 파일 기반 이벤트로 처리하고, 필수 필드가 모두 존재해야 한다.

- 필드: `event_type`, `checkpoint_id`, `payload`, `retry_policy`, `correlation`, `timestamp`
- 필수 이벤트 유형: `improvement_proposal`, `anomaly_detected`, `periodic_report`, `hitl_request`
- v0.0.3 추가 이벤트: `branch_created`, `merge_completed`, `checkout_executed`, `snapshot_committed`
- 출력 위치: `workspace/.mso-context/active/<Run ID>/60_observability/*.json`
- 수신자: `mso-observability`

## 4) Gate / HITL 규칙
- H1 Gate: 복잡도/리스크/비용 임계치 초과 시 `event_type=hitl_request`
- H2 Gate: 전략 변경 또는 topology 재작성 필요 시 `event_type=hitl_request`
- Gate 진입 시 `requires_manual_confirmation=true`
- 수동 승인은 Run 단위 산출물(`40_collaboration`, `70_governance`)에 기록

## 5) 에러/폴백 규칙

에러 분류 체계(Error Taxonomy)에 따라 행동한다:

| error_type | severity | action | target_commit | max_retry | requires_human |
|-----------|----------|--------|---------------|-----------|----------------|
| `schema_validation_error` | high | checkout | 절대 SHA | 2 | false |
| `hallucination` | medium | retry | - | 1 | false |
| `timeout` | low | retry | - | 3 | false |
| `hitl_block` | critical | escalate | - | 0 | true |

추가 규칙:
- `10/20/30` 또는 `50/60` 실행 실패 시 실패 채널에 에러 로그와 재시도 힌트 저장
- `mso-agent-collaboration` 외부 의존 미해결 시 fallback 출력 생성 후 파이프라인 계속
- CC 검증/정합 실패 시 `70_governance` 결과 기록 후 `manifest.status=failed`
- 복구 시 모호한 상대 참조(`HEAD~1`) 금지 — 오직 절대 불변 커밋 참조(Absolute SHA)만 사용

## 6) 실행/검증 권장 절차
1. `python3 skills/mso-skill-governance/scripts/run_sample_pipeline.py --goal "..." --task-title "..." --skill-key msowd --case-slug "..."`
2. `python3 skills/mso-skill-governance/scripts/validate_schemas.py --skill-key msogov --case-slug "..." --json`
3. `python3 skills/mso-skill-governance/scripts/validate_cc_contracts.py --skill-key msogov --case-slug "..." --json`
4. `python3 skills/mso-skill-governance/scripts/validate_gov.py --skill-key msogov --case-slug "..." --json`
5. `python3 skills/mso-skill-governance/scripts/validate_all.py --case-slug "..."`

`validate_all`/`run_sample_pipeline` 등 스크립트는 Runtime Workspace 정책을 준수해 산출물을 생성/검증한다.

## 7) Storage & Cleanup Lifecycle Policy (v0.0.3)

Worktree 기반 실행 시 파일 용량과 잔존물 관리 규칙:

| 정책 | 기본값 | 설명 |
|------|--------|------|
| `branch_ttl_days` | 7 | 실험성 Branch 워크스페이스는 Merge 후 7일 내 삭제 |
| `artifact_retention_days` | 30 | Audit 로그와 병합 통과 원본 최소 30일 보존 |
| `archive_on_merge` | true | 보존 기간 만료 후 압축 보존(Archive) 전환 |
| `cleanup_job_interval_days` | 1 | 주기적(1일) 잔류 워크트리 캐시 정리 |

정책은 `workspace/.mso-context/config/policy.yaml`의 `lifecycle_policy` 블록에서 오버라이드 가능.

## 8) 인프라 노트 (v0.0.3)

- **Git CLI 미사용**: 실제 `git` 명령어에 의존하지 않음. 파일시스템 에뮬레이션 + SQLite DB 방식
- **SQLite SoT**: `agent_log.db`의 `node_snapshots` 테이블이 불변 감사 기록 담당
- **SHA-256 해싱**: `tree_hash_ref`는 산출물의 SHA-256 해시로, 실행 시점에 Execution Agent가 생성
- **Worktree 격리**: 각 Run은 `run_root/worktree/` 디렉토리에서 독립적 실행 컨텍스트 유지
- **스냅샷 저장**: `run_root/50_audit/snapshots/`에 스냅샷 관련 아티팩트 보관
