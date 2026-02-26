# 변경 이력

## v0.0.6

### 핵심 변경

| 변경 | 내용 |
|------|------|
| **mso-workflow-optimizer 스킬 추가** | 워크플로우 성과 평가 → 3-Signal 기반 Automation Level(10/20/30) 판단 → 최적화 리포트 + goal 생성 |
| **CC-07/08/09 계약 추가** | observability → optimizer(CC-07), optimizer → audit-log(CC-08), optimizer → task-context(CC-09) |
| **work_type 확장** | `audit_logs.work_type`에 `workflow_optimization` 값 추가 |
| **user_feedback 매핑 규칙** | optimizer HITL 피드백을 기존 user_feedback 스키마에 매핑하는 규칙 정의 (feedback_text JSON 직렬화) |

### 수정 파일

**스킬 (신규)**
- `{mso-workflow-optimizer}/SKILL.md` — 5-Phase 실행 프로세스, Pack 내 관계
- `{mso-workflow-optimizer}/DIRECTORY.md` — 디렉토리 구성 명세, 모듈 추가 규약
- `{mso-workflow-optimizer}/core.md` — Input/Output 인터페이스, 처리 규칙, 에러 핸들링
- `{mso-workflow-optimizer}/.env.example` — llm-as-a-judge API 키 템플릿
- `{mso-workflow-optimizer}/configs/llm-model-catalog.yaml` — Provider별 분석 중심 모델 카탈로그
- `{mso-workflow-optimizer}/modules/modules_index.md` — Core/Operational 모듈 인덱스
- `{mso-workflow-optimizer}/modules/module.analysis-optimizing.md` — Phase 1–5 전체 오케스트레이션
- `{mso-workflow-optimizer}/modules/module.agent-decision.md` — 3-Signal(A/B/C) 판단 상세
- `{mso-workflow-optimizer}/modules/module.automation-level.md` — Level 10/20/30 실행 흐름 + 강등 정책
- `{mso-workflow-optimizer}/modules/module.hitl-feedback.md` — HITL 수렴 + goal 산출 + 타임아웃 처리
- `{mso-workflow-optimizer}/modules/module.process-optimizing.md` — 프로세스 실행·분석·평가 반복 워크플로우
- `{mso-workflow-optimizer}/modules/module.llm-as-a-judge.md` — LLM 라벨링 + TF-PN 정량 검증 + HITL 루프
- `{mso-workflow-optimizer}/schemas/optimizer_result.schema.json` — decision_output + goal JSON 스키마
- `{mso-workflow-optimizer}/scripts/select_llm_model.py` — 카탈로그 조회/검증 + env export 헬퍼

**기존 파일 수정**
- `{mso-agent-audit-log}/core.md` — work_type enum에 `workflow_optimization` 추가
- `{mso-observability}/SKILL.md` — Pack 내 관계에 CC-07 (→ optimizer) 추가
- `docs/pipelines.md` — CC-07/08/09 계약 정의 + Mermaid 다이어그램 업데이트
- `docs/usage_matrix.md` — 실행 방식/Phase/Swarm/운영 순서 매트릭스 + Sequence Diagram에 optimizer 반영
- `README.md` — Mermaid 아키텍처 다이어그램에 S10[Workflow Optimizer] 노드 추가

### 하위 호환 (v0.0.5 → v0.0.6)

- **스키마**: 변경 없음. DB 스키마 v1.5.0 유지. `work_type`은 nullable TEXT 컬럼이므로 신규 값 추가는 하위 호환
- **CC Contracts**: CC-01~CC-06 변경 없음. CC-07/08/09 순수 추가
- **스크립트**: 실행 스크립트 변경 없음
- **신규 추가만**: 기존 동작에 영향 없음

---

## v0.0.5

### 핵심 변경

| 변경 | 내용 |
|------|------|
| **Worktree 용어 도입** | branch, pull request(PR), merge를 명시적 운영 개념으로 정의. worktree 단위 작업 관리 체계 확립 |
| **Workspace Main 사용 원칙** | workflow topology 변경, orchestration 규칙 수정 등 핵심 변경은 반드시 worktree branch process를 통해서만 진행 |
| **Worktree Branch Process** | "생각 → 미리보기 → 실행" 단계 분리. Mermaid 기반 topology preview를 실행 전 필수 생성 |
| **Work Process 정의** | Planning Process(2-depth Planning)와 Discussion Process(Critique Discussion) 표준화 |
| **Hand-off Templates 확장** | PRD, SPEC, ADR, HITL Escalation Brief, Run Retrospective, Design Handoff Summary 6종 |
| **mso-process-template 스킬 분리** | `rules/ORCHESTRATOR.md`를 불변 정책만 남기고, 운영 상세를 `{mso-process-template}/SKILL.md`로 분리 |

### 수정 파일

**스킬 (신규)**
- `{mso-process-template}/SKILL.md` — 프로세스 규약, Hand-off 템플릿 레퍼런스
- `{mso-process-template}/core.md` — 실행 모델, 라우팅, Work Process, 에러 분류, 인프라 노트

**템플릿 (SoT: mso-process-template/templates/)**
- `{mso-process-template}/templates/PRD.md`
- `{mso-process-template}/templates/SPEC.md`
- `{mso-process-template}/templates/ADR.md`
- `{mso-process-template}/templates/HITL_ESCALATION_BRIEF.md`
- `{mso-process-template}/templates/RUN_RETROSPECTIVE.md`
- `{mso-process-template}/templates/DESIGN_HANDOFF_SUMMARY.md`

### 하위 호환 (v0.0.4 → v0.0.5)

- **스키마**: 변경 없음. DB 스키마 v1.5.0 유지
- **CC Contracts**: CC-01~CC-06 변경 없음
- **스크립트**: 실행 스크립트 변경 없음
- **신규 추가만**: 기존 동작에 영향 없음

---

## v0.0.4

### 핵심 변경

| 변경 | 내용 |
|------|------|
| **Global Audit DB** | Run-local DB → `audit_global.db`로 통합. Cross-Run 패턴 분석 기반 마련 |
| **스키마 v1.5.0** | `audit_logs`에 8개 work tracking 컬럼 추가. `suggestion_history` 테이블, 분석 뷰 3개 |
| **WAL 모드** | `PRAGMA journal_mode=WAL` 적용으로 동시 읽기 성능 향상 |
| **스크립트 독립화** | `init_db.py`, `append_from_payload.py`에서 `_shared` 의존성 제거. 4단계 DB 경로 resolve |
| **패턴 분석 시그널** | work_type imbalance, pattern_tag candidate, error hotspot 탐지 추가 |
| **Suggestion History** | 패턴 제안의 승인/거절 이력 기록. 3회 거절 시 자동 제안 제외 |

### work_type별 패턴 분석 시그널

| 시그널 | 조건 | 이벤트 |
|--------|------|--------|
| **Work Type Imbalance** | 단일 work_type > 50% | `improvement_proposal` |
| **Pattern Tag Candidate** | (work_type, files_affected) 3회+ 반복 | `improvement_proposal` |
| **Error Hotspot** | 동일 파일 fail 2회+ | `anomaly_detected` |

### 검증 결과

Claude Code(Opus 4.6)로 4개 에이전트 병렬 리뷰 수행. Schema 정합성·Script 로직·문서 정합성·Observability 스크립트 모두 PASS.

### 하위 호환 (v0.0.3 → v0.0.4)

- **DB 경로**: Global DB가 기본. 기존 Run-local 경로도 레거시 fallback으로 지원
- **스키마**: 8개 신규 컬럼은 모두 nullable. 기존 INSERT 쿼리는 수정 없이 동작
- **CC Contracts**: CC-01~CC-06 변경 없음

---

## v0.0.3

### 핵심 변경

| 변경 | 내용 |
|------|------|
| **execution_graph 도입** | flat 구조 → execution_graph DAG로 전면 교체. branch/merge/commit 노드 타입, SHA-256 tree_hash_ref 포함 |
| **node_snapshots 테이블** | Audit DB v1.4.0에 불변 스냅샷 기록용 테이블 추가. FTS5 + 인덱스 + lineage 뷰 |
| **에러 분류 체계** | 4가지 에러 유형(schema_validation_error / hallucination / timeout / hitl_block) × severity/action/max_retry 매핑 |
| **CC-06 계약** | mso-execution-design → mso-agent-audit-log 신규 계약. execution_graph 노드가 node_snapshots로 기록 가능해야 함 |
| **lifecycle_policy** | branch_ttl_days(7), artifact_retention_days(30), archive_on_merge(true), cleanup_job_interval_days(1) |
| **6개 에이전트 역할** | Provisioning, Execution, Handoff, Branching, Critic/Judge, Sentinel — 4단계 런타임 Phase에 매핑 |

### 검증 결과

Codex CLI(`gpt-5.3-codex-spark`, reasoning effort `xhigh`)로 2회 검증. 1차 `runtime-v003`/`runtime-v0.0.3` 태그 불일치 수정 후 7/7 PASS.

### 하위 호환 (v0.0.2 → v0.0.3)

- **스키마**: `additionalProperties: true` 유지. v0.0.2 아티팩트 로드는 가능하나 validation은 실패
- **build_plan.py**: 기존 flat 키 제거. `execution_graph` 구조만 출력 (clean break)
- **SQL**: `node_snapshots`는 순수 추가. 기존 테이블/트리거 변경 없음
- **CC Contracts**: CC-01~CC-05 유지, CC-06 추가
