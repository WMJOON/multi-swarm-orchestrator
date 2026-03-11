# 변경 이력

## v0.0.9

### 핵심 변경

#### Categorical Relation Inference — ontology.json 도입

| 변경 | 내용 |
|------|------|
| **ontology.json 신설** | chart.json(Ob 좌표)과 분리하여 Morphism(Hom) + Composition Table을 별도 파일로 관리. `20_mental-model/` 내 저장 |
| **Mode D Step 8: Morphism Inference** | 축 간 임베딩 강도 계산(R_ij) → 사상 유형 판별(`causes`, `requires`, `constrains`, `informs`, `contrasts_with`) → ontology.json 저장 |
| **Mode D Step 9: HITL 확인** | 추론된 morphisms를 사용자에게 제시 → 추가/수정/삭제 후 확정 |
| **Lazy Composition** | derived morphisms는 ontology.json에 저장하지 않고, `build_ontology.py --query` 실행 시 composition_table 기반 동적 계산 |
| **contrasts_with 합성 규칙** | 합성을 차단하지 않되 `"warning": "contrasts_with chain"` 플래그 표시. 소비자가 필터링/가중치 조정 판단 |

### 수정 파일

**신규**

| 파일 | 설명 |
|------|------|
| `skills/mso-mental-model-design/scripts/build_ontology.py` | chart.json → ontology.json 생성 + 스키마 검증(`--validate`) + lazy composition 쿼리(`--query "A→?"`, `"?→B"`, `"all"`) |
| `skills/mso-mental-model-design/schemas/ontology.schema.json` | ontology.json JSON Schema (category, objects, morphisms, composition_table) |

**수정**

| 파일 | 변경 |
|------|------|
| `skills/mso-mental-model-design/SKILL.md` | 핵심 정의에 Morphism/Composition Table/ontology.json/contrasts_with 규칙 추가. 저장 경로에 ontology.json 추가. Mode D에 Step 8(Morphism Inference) + Step 9(HITL) 추가. 상세 파일 참조에 build_ontology.py + ontology.schema.json 추가 |

### 하위 호환 (v0.0.8 → v0.0.9)

- **chart.json**: 변경 없음. 기존 chart.json 소비자에 영향 없음
- **ontology.json**: 순수 추가. Mode D 실행 시 자동 생성되나, 기존 워크플로우에서 참조하지 않으면 무시 가능
- **CC Contracts**: CC-01~CC-10 변경 없음
- **스크립트 CLI**: 기존 스크립트(`bootstrap_chart.py`, `bind_directives.py` 등) 인터페이스 변경 없음
- **directive_binding.json**: 스키마 변경 없음

---

## v0.0.8

### 핵심 변경

#### Part 1: Global Registry (`~/.mso-registry/`)

| 변경 | 내용 |
|------|------|
| **글로벌 레지스트리 경로** | Vertex Registry + Workflow Registry를 `~/.mso-registry/`로 승격. 프로젝트 간 공유 기본 |
| **이원 구조 해석(Resolution)** | 글로벌 → 워크스페이스 로컬 → seed 순서. UNION 머지, id 충돌 시 글로벌 우선 |
| **`registry_config.json`** | `_meta/` 하위에 버전, 해석 순서, 도메인 목록 관리 |
| **`init_global_registry.py`** | 글로벌 registry 초기화 + seed directive 복사 스크립트 |
| **`_load_registry_multi()`** | `bind_directives.py`에 다중 경로 로딩 함수 추가. 글로벌 + 로컬 동시 탐색 |

#### Part 2: Local Chart (Mode C/D)

| 변경 | 내용 |
|------|------|
| **chart.json** | 도메인별 의미 좌표계. axes(축 정의) + vertices(좌표 캐시) + metrics(직교성) |
| **Mode C: Chart Projection** | 기존 chart에 새 vertex 투영. `project_vertex.py` scaffold 구현 |
| **Mode D: Chart Bootstrap** | Purpose 기반 7단계 좌표계 구성. `bootstrap_chart.py` scaffold 구현 |
| **Sparsity 원칙** | 주도 축 ≥ 0.7, 보조 축 ≤ 0.3. 1 vertex = 1 핵심 관심사 |
| **LLM 의미 근사** | Embedding 모델 대신 LLM이 유사도 판단 (추후 교체 포인트) |
| **Purpose 정의** | Mode D 기준점. 문제 공간 경계를 정의하여 좌표계 안정성 확보 |

#### Part 3: Workflow Registry 글로벌화

| 변경 | 내용 |
|------|------|
| **`graph_search.py`** | **신규** — 글로벌 + 로컬 workflow_registry.json에서 intent 기반 워크플로우 검색 |
| **`registry_upsert.py`** | **신규** — 완료된 topology spec을 글로벌 레지스트리에 등록 |
| **Mode B 이원 구조** | topology SKILL.md + core.md에 글로벌 우선 해석 규칙 반영 |

### 수정 파일

**신규 스크립트**

| 파일 | 설명 |
|------|------|
| `skills/mso-mental-model-design/scripts/init_global_registry.py` | 글로벌 registry 초기화 + seed 복사 |
| `skills/mso-mental-model-design/scripts/project_vertex.py` | Mode C: 기존 chart에 vertex 투영 |
| `skills/mso-mental-model-design/scripts/bootstrap_chart.py` | Mode D: 도메인 chart.json 골격 생성 |
| `skills/mso-workflow-topology-design/scripts/graph_search.py` | Mode B: intent 기반 워크플로우 검색 |
| `skills/mso-workflow-topology-design/scripts/registry_upsert.py` | 워크플로우 메타데이터 글로벌 등록 |

**수정 스크립트**

| 파일 | 변경 |
|------|------|
| `skills/mso-mental-model-design/scripts/bind_directives.py` | `_load_registry_multi()` 추가, `--registry` default `~/.mso-registry`, `--local-registry` 옵션 |
| `skills/mso-mental-model-design/scripts/search_directives.py` | `--registry` default 변경, `--local-registry` 옵션, `_load_registry_multi` 사용 |
| `skills/mso-mental-model-design/scripts/register_directive.py` | `--registry` default 변경, `--local` 플래그, `registry_config.json` domains 자동 갱신 |

**문서**

| 파일 | 변경 |
|------|------|
| `skills/mso-mental-model-design/SKILL.md` | Registry 해석 순서 테이블, Mode C/D 스크립트 참조, Local Chart 개념 |
| `skills/mso-mental-model-design/core.md` | Input Interface 이원 구조, init 안내 |
| `skills/mso-workflow-topology-design/SKILL.md` | Mode B 글로벌 경로, graph_search/registry_upsert 참조 |
| `skills/mso-workflow-topology-design/core.md` | Registry 해석 규칙 (Mode B) 섹션 추가 |
| `README.md` | v0.0.8 변경 이력 |

### 하위 호환 (v0.0.7 → v0.0.8)

- **레지스트리 경로**: `~/.mso-registry/` 미존재 시 `init_global_registry.py` 실행 필요. 워크스페이스 로컬 경로는 fallback으로 유지되어 기존 데이터 접근 가능
- **스키마**: DB 스키마 v1.5.0 유지. chart.json은 순수 추가
- **CC Contracts**: CC-01~CC-10 변경 없음
- **스크립트 CLI**: `--registry` 기본값 변경(빈 문자열 → `~/.mso-registry`). 명시적으로 `--registry`를 지정하던 기존 호출은 영향 없음
- **Mode B fallback**: workflow_registry.json 미존재 시 자동 Mode A fallback 유지

---

## v0.0.7

### 핵심 변경

#### Part 1: Agent Teams + Jewels

| 변경 | 내용 |
|------|------|
| **Agent Teams + Jewels 패턴** | mso-workflow-optimizer에 4-teammate 아키텍처 도입. Proactive Async 패턴으로 audit_global.db 상시 모니터링 |
| **provider-free mso-agent-collaboration 연계** | 단일 세션 외에 티켓 dispatch 방식으로 Jewels 패턴 구현 가능 (CC-10) |
| **CC-10 계약 추가** | optimizer(Phase 0) → mso-agent-collaboration teammate dispatch 계약 |
| **CC-07~09 governance 등록** | _cc_defaults.py에 CC-07~09 계약 추가, CC_VERSION 0.0.7 갱신 |
| **tier_downgrade Jewel 타입** | module.agent-team.md에 tier_downgrade 타입 명세 추가 |
| **Claude Code Hook 3종** | PostToolUse(jewels 경로) + PostToolUse(report 경로) + SubagentStop(jewel-producer) |

#### Part 2: Topology Motif + Graph Search Loader + Tier Escalation

| 변경 | 내용 |
|------|------|
| **Topology Motif 도입** | 6가지 표준 구조 패턴(Chain/Star/Fork-Join/Loop/Diamond/Switch) 정의. 기존 topology_type과 매핑 |
| **Vertex Composition** | Task Node에 실행 단위 유형(agent/skill/tool/model) 지정 체계. `Workflow Graph = Motif + Vertex Mapping` |
| **Graph Search Loader (Mode B)** | mso-workflow-topology-design에 Mode A(신규 설계)/Mode B(레지스트리 검색) 이원화 |
| **Tier Escalation** | mso-workflow-optimizer에 `pattern_stability = frequency × success_rate` 기반 자동 에스컬레이션. L30→L20→L10 |

#### Part 3: Vertex Registry (mso-mental-model-design 재설계)

| 변경 | 내용 |
|------|------|
| **Directive 도입** | Vertex에 바인딩되는 도메인 지식 단위. type: framework / instruction / prompt |
| **Vertex Registry** | Directive를 택소노미로 분류·검색·관리하는 MD 파일 기반 저장소 |
| **mental_model_bundle.json → directive_binding.json** | CC-02 출력 형식 변경 |
| **Seed Directives** | `directives/analysis/` (MECE, Root Cause Analysis) + `directives/general/` (Generic Reasoning) |

#### Part 4: 스킬 표준화

| 변경 | 내용 |
|------|------|
| **frontmatter 표준화** | 전체 10개 스킬 frontmatter를 skill-creator 표준(`name` + `description`만)으로 통일 |
| **description 보강** | 전체 10개 스킬에 "Use when" 트리거 추가 |
| **extraneous file 삭제** | mso-workflow-optimizer/DIRECTORY.md 제거 |

### 수정 파일

**Part 1 파일**

| 파일 | 변경 |
|------|------|
| `skills/mso-workflow-optimizer/modules/module.agent-team.md` | tier_downgrade 추가, Hook 3종 추가 |
| `skills/mso-workflow-optimizer/modules/module.agent-decision.md` | Signal C에 Jewels 입력 추가 |
| `skills/mso-agent-collaboration/core.md` | when_unsure 레거시 텍스트 교체 |
| `skills/mso-skill-governance/SKILL.md` | CC 검증 범위 CC-10으로 확장 |
| `skills/mso-skill-governance/scripts/_cc_defaults.py` | CC-07~10 등록 |
| `skills/mso-skill-governance/scripts/validate_cc_contracts.py` | CC-07~10 매핑 |
| `docs/pipelines.md` | CC-10 계약 + Mermaid 업데이트 |

**Part 2 파일**

| 파일 | 변경 |
|------|------|
| `skills/mso-workflow-topology-design/SKILL.md` | Mode A/B 이원화, JSON 스키마 축약 |
| `skills/mso-workflow-topology-design/modules/module.motif-vocabulary.md` | **신규** — Motif 6종 정의·매핑·구분 기준 |
| `skills/mso-workflow-topology-design/modules/module.vertex-composition.md` | **신규** — Vertex 4종 정의·선택 기준 |
| `skills/mso-workflow-topology-design/modules/module.graph-search-loader.md` | **신규** — 레지스트리 구조·검색 점수·Vertex Binding |
| `skills/mso-workflow-topology-design/modules/module.topology-selection.md` | Motif 식별 Step 추가, 중복 축약 |
| `skills/mso-workflow-optimizer/SKILL.md` | Tier Escalation 섹션 추가 |

**Part 3 파일 (Vertex Registry)**

| 파일 | 변경 |
|------|------|
| `skills/mso-mental-model-design/SKILL.md` | 전면 재설계 — Vertex Registry + Directive 택소노미 |
| `skills/mso-mental-model-design/core.md` | 재작성 — Directive 인터페이스 |
| `skills/mso-mental-model-design/modules/module.directive-taxonomy.md` | **신규** — 택소노미 구조, reserved domains |
| `skills/mso-mental-model-design/modules/module.vertex-binding.md` | **신규** — 검색·바인딩 규칙, CC-02 호환 |
| `skills/mso-mental-model-design/schemas/directive_binding.schema.json` | **신규** — 바인딩 출력 스키마 |
| `skills/mso-mental-model-design/schemas/directive.frontmatter.schema.json` | **신규** — frontmatter 스키마 |
| `skills/mso-mental-model-design/directives/` | **신규** — seed directives (3개) |
| `skills/mso-mental-model-design/schemas/mental_model_bundle.schema.json` | **삭제** |
| `skills/mso-mental-model-design/scripts/build_bundle.py` | **삭제** |
| `skills/mso-mental-model-design/modules/module.bundle-contract.md` | **삭제** |
| `skills/mso-mental-model-design/modules/module.loading-policy.md` | **삭제** |
| `skills/mso-mental-model-design/modules/module.routing-kpi.md` | **삭제** |
| `skills/mso-process-template/core.md` | 수정 — `mental_model_bundle.json` → `directive_binding.json` |
| `docs/getting-started.md` | 수정 — Vertex Registry 디렉토리·스크립트 반영 |
| `docs/pipelines.md` | 수정 — Design 파이프라인 설명 업데이트 |
| `docs/usage_matrix.md` | 수정 — mental-model-design 설명 업데이트 |

**Part 4 파일**

- 전체 10개 `SKILL.md` — frontmatter 표준화 (`disable-model-invocation`, `version` 제거)
- `skills/mso-workflow-optimizer/DIRECTORY.md` — **삭제**

### 하위 호환 (v0.0.6 → v0.0.7)

- **스키마**: DB 스키마 v1.5.0 유지. workflow_topology_spec.json에 `vertex_type`, `metadata.motif`, `metadata.motif_composition` 필드 추가 (optional)
- **CC Contracts**: CC-01~09 변경 없음. CC-10 순수 추가
- **단일 세션 모드**: 변경 없음. Phase 0는 선택적
- **Mode B**: 레지스트리(`workflow_registry.json`) 미존재 시 자동 Mode A fallback
- **Tier Escalation**: audit_global.db 기반 동적 계산. 기존 3-Signal 판단 로직과 병행
- **Hook**: Claude Code 환경에서만 활성화. 미지원 환경에서는 무시됨
- **CC-10 governance**: 단일 세션 모드 사용자는 warn 처리 (파이프라인 차단 없음)

---

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
