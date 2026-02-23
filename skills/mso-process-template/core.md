# mso-process-template — 상세 프로세스 정의

---

## 1) 기본 실행 모델

- 기본 모드: 문서 가이드 기반 수동 오케스트레이션
- 스킬 간 데이터 전달: Runtime Workspace 파일 아티팩트
- 감사/추적: `workspace/.mso-context/active/<Run ID>/`의 `manifest.json` + phase 산출물

### Git-Metaphor 상태 모델 (v0.0.5)

v0.0.5는 실행 계획을 **버전화된 상태 전이 그래프(Versioned State Transition Graph)**로 취급한다.
실제 Git CLI에 의존하지 않으며, 파일시스템 분리 + SQLite DB 해싱 에뮬레이션 방식을 채택한다.

| Git 개념 | MSO v0.0.5 런타임 | 설명 |
|----------|-------------------|------|
| **Worktree** | **Run Workspace** | 매 실행(Run)마다 격리된 작업 디렉토리. `.mso-context/active/{Run ID}` |
| **Commit** | **Node Snapshot** | 노드 실행 완료 시점의 불변 기록. DB 내 `node_snapshots` 테이블 |
| **Tree** | **Handoff Contract Context** | 단일 노드의 디렉토리/토큰 상태. `tree_hash_ref`(SHA-256) 포인터 |
| **Branch** | **Dynamic Execution 분기** | 동일 부모에서 파생된 탐색 경로. 자율 Branch 생성 가능 |
| **Merge** | **Fan-in Consensus** | 브랜치 결과 취합. merge_policy 기반 Critic/Judge 노드 |
| **Checkout** | **Fallback / Rollback** | 절대 SHA 참조로 안정 상태 복원 후 대안 경로 재시작 |

---

## 2) Worktree Branch Process

worktree branch process는 "생각 → 미리보기 → 실행"의 단계를 분리하기 위한 절차다.

### Planning Process

planning 단계에서는 실제 실행 이전에 구조와 영향을 명확히 드러내야 한다.

**1. Preview 단계**
- workflow를 직접 수정하지 않고, dashboard 기반 topology preview를 먼저 생성한다.
- 이 preview는 Mermaid 다이어그램으로 표현되며, 다음 요소를 포함해야 한다:
  - 노드(Agent, Skill, Tool)
  - Edge(Trigger, Dependency, Fan-out/Fan-in)
  - 변경 전/후 비교 가능 여부

이 단계의 목적은 "이 변경이 전체 시스템에 어떤 파장을 일으키는가"를 실행 없이 검증하는 것이다.

---

## 3) Work Process 정의

work process는 `workflow의 프리셋(template)`에 가깝다. 반복적으로 등장하는 작업 패턴을 구조화하여, 에이전트와 사람이 동일한 기대치를 공유하도록 한다.

### Planning Process — Type 1: 2-depth Planning

1. **에이전트 초안 작성**
   - 에이전트는 {target}에 대해 1차 초안을 생성한다.
   - 이 초안은 완성도가 아닌, 구조와 범위 정의를 목적으로 한다.
   - 반드시 "불확실한 지점"과 "추정한 전제"를 명시해야 한다.
2. **Human-in-the-loop 검토**
   - 사람은 초안을 검토하며 다음 중 하나를 선택한다:
     - **승인**: 계획을 고정하고 다음 단계로 진행한다.
     - **반려**: 수정 요청과 함께 1번 단계로 되돌리거나, 작업을 종료한다.
   - 이 단계는 책임 소재를 명확히 하기 위한 필수 절차다.
3. **Plan MD 작성**
   - 승인된 내용을 기준으로 plan md를 작성한다.
   - 이후 모든 실행·토론·SPEC은 이 plan md를 기준점(anchor)으로 삼는다.

### Discussion Process — Type 1: Critique Discussion

discussion process는 "결론 도출"이 아니라, 판단 품질을 높이기 위한 구조적 마찰을 의도한다.

**실행 조건**: PRD/SPEC의 `discussion-required: true`인 경우에만 멀티 모델 fan-out을 실행한다.
단순 케이스에서 무분별한 멀티 에이전트 호출을 방지하기 위한 정책이다.

#### discussion-required 판단 기준

`true`로 설정해야 하는 경우:

복합 추론:
- 복수의 설계 대안 중 우열이 불명확한 경우
- 단일 모델 추론의 편향 가능성이 높은 경우 (확증 편향 위험, 신규 도메인/미지 영역)

비가역성:
- 외부 서비스 호출·프로덕션 배포가 포함된 실행 (롤백 불가)
- 데이터 삭제 또는 스키마 파괴적 변경

영향 범위:
- 단일 결정이 복수 스킬/노드의 동작을 동시에 변경
- 공용 API·스키마·인터페이스 계약 변경 (downstream 전파)
- Merge policy 변경 (fan-in 합의 기준 자체가 달라지는 경우)
- topology 재설계, 공용 규칙 변경

불확실성:
- HITL escalation 이후 재시작 케이스 (이미 한 번 판단 실패) → 자동으로 `true`
- Fallback 경로가 설계되지 않은 상태에서 실행 진입

비용/성능:
- 토큰·API 비용이 예상 대비 현저히 초과될 가능성
- 고동시성·대규모 데이터 처리 경로 첫 설계

`false`로 유지해도 되는 경우 (기본값):
- 범위가 명확한 단순 리서치 또는 병렬 정보 수집
- 실행 절차가 확정된 routine 태스크
- 단일 SPEC 내 독립적인 구현 작업

#### 권고 트리거 케이스 (참고용)

| trigger | 설명 | 권고 여부 |
|---------|------|----------|
| `critique` | 설계안 전반의 구조적 결함 탐색 | 권고 |
| `risk-review` | 리스크·가정 검토, 고위험 결정 전 | 권고 |
| `design-compare` | 복수 설계 대안 비교 | 선택 |
| `custom` | 사용자 정의 | 선택 |

#### 실행 절차

1. Hand-off Template 결과를 입력으로 critique process를 실행한다.
2. critique는 다음 관점을 최소한으로 포함해야 한다:
   - 누락된 가정
   - 과도하게 낙관적인 부분
   - 시스템적 리스크 (확장성, 비용, 통제성)
3. critique 결과는 수정 의무를 강제하지 않지만, 기록으로 남겨야 한다.

---

## 4) Hand-off Templates 사용 규칙

템플릿 파일은 [templates/](templates/) 디렉토리에 위치한다.

- PRD의 각 Scenario에는 worktree branch 필수 여부(`True|False`), worktree id, worktree name 메타데이터를 명시해야 한다.
- SPEC의 Execution Policy에는 Retry Policy, Timeout/Fallback, Human Override Point를 정의한다.
- ADR의 status는 `proposed → accepted → deprecated|superseded`로 전이하며, superseded 시 후속 ADR의 decision-id를 참조한다.
- HITL Escalation Brief는 `mso-observability`의 `module.hitl-interaction`이 `hitl_request` 이벤트 생성 시 함께 작성한다.
- Run Retrospective는 Run 종료 후 `mso-observability`의 `improvement_proposal`, `anomaly_detected` 이벤트를 기반으로 작성한다.
- Design Handoff Summary는 `mso-execution-design`이 CC-01, CC-02, CC-06 산출물을 모두 생성한 후 작성한다.

---

## 5) 단계 라우팅

자세한 파이프라인 정의는 [pipelines.md](pipelines.md) 참조.

### 5.1 Design pipeline
- `mso-workflow-topology-design` → `mso-mental-model-design` → `mso-execution-design`

경로:
`workspace/.mso-context/active/<Run ID>/10_topology/workflow_topology_spec.json`
`→ 20_mental-model/mental_model_bundle.json`
`→ 30_execution/execution_plan.json`

### 5.2 Ops pipeline
- `mso-task-context-management` → `mso-agent-collaboration`

경로:
`workspace/.mso-context/active/<Run ID>/40_collaboration/task-context/tickets/TKT-0001.md`
`→ *.agent-collaboration.json`

### 5.3 Infra pipeline
- `mso-agent-audit-log` → `mso-observability`

경로:
`workspace/.mso-context/audit_global.db` (v0.0.5 global DB)
`→ active/<Run ID>/60_observability/callback-*.json`

### 5.4 Governance pipeline
- `mso-skill-governance` → `workspace/.mso-context/active/<Run ID>/70_governance/`

### 5.5 런타임 Phase (v0.0.5)

| Phase | 단계 | 에이전트 역할 | 핵심 업무 |
|-------|------|-------------|----------|
| 1 | Worktree Initialization | Provisioning Agent | 폴더 격리, Base Commit 생성 |
| 2 | Node Execution & Commit | Execution Agent, Handoff Agent | 태스크 수행, SHA-256 해싱, Handoff |
| 3 | Dynamic Branching & Merge | Branching Agent, Handoff Agent, Critic/Judge Agent | 분기/합류, 합의 평가 |
| 4 | Fallback Checkout | Sentinel Agent | 에러 식별, 절대 SHA 기반 복구 |

---

## 6) 콜백/이벤트 계약

오케스트레이션 이벤트는 파일 기반 이벤트로 처리하고, 필수 필드가 모두 존재해야 한다.

- 필드: `event_type`, `checkpoint_id`, `payload`, `retry_policy`, `correlation`, `timestamp`
- 필수 이벤트 유형: `improvement_proposal`, `anomaly_detected`, `periodic_report`, `hitl_request`
- v0.0.5 추가 이벤트: `branch_created`, `merge_completed`, `checkout_executed`, `snapshot_committed`
- 출력 위치: `workspace/.mso-context/active/<Run ID>/60_observability/*.json`
- 수신자: `mso-observability`

---

## 7) 에러/폴백 규칙

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

---

## 8) 실행/검증 권장 절차

1. `python3 skills/mso-skill-governance/scripts/run_sample_pipeline.py --goal "..." --task-title "..." --skill-key msowd --case-slug "..."`
2. `python3 skills/mso-skill-governance/scripts/validate_schemas.py --skill-key msogov --case-slug "..." --json`
3. `python3 skills/mso-skill-governance/scripts/validate_cc_contracts.py --skill-key msogov --case-slug "..." --json`
4. `python3 skills/mso-skill-governance/scripts/validate_gov.py --skill-key msogov --case-slug "..." --json`
5. `python3 skills/mso-skill-governance/scripts/validate_all.py --case-slug "..."`

---

## 9) Storage & Cleanup Lifecycle Policy

| 정책 | 기본값 | 설명 |
|------|--------|------|
| `branch_ttl_days` | 7 | 실험성 Branch 워크스페이스는 Merge 후 7일 내 삭제 |
| `artifact_retention_days` | 30 | Audit 로그와 병합 통과 원본 최소 30일 보존 |
| `archive_on_merge` | true | 보존 기간 만료 후 압축 보존(Archive) 전환 |
| `cleanup_job_interval_days` | 1 | 주기적(1일) 잔류 워크트리 캐시 정리 |

정책은 `workspace/.mso-context/config/policy.yaml`의 `lifecycle_policy` 블록에서 오버라이드 가능.

---

## 10) 인프라 노트

- **Git CLI 미사용**: 실제 `git` 명령어에 의존하지 않음. 파일시스템 에뮬레이션 + SQLite DB 방식
- **SQLite SoT**: `audit_global.db`가 전체 감사 데이터의 단일 진실 원천. 스키마 v1.5.0
- **WAL 모드**: `PRAGMA journal_mode=WAL` 적용으로 동시 읽기 성능 향상
- **Global DB**: v0.0.5부터 `workspace/.mso-context/audit_global.db`를 기본 경로로 사용. Run-local DB(`50_audit/agent_log.db`)는 레거시 호환
- **SHA-256 해싱**: `tree_hash_ref`는 산출물의 SHA-256 해시로, 실행 시점에 Execution Agent가 생성
- **Worktree 격리**: 각 Run은 `run_root/worktree/` 디렉토리에서 독립적 실행 컨텍스트 유지
- **스냅샷 저장**: `run_root/50_audit/snapshots/`에 스냅샷 관련 아티팩트 보관
- **스크립트 독립성**: `init_db.py`, `append_from_payload.py`는 `_shared` 의존 없이 독립 실행 가능
