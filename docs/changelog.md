# 변경 이력

## v0.9.0 (2026-07-17) — Work-Memory Release Governance

> 교훈에 유효기간을 부여한다. release-note(RN)가 상태 축의 앵커가 되어, 릴리스가 전제를 바꿀 때 어떤 UD/AD/TS/PT/PR 이 더 이상 동작하지 않는지를 append-only 그래프에서 도출한다.

### Added

| 추가 | 내용 |
|------|------|
| `release-record/release-note.jsonl` (RN) | work-memory 9번째 entry 타입. `metadata.version/released_at/kind(release\|rollback)/scope`. current 는 저장하지 않고 derived view 로 도출한다. |
| relation 4종 | `released-in`(TS/UD/AD → RN), `verified-in` / `invalidated-by`(UD/AD/TS/PT/PR → RN), `rolls-back`(RN → RN). 롤백은 기존 RN 수정이 아니라 `kind=rollback` RN append + `rolls-back` 엣지다. |
| `skills/mso-work-memory/scripts/wm_release.py` | `current` / `validity` / `context` CLI. stdlib-only — copy-form hook 배포를 위해 wm_node.py 와 독립. |
| `skills/mso-work-memory/references/queries/` | TTL projection 용 SPARQL 3종 (`release-current`, `release-invalidated-active`, `release-revalidation-candidates`). JSONL CLI 와 같은 파생 규칙의 두 구현. |
| `skills/mso-work-memory/hooks/release-context.sh` | SessionStart(startup/compact/resume) 훅. 현재 릴리스·무효화 교훈·재유효 후보를 컨텍스트로 주입. RN 미사용 프로젝트에서는 무출력. |

### Changed

- `mso-work-memory` schema v1.3.0 / SKILL.md v0.7.0 — "릴리스·유효성 거버넌스" 섹션 신설 (derived current, 롤백 이벤트, 롤백 캐스케이드 derived, PR.status 근거 트레일).
- TBox 에 `wm:ReleaseNote` 클래스와 4개 ObjectProperty 추가, SHACL 에 RN target 제약 + `rolls-back` subject 제약(`sh:targetSubjectsOf`) 추가.
- `wm_node.py` 기본 어휘와 `wm_to_ttl.py` TYPE_CLASS/RELATION_PREDICATE/디스커버리에 `release-record/` 반영.
- `mso-repository-setup` `init.py --hook` 이 `release-context.sh` + `wm_release.py` 를 copy-form 으로 복사하고 SessionStart(startup 포함)에 등록한다.
- 테스트 확장: release lifecycle e2e(릴리스→무효화→롤백→재유효 후보), `rolls-back` subject 제약, hook 전달 의미론 (10 passed).

## v0.8.2 (2026-07-09) — Workflow Observation alias

> workflow graph 노출을 `mso-workflow-observation`이라는 좁은 public rail로 제공한다.

### Added

| 추가 | 내용 |
|------|------|
| `skills/mso-workflow-observation/` | `mso-graph-observability`의 workflow scope를 감싸는 alias skill. `execution-rail.md`, `artifact-stream-graph.md`, `repository-graph.md`를 관측 산출물로 삼는다. |
| `scripts/mso-workflow-observation.py` | 내부적으로 `skills/mso-graph-observability/scripts/observe_graph.py`를 호출하는 wrapper. |

### Changed

- `mso-orchestration` 라우팅에 `mso-workflow-observation`, `workflow observation`, `workflow graph 노출` 트리거를 추가했다.
- `install.sh` 설치 대상에 `mso-workflow-observation`을 포함했다.
- Mermaid node label line break를 `<br/>`로 통일해 GitHub/Obsidian 계열 Mermaid renderer에서 graph가 깨질 가능성을 낮췄다.
- control-only 뷰는 `workflow-graph.md` 대신 `execution-rail.md`로 생성한다. artifact 소비/생산까지 포함한 통합 뷰는 `repository-graph.md`가 담당한다.
- `execution-rail.md`는 Artifact node와 Artifact Node Index를 제외한다. Artifact 소비/생산 및 provenance는 `artifact-stream-graph.md`와 `repository-graph.md`에서 확인한다.

## v0.8.1 (2026-07-08) — Hermes Bridge 지원 폐기

> `mso-hermes-bridge`를 MSO 기본 실행 plane에서 제거한다. Hermes Agent를 외부 Executor로 붙이는 방식은 skill/runtime 배선을 늘려 오류 표면이 커졌으므로, work-memory/workflow 정리와 실행 자동화는 LangGraph 기반 artifact 경로로 집중한다.

### Removed

| 제거 | 내용 |
|------|------|
| `skills/mso-hermes-bridge/` | Hermes Agent 외부 Executor 위임 스킬 디렉토리를 제거했다. |
| `mso-orchestration` 라우팅 | Hermes Bridge 트리거와 초기화 커맨드를 제거했다. |
| `install.sh` | `SKILLS` 배열에서 `mso-hermes-bridge`를 제거했다. |
| README `## Skills` 테이블 | `mso-hermes-bridge` 행을 제거했다. |
| `mso-repository-setup` | `init.py --cleanup-hermes <project>`를 추가해 v0.8.0 적용 후 남은 Hermes Bridge 설정을 정리할 수 있게 했다. |

### Direction

- execution plane은 `mso-workflow-optimizer`를 통해 TTL workflow를 LangGraph artifact로 컴파일하는 경로를 우선한다.
- 외부 agent 위임은 MSO core skill을 늘리는 방식이 아니라 provider policy / generated graph adapter 수준에서 재검토한다.
- cleanup은 MSO가 만든 `.hermes/mso-context.md`, `.hermes/bridge.sh`, 전역 `mso-hermes-bridge` skill symlink만 대상으로 하며, Hermes 본체 설정(`~/.hermes/.env`, gateway/launchd)은 건드리지 않는다.

## v0.8.0 (2026-07-06) — 폐기됨: Hermes Bridge 외부 Executor 위임

> Hermes Agent를 MSO workflow의 외부 Executor로 위임하는 `mso-hermes-bridge` 스킬 추가. `wf:delegates_to :hermes-executor`로 선언된 step을 Hermes API Server(OpenAI-compatible, port 8642)로 HTTP 위임하고 Runs API 폴링으로 결과를 수집한다. MSO ROADMAP §7 Execution Metadata의 ExecutionMethod=api 구현 사례.

> 상태: v0.8.1에서 기본 지원 폐기. 이 항목은 실험 이력으로만 유지한다.

### Added

| 추가 | 내용 |
|------|------|
| `skills/mso-hermes-bridge/` | Hermes Agent 외부 Executor 위임 스킬. `scripts/hermes_bridge.py`(HTTP 위임 + Runs API 폴링), `scripts/setup-with-hermes.sh`(MSO init + Hermes 세팅 통합), `scripts/workflow_context.py`, `scripts/bridge.sh`(cron/launchd 호출용 wrapper), `hooks/hermes-repo-setup.sh`(기존 repository에 Hermes만 추가), `references/cron-examples.md`(crontab/launchd 예시). |
| `mso-orchestration` 라우팅 | Hermes 위임 트리거(`hermes 위임`, `hermes-bridge`, `외부 에이전트 위임`, `delegates_to hermes`)와 초기화 커맨드를 SKILL.md에 등록. |
| `install.sh` | `SKILLS` 배열에 `mso-hermes-bridge` 등록. |
| README `## Skills` 테이블 | `mso-hermes-bridge` 행 추가. |

### Design

- ExecutionSubject=Agent(Hermes), ExecutionMethod=api — MSO ROADMAP §7 Execution Metadata에서 선언한 실행 방식의 첫 구현체.

## v0.7.1 (2026-07-03) — UUG grounding 연동 넛지

> UUG(uug-grounding)가 발화에서 grounding한 `target_project`가 현재 레포와 다를 때만, 그 프로젝트의 `agent-context/` 위치를 `UserPromptSubmit` 훅으로 1줄 넛지한다. MSO만 설치하고 UUG를 세팅하지 않은 사용자에게는 어떤 흔적도 남기지 않는다(설치 시점 + 런타임 이중 게이팅).

### Added

| 추가 | 내용 |
|------|------|
| `hooks/uug-context-hook.py` (mso-work-memory) | `UserPromptSubmit` 훅. `ug.py dispatch --json`을 read-only subprocess로 호출해 `intent_id`/`target_project`를 읽는다. 게이팅 intent(기본 `work-on-project`)에 걸리고 `target_project ≠ $CLAUDE_PROJECT_DIR`이며 그 프로젝트에 `agent-context/`가 있을 때만 1줄 넛지, 그 외에는 항상 침묵·항상 exit 0. `ug.py` 부재/오류/timeout 시 조용히 no-op. 게이팅은 `MSO_UUG_CONTEXT_INTENTS`, 비활성화는 `MSO_UUG_CONTEXT_DISABLED=1`. |
| `init.py --hook` 설치 시점 게이팅 (mso-repository-setup) | `_find_uug_ug()`로 이 머신에 uug-grounding이 있는지 먼저 확인한다. 없으면 `uug-context-hook.py` 복사와 `settings.json` `UserPromptSubmit` 등록 자체를 생략한다 — MSO만 쓰는 사용자의 설정 파일에는 이 훅이 전혀 나타나지 않는다. |

### Design

- uug-grounding SKILL.md의 "MSO는 UUG를 모른다(단방향)" 경계에 대한 의도적 예외 — MSO가 UUG의 안정된 public CLI(`ug.py`)를 **read-only**로만 호출한다(역방향 없음, UUG는 여전히 MSO를 모름).
- 참조 대상은 cwd 프로젝트가 아니라 **UUG가 grounding한 target_project** — UUG 도입 목적 자체가 발화가 가리키는 프로젝트가 cwd와 다를 수 있다는 것이므로, cwd 비교만으로는 UUG를 쓰는 의미가 없다.
- Claude provider 전용 등록 — Codex는 `SessionStart` 밖 `UserPromptSubmit` stdout 전달 의미론이 미검증이라 보류(`work-memory-check.sh`가 SessionStart에만 넛지를 거는 것과 동일한 근거).

## v0.7.0 (2026-07-02) — Repository Graph: edge-first ontology (Rail/Stream)

> **Repository Graph = Execution Graph(Control Plane) + Artifact Stream Graph(Data Plane).** edge를 일급 인스턴스로 승격하고, Execution 주체(hand_off)·WorkflowGraph 평가 단위·Property Chain·Provenance·Trust 계산까지 온톨로지 레이어 v0.7~v0.10을 한 릴리스로 담았다.

### Added

| 추가 | 내용 |
|------|------|
| Rail/Stream 온톨로지 | `wf:Edge ⊃ Rail(제어)/Stream(공급망)` reification. railType: default/reads/delegates_to/escalates_to/measured_by/measures/evolves_to/tests_to. streamType: consumed_by/produces_to/evidence_of. 소스 SSOT는 `references/schemas/v07/{tbox,shapes}.ttl`, `schemas_to_tbox.py`가 생성·drift 가드. |
| Execution 모델 | `wf:Execution ⊃ Task/Decision/Eval` + `hasSubject`(self\|human\|model\|system\|workflow, 기본 self) + `subjectDetail`/`realizedBy`(Skill=sub-workflow). hand_off는 Execution→Execution 주체 전환 — HITL은 `escalates_to → Decision(human)` rail로 파생. |
| Terminal | `wf:Terminal ⊃ Start/End`. workflow당 Start=1, End≥1. Task out default-Rail 정확히 1 — 다중 분기는 shape 수준에서 불가능. |
| WorkflowGraph 평가 | `Eval --measures--> Workflow` = 소비 Artifact + Execution + 생산 Artifact closure 측정. `metricDimension` 7종. oracle 대상(evolves_to/tests_to)은 Workflow ∪ **Artifact** — 지식 artifact(prompt/ontology/KB)도 개선 대상. |
| Property Chain | `consumed_by ∘ produces_to = evidence_of` — OWL 공리(술어 projection) + `materialize_v07.py` SPARQL 파생. derived Stream은 `wf:derived`+`derivedFrom`로 표시, `.inferred.ttl` sibling 출력(정본 불변·멱등), 관측 `evidence_of*` 표기. |
| Provenance | Artifact: author/version/timestamp/validation/coverage/confidence (PROV-O 정렬 주석). Execution: method/policy/timestamp. SHACL은 값 형식만 오류, 충족은 validator 커버리지 경고. |
| Trust 계산 | `trust_v07.py` — Trust Policy(내장+YAML 재정의) 기반 Artifact/Execution/WorkflowGraph/repository trust + evidence 계보 전파(GIGO) + `measures` rail별 Oracle Decision 제안. **Trust는 저장하지 않는다** — 산출물은 리포트/JSON뿐. |
| validate_abox.py | TTL ABox(SSOT) 직접 검증 진입점. v0.6/v0.7 파일 단위 자동 감지 이중 스택. v0.7: SHACL + oracle disjoint/partition/loop control python 검사. v0.6: SHACL + directory shape + step multi-outgoing/legacy YAML 거버넌스 경고. |
| migrate_abox_v06_to_v07.py | v0.6→v0.7 변환. legacy Phase→Workflow 승격, judge→hasSubject, goto 문자열 전역 해석, usesTool→위임 Execution 합성, Start/End 합성, wf:target→measures rail. |
| observe_v07.py | Rail/Stream native 렌더러 — 호환 projection 없이 직접 순회. Start/End 정본 렌더, hand_off/measures edge, artifactType 무추론(unspecified 표기), provenance 열. |
| workflow-check.sh | hook 자산: `.abox.ttl` 저장 시 validate → materialize → trust report → observe 체인 자동 실행. |

### Changed

| 변경 | 내용 |
|------|------|
| 출력 규약 | 분석 리포트는 `agent-context/observability/*`, 시각화 md는 `agent-context/observability/graph/*`로 분리. 구 배치 리포트 잔재는 자동 제거. |
| 경계 정리 (v0.6.7) | Mermaid 렌더 규칙 서술을 observability SKILL 단일 소유로 이동. 관측기의 Step→Decision 조용한 승격 제거(shape-violation 표기). artifact_type은 TTL 명시 선언(`wf:artifactType`) > index > 추론. SSOT 거버넌스 판정은 validate_abox 소유. |
| v0.6 호환 | `wf_v07.project_v06_compat`는 deprecated — 외부 v0.6 소비자 전환 지원용만 유지. |


## v0.6.6 (2026-07-02) — Workflow shape and observability hardening

> **Workflow는 workflow로, 선택은 Decision으로, 산출물 측정은 Eval로 고정.** phase/validation 잔재를 정본 topology에서 제거하고, graph observability가 Mermaid 문서형 노드와 Eval target/measured artifact 관계를 명확히 렌더링하도록 강화했다.

### Changed

| 변경 | 내용 |
|------|------|
| workflow shape guard | Eval은 target workflow와 targetArtifact를 가져야 하며, targetArtifact는 target workflow의 Task/Decision 산출물이어야 한다. Eval/Decision은 2개 이상의 branch를 가져야 하고, branch와 같은 방향의 중복 `next` edge를 금지한다. |
| decision/eval wording | 선택·판단·라우팅은 Decision, 산출물 측정·평가·검증은 Eval이라는 설명을 `mso-workflow-design`에 정렬했다. |
| legacy migration | YAML의 `phases`를 `workflows`로, `type: validation`을 `type: eval`로 전환하는 migration script와 regression test를 추가했다. |
| observability renderer | repository/workflow/artifact graph가 Mermaid 문서형 artifact, Eval `target` edge, measured artifact identity, dotted `delegates_to` edge를 안정적으로 렌더링하도록 개선했다. |
| TBox/SHACL sync | workflow TBox와 generated SHACL shape를 새 Eval/Decision/Artifact stream 제약에 맞춰 재생성했다. |
| 민감정보 정리 | 배포 파일에 남아 있던 개인 식별 예시 owner/evaluator를 generic fixture로 치환하고, secret/token/absolute path 후보 스캔을 통과했다. |
| 버전 정렬 | README, changelog, 모든 MSO skill frontmatter 버전을 v0.6.6으로 정렬. |

## v0.6.5 (2026-07-01) — Eval artifact provenance

> **Oracle Eval이 평가하는 artifact를 target workflow의 실제 산출물로 고정.** TTL ABox가 SSOT인 상황에서 Eval의 `targetArtifact`가 target workflow 내부 task/decision 산출물과 어긋나면 shape 검증이 실패하고, 관측 그래프는 같은 산출물을 `produces`와 `measured_by`가 공유하는 단일 data node로 렌더링한다.

### Changed

| 변경 | 내용 |
|------|------|
| eval targetArtifact shape | `Eval --target--> workflow`의 plain `targetArtifact`는 target workflow의 `wf:hasNode` 아래 `Task`/`Decision`이 생산한 `wf:deliverables` 또는 output directory artifact와 일치해야 함. |
| workflow validator | `wf_to_ttl.py validate`에 `eval_target_artifact_mismatches` 검증 결과를 추가하고, 위반 시 `ok=false`로 실패 처리. |
| graph observability | Eval measured artifact가 target workflow 산출물과 일치하면 producer의 data ref를 재사용해 `produces`와 `measured_by`가 같은 Mermaid node에 붙도록 수정. |
| target scope | root-scoped workflow에서 sibling workflow를 Eval target/evolves로 참조할 때 workflow URI scope가 현재 node scope로 잘못 좁혀지지 않도록 보정. |
| templates/tests | root workflow template의 testing Eval target을 development 산출물 평가로 정렬하고, provenance shape 및 rendering identity regression test 추가. |
| 버전 정렬 | README, changelog, 모든 MSO skill frontmatter 버전을 v0.6.5로 정렬. |

## v0.6.4 (2026-07-01) — Decision/Validation loop gates

> **Eval을 산출물 평가/evolve gate로 좁히고, 결정적 검증·HITL 승인 루프는 Decision gate로 표현.** TTL ABox가 SSOT인 상황에서 `wf:Decision + wf:Validation` 검증 게이트와 `decisionSubject="user"` 승인 게이트를 loop control shape가 인식하도록 정리했다.

### Changed

| 변경 | 내용 |
|------|------|
| loop control shape | `wf:next`/branch 순환의 제어점을 `wf:Eval`뿐 아니라 `wf:Validation` gate, `decisionSubject="user"`인 `wf:Decision` gate까지 인정. agent Decision만 있는 재귀 루프는 계속 실패. |
| workflow validator | `wf_to_ttl.py` 내부 feedback-loop detector를 SHACL과 같은 정책으로 정렬. |
| eval shape guard | Eval은 직접 `wf:next`를 쓰지 않고 fail/pass branch를 사용하며, fail branch downstream Task가 Eval target workflow를 `wf:evolves`로 선언해야 한다는 v0.6.3 이후 정책 유지. |
| regression tests | user Decision loop, TTL-only `Decision + Validation` loop, Eval-controlled loop, uncontrolled agent Decision loop 테스트를 분리해 회귀 방지. |
| observability contract | TTL 관측에서 deterministic validation gate는 Eval이 아니라 Decision으로 렌더링될 수 있음을 명확화. |
| 버전 정렬 | README, changelog, 모든 MSO skill frontmatter 버전을 v0.6.4로 정렬. |

## v0.6.3 (2026-06-30) — Stop reminder throttle

> **Stop hook이 매 턴 사용자에게 같은 안내를 반복하는 문제를 상태 파일로 완화.** reminder 출력은 1회 표시 뒤 다음 Stop 1회를 억제하지만, work-memory 자동 커밋 백스톱은 계속 실행한다.

### Changed

| 변경 | 내용 |
|------|------|
| stop-check hook | `mso-work-memory/hooks/stop-check.sh` 추가. `.claude/state/stop-check.state`를 사용해 첫 Stop 출력 후 다음 Stop 1회를 무출력으로 통과시키고 state를 삭제. |
| setup copy-form | `mso-repository-setup init.py --hook --provider claude`가 `stop-check.sh`를 `.claude/scripts/`로 복사하고 Stop hook에 등록. |
| state gitignore | setup 대상 `.gitignore`에 `.claude/state/` 추가. 상태 파일은 local runtime artifact로 유지. |
| hook 경계 | throttle은 사용자 reminder 출력에만 적용. `commit-work-memory.sh`는 Stop/PreCompact에서 계속 실행해 work-memory 변경분 커밋 백스톱을 유지. |
| 버전 정렬 | README, changelog, `mso-work-memory`, `mso-repository-setup` 버전을 v0.6.3으로 정렬. |

## v0.6.2 (2026-06-30) — Worklog semantic boundary + cloud hand-off

> **worklog를 workflow TTL node 실행 기록으로 재정의하고, Stop hook 자동 생성과 cloud hook side effect 의존을 제거.** `auditlog`는 도구 실행 사실, `worklog`는 workflow `node -> node` 레일 실행, `AD/IN/TS`는 레일 밖 판단과 예외 기록을 담당한다.

### Changed

| 변경 | 내용 |
|------|------|
| worklog 의미 | `worklog`는 세션 종료 요약이나 auditlog 요약이 아니라 workflow TTL node 실행 기록으로 제한. workflow node를 특정할 수 없으면 `AD` 또는 `IN/TS` 후보로 기록. |
| hook 정책 | Stop/PreCompact는 `commit-work-memory.sh`만 수행. Stop hook은 worklog를 자동 생성하지 않음. `work-memory-check`는 SessionStart(compact/resume)에서 기록 판단 넛지만 제공. |
| cloud hand-off | Codex cloud 같은 ephemeral runtime에서 project hook side effect나 로컬 커밋을 다음 에이전트 기억 보장으로 보지 않음. 최종 답변, diff, 커밋 가능한 tracked file을 hand-off 기준으로 명시. |
| repository setup | `mso-repository-setup` hook 생성 메시지와 `init.py` 주석을 `worklog.py`/Stop worklog 중심에서 `commit-work-memory` + 판단 넛지 구조로 정정. |
| 운영 문서 | `architecture.md`, `getting-started.md`의 hook 흐름, 파일 레이아웃, 수동 hook 테스트 예시에서 자동 worklog 표현 제거. |
| work-memory guide | `work-memory-judgment.md`에 workflow TTL node를 특정할 수 있을 때만 `worklog`를 쓰고, 레일 밖 작업은 `AD` 또는 `IN/TS`로 기록한다는 판단 모델 추가. |
| schema 문구 | `schema.yaml`의 WL 설명을 자동 일별 로그가 아니라 workflow TTL node 실행 기록으로 정정. |
| hook script 주석 | `commit-work-memory.sh`, `work-memory-check.sh` 주석을 수동 worklog/track/insight까지 포함하는 work-memory 변경분 기준으로 정정. |
| 버전 정렬 | README, changelog, `mso-work-memory`, `mso-repository-setup` 버전을 v0.6.2로 정렬. |

## v0.6.1 (2026-06-30) — Phase-less Workflow Model

> **phase 중간 계층을 workflow 재귀로 흡수하는 구현 완료.** v0.6.0 oracle graph의 `has_subWorkflow` 재귀 계층을 끝까지 밀어 `wf:Phase`/`wf:Validation`/`wf:dependsOn`/`wf:WorkflowRef`를 정본 생성물에서 제거했다.

### Changed

| 항목 | 내용 |
|------|------|
| phase-less 모델 | `workflow -> phase -> node` 대신 `workflow --hasNode--> node`와 `workflow --has_subWorkflow--> workflow`로 멤버십과 lifecycle을 표현. |
| TBox/SHACL | `Phase`, `WorkflowRef`, `dependsOn`, `hasWorkflowRef`, `Validation` 정본 생성을 제거하고 `Workflow`, `hasNode`, `has_subWorkflow`, `inWorkflow`, `Eval` 중심으로 재생성. |
| YAML import | top-level `workflows[]`를 정본 입력으로 승격. legacy `phases[]`/named phase는 읽기 호환으로 `wf:Workflow`에 투영하고 warning을 낸다. |
| validation 정리 | legacy `type: validation`은 `wf:Eval` + `oracle_type=metric`으로 투영. 신규 scaffold/docs는 `eval`을 사용. |
| observability | process unit을 workflow/sub-workflow 중심으로 정리하고 legacy `wf:Phase`는 읽기 호환으로만 포함. |
| templates/tests | root/module workflow template, generated ABox 예시, workflow-design/graph-observability tests를 phase-less 모델에 맞춰 갱신. |

상세 설계: `planning/mso-v0.6.1-SPEC-phase-less-workflow.md`.

## v0.6.0 (2026-06-30) — Oracle Graph (self-improvement stratification)

> **workflow self-improvement loop 의 자기참조를 edge 종류(base/oracle)로 차단하는 oracle graph 레이어 추가.** skill = sub-workflow 이므로 self-improvement 를 base workflow 에 직접 넣으면 evolve 행위가 자기 자신으로 되돌아오는 순환이 생긴다. design-time SHACL 이 자기참조를 막고, run-time optimizer governance 가 evolve 확정을 control plane 으로 gate 하는 이중 방어.

### Added

| 항목 | 내용 |
|------|------|
| oracle graph 모델 | 레이어를 노드 type 아닌 **edge** 로 구분. `delegatesTo`(base 수단) ↔ `exercises`(평가 실행, 대상 불변)·`evolves`(개선) (oracle 대상), 경계 `measures`. 계층 `workflow --has_subWorkflow--> workflow`(대칭: oracle-workflow = sub-workflow 의 meta). evolves/exercises/has_subWorkflow 모두 workflow→workflow. |
| SHACL invariant | `EvolvesSelfShape`(자기 evolve) + `EvolvesStratificationShape`(C·W 가 `has_subWorkflow*` 연결 시 위반 — C∩W=∅) + `SubWorkflowPartitionShape`(workflow 부모 ≤1 — 형제·oracle disjoint). 실 yaml→TTL emission 데이터로 검출. |
| artifact 노드화 | `wf:Artifact` + `produces`/`consumes`/`check`/`measures` (orphan 탐지·supply-chain view). |
| oracle view | `mso-graph-observability` 가 `oracle-graph.md`(`evolves`/`exercises`/`has_subWorkflow`/`target` edge-필터) 자동 생성. |
| control plane governance | `mso-workflow-optimizer` `governance.evolves`(execution=propose-only / control=confirm-after-human-or-metric-oracle) + halt_on `propose_evolution` — evolve 확정은 control plane oracle 권위(SPEC §5). |

상세 설계: `planning/mso-v0.6.0-SPEC-oracle-graph.md`.

## v0.5.0 (2026-06-29) — Workflow/Artifact/Eval graph observability

> **workflow, artifact stream, eval node/edge를 분리해 관측 가능하게 정리.** repository workflow design을 agentic workflow, artifact supply-chain, eval gate 세 관점으로 보고, 각 관점의 graph shape requirements를 slot으로 다룬다. 대화는 비어 있는 slot을 채우기 위한 slot-filling 과정이며, 최종 정본은 TTL ABox다. `wf:Oracle` 노드 타입을 `wf:Eval`로 전환하고, `oracle`은 eval 수행 주체/권위 필드로 남긴다. legacy YAML의 `type: oracle`은 import 시 `wf:Eval`로 투영하고, TTL migration 검증 후 legacy YAML은 제거한다.

### Changed

| 변경 | 내용 |
|------|------|
| v0.5.0 design lens | agentic workflow / artifact supply-chain / eval gate 3관점을 graph shape slot group으로 보고, 대화를 통해 slot-filling 후 안정적인 workflow topology로 기록하는 원칙 추가 |
| `mso-workflow-design` | TTL ABox에서 workflow, artifact stream, eval의 node/edge shape 생성과 검증 책임을 명시. `wf:Eval`, `wf:targetArtifact`, `wf:orderTarget`, `wf:orderArtifact`, `wf:dirNote` 반영 |
| `mso-scaffold-design` / `mso-repository-setup` | artifact stream TTL 확인 뒤 index/sub_index/data_registry를 스캔·연결하는 책임 경계 정리. setup은 부트스트랩/후속 진입점, scaffold는 index 연결 규칙 소유 |
| `mso-graph-observability` | TTL 가시화와 개선 리포트 생성 책임으로 정리. workflow view, artifact-stream view, eval edge, runtime analysis를 읽기 전용 산출물로 생성 |
| TTL-only migration policy | workflow YAML은 migration input으로만 허용. sibling TTL이 있으면 제거 후보, 없으면 migration blocker로 보고하며 topology 입력은 항상 TTL ABox만 사용 |
| `mso-conversation-analytics` | de-routed 잔존 상태를 재확인. 전환행렬·funnel·reprompt율·많이 사용하는 workflow 후보 등 user/turn 패턴 분석은 UUG `uug-pattern-analytics` 흡수 대상 |
| `mso-intent-analytics` | MSO runtime tier-escalation 신호와 intent-level dispatch analytics의 귀속지로 명시 |
| 전체 버전 | README, install script, SKILL.md version field, manifest version을 v0.5.0으로 정렬 |

## v0.4.0 (2026-06-27) — Artifact stream observability

> **Task-only topology에서 artifact stream topology로 확장.** workflow sub-graph에서 `wf:directory`와 `wf:deliverables`를 Artifact node로 파생해 `artifact --upstream--> task --downstream--> artifact` supply chain을 볼 수 있게 했다. MSO는 Data Pipeline이 아니라 Repository Artifact Supply Chain을 관측한다. `data_type`은 접근 매체(local_file/api/mcp/database 등), `artifact_type`은 Knowledge Store/Event Store/Local Database/Document/Media 같은 소비·운영 의미를 표현한다.

### Changed

| 변경 | 내용 |
|------|------|
| `mso-graph-observability` | workflow별 subgraph에 Artifact node와 input/output edge 추가 |
| `observe_graph.py` | `wf:directory`를 `data_type=local_file` Artifact로 해석. 명시 `artifact_type`이 없으면 locator/detail/role/data_type으로 knowledge_store, event_store, local_database, document, media를 추론 |
| Deliverables | `wf:deliverables`는 detail 기반으로 Artifact Type 추론. `*.ttl`, `*.json`, `*.yaml` 등 구조화 산출물은 machine-native artifact로 분류 가능 |
| View separation | workflow별 `integrated`, `workflow`, `artifact-stream` view 생성. `workflow` view는 공유 Artifact id 기반 task spine으로 `((start)) --next--> task --next--> ((end))`를 표시 |
| Observability output cleanup | 중복 파일을 줄이기 위해 `resource-stream-*`, `data-stream-*` deprecated alias 출력을 제거하고 canonical `artifact-stream-*`만 생성 |
| Artifact stream report | `artifact-stream-report.md` 추가. produced-but-unconsumed artifact를 cross-workflow artifact, missing agent consumer, terminal/review document, terminal media deliverable 후보로 분류 |
| Consumer fit heuristic | Markdown/document Artifact에 Agent/User 소비자가 없으면 생략하거나 JSONL/TTL/SQLite 같은 machine-native Artifact로 구조화하도록 report와 문서에 기준 추가 |
| Directory boundary | 디렉토리는 workflow topology와 Artifact 소비 관계에서 파생되는 구현 경계로 보고, 소비자가 없는 Artifact boundary는 축소/병합 후보로 판단 |
| Workflow semantics | 같은 target Artifact id로 이어지는 stream은 하나의 workflow, 분기되거나 다르게 소비되는 stream은 별도 workflow boundary 후보로 해석 |
| Mermaid shape | task `["label"]`, document `@{ shape: doc }`, machine-native artifact cylinder, media stadium, decision `{{"label"}}`, oracle `[/"label"\]` 적용 |
| Phase containment | workflow별 subgraph에서 `hasNode` edge 대신 Mermaid `subgraph` 블록으로 phase membership 표현 |
| Node id labels | Mermaid label에 `id: <node-id>`를 표시해 사용자가 특정 workflow node를 지목할 수 있도록 개선 |
| Artifact registry location | Mermaid node label은 `DOCUMENT|MEDIA|KNOWLEDGE STORE|EVENT STORE|LOCAL DATABASE`와 `id`만 표시하고, `location=index:<artifact-id>`와 실제 접근자 `locator`는 `Artifact Node Index` 표로 분리 |
| `workflow-subgraph-index.md` | workflow별 Artifact node 개수 컬럼 추가 |
| 전체 버전 | README와 SKILL.md version field를 v0.4.0으로 정렬 |

## v0.4.0 (2026-06-27) — Decision/Oracle gate separation

> **Decision gate와 Oracle gate 분리.** workflow topology는 task/decision/oracle node와 process edge로 관측한다. 순환 자체는 금지하지 않고, 산출물 재귀 소비 loop 안에 별도 Oracle gate가 없을 때만 uncontrolled feedback loop로 판정한다.

### Added

| 변경 | 내용 |
|------|------|
| `oracle.schema.yaml` | `type: oracle`, `oracle_type ∈ {user, agent, metric}`, `criteria`, `target_artifact`, `on_fail`을 갖는 산출물 평가 gate 추가 |
| `wf_to_ttl.py` | `oracle` 노드를 `wf:Oracle`로 투영하고, ordered phase steps를 `wf:next`, branch goto를 `wf:gotoNode` process edge로 투영 |
| `mso-graph-observability` | repository topology에서는 내부 node flow를 숨기고, workflow별 subgraph에서 `next`와 `on:<condition>` edge를 표시 |

### Changed

| 변경 | 내용 |
|------|------|
| feedback loop validation | DAG/비순환 강제가 아니라 Oracle gate 없는 feedback loop를 오류로 판정 |
| `decision.schema.yaml` | `judge`에 `AGENT` 추가. decision은 process branch/진행 판단만 담당하고 산출물 품질평가는 `oracle`로 분리 |
| 전체 버전 | README와 SKILL.md version field를 v0.4.0로 정렬 |

## v0.4.0 (2026-06-27) — TTL-only workflow observability patch

> **YAML 생성 루프 제거 + workflow sub-graph 관측 추가.** workflow SSOT는 TTL ABox만 사용한다. YAML은 신규 작성/역생성 대상이 아니라 legacy migration input으로만 남긴다.

### Changed

| 변경 | 내용 |
|------|------|
| `mso-graph-observability` | repository 전체 `workflow-topology.md`와 workflow별 `workflow-subgraphs/<scope>.md`를 함께 생성. topology 입력은 TTL ABox만 사용 |
| `observe_graph.py` | `workflow-ssot-report.md`와 `--strict-ssot`로 legacy YAML 잔존을 drift로 감지. sibling `.abox.ttl`이 있으면 제거 후보, 없으면 migration blocker로 분리 |
| `wf_to_ttl.py` | YAML authoring compiler가 아니라 legacy migration backend로 문서화. workflow/module/project scope 기반 phase/node URI로 multi-workflow 충돌 방지 |
| `ttl_to_wf.py` | TTL→YAML 역생성 경로 제거. YAML을 되살리지 않도록 SSOT 경계 고정 |
| `mso-workflow-design` | YAML edit layer/양방향 무손실 표현 제거. 신규 workflow는 TTL ABox로 작성하고, legacy YAML은 `migrate_workflows_to_ttl.py`로만 흡수 |
| `mso-work-memory` | JSONL SSOT는 유지하고 `wm_to_ttl.py` projection + `work-memory-shapes.ttl` SHACL gate 추가. `references`는 `ExternalReference` 허용, lifecycle relation은 target class 검증 |

## v0.4.0 (2026-06-27) — Graph Observability + Codex hook adapter 정식화

> **MSO graph observability 내장 + v0.4.0 정식 버전 bump.** workflow TTL/ABox는 Mermaid view로, work-memory/auditlog/worklog/intent turn은 runtime analysis로 관측하는 `mso-graph-observability`를 추가했다. 동시에 Codex hook adapter의 Stop 잡음/중복 실행을 제거하고, §11 NLU 경계 재편을 정식 버전에 포함했다.

### Added

| 변경 | 내용 |
|------|------|
| `mso-graph-observability` | workflow topology/class/property Mermaid view + runtime JSONL analysis(`runtime-analysis.md`) 생성 |
| `observe_graph.py` | workflow TTL/TBox를 읽어 `agent-context/observability/graph/` 산출물 생성. work-memory/auditlog/worklog/intent JSONL에서 실패 hotspot, workflow/intent 사용 빈도, 반복 ID, parse error를 요약 |
| `requirements.txt` | graph observability와 기존 TTL tooling에 필요한 `rdflib>=7.0` 명시 |

### Changed

| 변경 | 내용 |
|------|------|
| 전체 버전 | README, install script, SKILL.md version field, manifest version을 v0.4.0으로 정렬 |
| `mso-orchestration` | graph 관측·분석 의도를 `mso-graph-observability`로 라우팅 |

## v0.4.0 Included — Codex hook adapter 안정화 (2026-06-26)

> **Codex Stop hook 잡음/중복 실행 제거.** `work-memory-check.sh` 의 Stop `hookSpecificOutput.additionalContext` 경로는 Codex에서 출력 잡음과 중복 hook 실행을 만들 수 있어 폐기했다. 기록 판단 넛지는 provider 간 컨텍스트 도달이 확인된 `SessionStart(compact|resume)` 에만 둔다. `Stop`은 worklog 파일 기록만 수행한다.

### Changed

| 변경 | 내용 |
|------|------|
| `hooks/work-memory-check.sh` | Stop/PreCompact/SessionEnd 에서 조용히 종료. SessionStart 또는 수동 실행에서만 plain stdout 출력. Codex root fallback(`CODEX_PROJECT_DIR`/`PROJECT_DIR`) 반영 |
| `mso-repository-setup/scripts/init.py` | Codex `config.toml` 생성 시 Stop에는 worklog만 등록하고, work-memory-check는 SessionStart(compact/resume)에만 등록. `.codex/hooks.json`은 중복 실행 방지를 위한 빈 compatibility 파일로 갱신 |
| `settings-hook-snippet.json` / docs | Stop additionalContext 설명 제거. 수동 스니펫도 Stop check hook을 제거해 자동 생성 경로와 일치 |

## v0.4.0 Included — §11 NLU 경계 재편 (2026-06-17)

> **utterance→intent = UUG / intent→action = MSO.** NLU 앞단(자연어→intent 분류)을 UUG(`01_user-utterance-grounding`)로 흡수하고, MSO 는 intent→action(뒷단 slot/dispatch)만 보유. 스킬 8→7.

### Changed
| 변경 | 내용 |
|------|------|
| `mso-intent-registry` → `mso-intent-analytics` | 개명. registry SoT 유지 + 뒷단 dispatch(`src/pipeline.py`) 흡수. role `data`→`data+runtime`. (analytics 본체·tier-escalation 흡수는 미구현 — §11.1) |
| `mso-utterance-grounding` | **해체.** 앞단(normalize/router/serve)은 UUG 흡수로 제거. 뒷단(slot_filler/resolver/validator/turn_writer/pipeline)은 `mso-intent-analytics/src/` 로 이전. `pipeline.ground(utterance, intent_id)` — intent_id 는 UUG 가 공급(디커플). |
| `mso-conversation-analytics` | **de-route.** orchestration 라우팅에서 제외(잔존). 분석 메서드는 UUG(`uug-pattern-analytics`) 흡수 대기 — 흡수 완료 후 제거. depends_on → `mso-intent-analytics`. |
| `mso-orchestration` | 운영 명령 라우팅 = UUG `ug ground`→intent_id→`mso-intent-analytics` dispatch. utterance-grounding 라우팅 제거, conversation-analytics de-route. |
| UUG `uug-grounding` | namespace-agnostic 멀티-레지스트리 lookup + `projects.yaml intent_registry` + 도메인 intent commit 정책(MSO decisiveness 동등, fixture 84%≥80%). |

> **비고**: v0.4.0에서 정식 버전 bump와 함께 포함.
>
> ⚠ **capability 회귀 (미해소)**: 구 `mso-utterance-grounding/slots/inference/serve.py` 는 **실제 Lv30 LLM(Claude Haiku) fallback + Lv20 모델 경로**를 가졌고, Lv10 keyword-miss(~20%)를 프로덕션에서 복구했다. 앞단 제거로 이 serve.py 가 삭제됐고 **UUG 의 Lv30 은 미빌드(후속)** → keyword-miss 발화의 LLM 복구 경로가 현재 **없음**. 비회귀 측정(UUG 84% ≥ MSO 80%)은 **양쪽 `GROUNDING_SKIP_LLM=1` Lv10-only** 수치라 이 Lv30 격차를 반영하지 않는다. serve.py 로직은 git history 에 보존 — UUG Lv30 으로 포팅 필요(미결).

## v0.3.6 (2026-06-19) — work-memory Decision Governance + workflow TTL-first

> **status: `repository-test/` 검증 완료 후 `repository/` 승격 완료.** 위 §11 Unreleased(NLU 경계 재편)와 **독립 트랙** — §11 은 v0.4.0 행, 본 건은 work-memory 한정 additive + workflow TTL-first 기준이라 v0.3.6 으로 선행.

> **work-memory 에 의사결정 거버넌스 레이어 추가 — alternatives-record(AR) + UD boundary 거버넌스.** Decision-Centric Governance Loop(GPT 논의 통합). 척추 원리 = **Deliberation is a View**: 코어는 이벤트(IN/AR/AD/UD)와 관계만 저장하고, 의사결정 케이스·drift 사건은 그래프 쿼리로 재구성하는 view 로 둔다. v0.3.4 schema-driven 덕에 **엔진 코드 무변경**(순수 additive). 동시에 workflow는 TTL ABox를 SSOT로 두고 legacy YAML은 마이그레이션/edit layer로 격하한다. 기원: NLU `00.raw-data` 운영 학습(PR-0003/PR-0004/AR-0001).

### Added

| 변경 | 내용 |
|------|------|
| `references/schema.yaml` — `alternatives-record`(AR) 타입 | 결정 전 단계에서 옵션 집합+득실 기록(`provided_by`/`options`/`recommended`). `AR ──followed-by──> UD`. 결정은 안 함 — agent/user 제안을 동일 형식에 담음 |
| `references/schema.yaml` — UD `boundary`/`criterion` metadata | UD 가 지배하는 정책/기준 식별자(boundary) + 기준 한 줄(criterion). 같은 boundary 의 UD 체인 `supersedes`/`refines` 링크 = **drift event(derived)** |
| `references/schema.yaml` — oracle ∈ {human, metric} 주석 | 결정 권위는 사람만이 아니라 metric/KPI 게이트도 포함(지표 기반 eval 대조 시) |
| `SKILL.md` — 거버넌스 컨벤션 섹션 | AD/AR 구분 규칙, DriftEvent=derived, DecisionCase=view→episode(EP), policy→stale 캐스케이드=프로젝트 영역 |
| `mso-workflow-design` — workflow TTL-first | `*.abox.ttl` 을 workflow SSOT로 두고 `migrate_workflows_to_ttl.py` 로 legacy YAML을 TTL 정본으로 변환 |
| `mso-workflow-optimizer` | workflow TTL ABox를 LangGraph generated artifact로 컴파일. provider routing은 TTL 밖 policy로 분리. Vertex별 work-memory ContextPack과 `memory_writeback_queue` 계약 추가. Claude Code/Codex=control plane, LangGraph=execution plane 경계와 `control_plane_events` 추가 |

### 결정 (planning `mso-v0.3.6-PLAN.md`)

- **A1**: AD 유지 + AR 병존 (AD=agent 권한 내 결정·실행 / AR=oracle 에 옵션 제시). AD 은퇴는 자율 에이전트 표현 불가 → MSO 본질과 충돌이라 기각.
- **B2**: policy→stale 캐스케이드(drift_scan/relabel_queue)는 산출물 모델 의존 → 코어는 신호(boundary+supersedes)까지만, *구현*은 레퍼런스 패턴.
- DecisionCase 는 신규 타입 추가 없이 기존 `episode`(EP)로 흡수(live=view, closed=EP).

### 비고

schema version 1.0.0 → 1.1.0 (additive). 기존 AD 마이그레이션 없음(이력 보존). GPT governance 노드(DriftEvent/PolicyUpdateCase 등)의 1급 노드화는 미채택 — v0.4.0 사안(PLAN §8).

## v0.3.4 (2026-06-13)

> **work-memory 엔진 타입 어휘를 schema-driven 화 — 같은 엔진을 다른 스코프로 재사용 가능.** `wm_node.py` 가 타입 prefix/dir(과 relation 어휘)을 하드코딩 대신 `WORKMEM_DIR/schema.yaml` 의 `types:`/`relation_types:` 에서 읽는다. **하위호환**: `types:` 섹션이 없으면 기존 work-memory 7타입 기본값으로 fallback(기존 프로젝트 무영향). 이로써 동일 엔진(jsonl+zvec+graph)을 user-memory(UC/UP/UF) 같은 다른 스코프로 재사용 — `user-utterance-grounding` user-memory 레이어의 토대. 스킬 수 8개 유지.

### Changed

| 변경 | 내용 |
|------|------|
| `scripts/wm_node.py` | `TYPE_PREFIX`/`TYPE_DIR`/`ALLOWED_RELATIONS` 하드코딩 → `_load_vocab()` 으로 `schema.yaml` 로딩(없으면 기본값 fallback). `REQUIRED_FIELDS` 는 스코프 불변이라 하드코딩 유지 |
| `references/schema.yaml` | 머신리더블 `types:` 섹션 추가(SSOT — wm_node 가 prefix/dir 을 여기서 읽음). 기존 `id_patterns:` 는 사람용 미러로 잔존 |

### 검증

격리 테스트: 신 template(types: 포함) + 옛 schema(types: 없음 → fallback) 양쪽 기존 7타입 동작 동일; user 티어(UC/UP/UF) 스키마로 new/validate/graph full cycle 통과. 기존 work-memory 동작 무변경.

## v0.3.3 (2026-06-13)

> **IN/TS 비대칭 누락 보완 + 넛지 전달 메커니즘 수정.** UD는 사용자 발화라는 외부 트리거로 잘 기록되지만 issue-note(IN)/trouble-shooting(TS)는 에이전트 내부 작업에서만 촉발돼 누락되기 쉬웠다. (a) 판단 기준(상시 로드 레버)에 "IN/TS 회고 기록 정상" + 트리거 앵커(테스트 green·fix 검증·`fix:`/`revert:` 커밋·접근 전환)를 명시하고, (b) fix 커밋 탐지(1b)·세션 회고(4) 넛지를 더했다. **핵심: 기존 넛지는 Stop/PreCompact 의 plain stdout 으로 떠서 모델에 도달하지 않았다(공식 문서상 plain stdout 주입은 SessionStart·UserPromptSubmit 한정).** 전달을 이벤트별로 교정 — Stop 은 `hookSpecificOutput.additionalContext` JSON, 넓은 회고는 SessionStart(compact/resume)의 plain stdout. ⚠️ additionalContext-on-Stop 의 실제 주입 여부는 **문서 근거이며 실측 1회 확인 필요**(안 닿으면 UserPromptSubmit 으로 대체). 스킬 수 8개 유지.

### Changed

| 변경 | 내용 |
|------|------|
| `assets/work-memory-judgment.md` | IN 기준 "문제 발견 즉시(해결 전)" → "발견했거나 해결한 직후 — 같은 턴에 고쳤다면 IN+TS 회고 공동 기록". 트리거 이벤트(red→green·fix 검증·`fix:`/`revert:` 커밋·접근 전환) 명시. "이미 고쳤으니 늦었다"는 누락 사유 아님 + TS 단독 기록 금지 명문화 |
| `SKILL.md` 원리 6 / 넛지 섹션 | IN/TS 회고 기록 정상·트리거 앵커·TS 단독 금지를 always-on 책임에 반영. 넛지 섹션에 전달 의미론(이벤트별 주입 방식) + (1b)·(4) 넛지 문서화. 훅=백스톱, always-on 텍스트=주 레버 명시 |
| `hooks/work-memory-check.sh` | **넛지 전달 메커니즘 교정** — Stop 은 `hookSpecificOutput.additionalContext` JSON(비차단, 다음 턴 주입; `stop_hook_active` 루프 가드), SessionStart 는 plain stdout. stdin 파싱을 python3 로(BSD/GNU sed `\|` 차이 비의존). **(1b) IN/TS 넛지** — fix/revert 커밋(WM 최신 기록 이후) 있는데 IN/TS 대기 없으면 IN+TS 권유, track 넛지(WORTHY_PATHS)와 독립. **(4) 세션 회고 넛지** — 미커밋 소스 변경(WM 밖) 남아 IN/TS 대기 없으면 점검 권유, SessionStart 전용. 비차단(exit 0) |
| `mso-repository-setup` init.py / settings-hook-snippet.json | work-memory-check 등록을 **출력이 모델에 도달하는 이벤트로 한정** — Stop + SessionStart(compact·resume). PreCompact·SessionEnd 등록 제거(plain stdout 미도달). worklog 는 Stop·PreCompact 유지 |

## v0.3.2 (2026-06-10)

> **기록 판단 넛지 레이어 추가 — 무엇을 했는지(자동 로깅)와 무엇을 기록할지(판단)를 분리.** `auditlog`/`worklog` 자동 로깅 위에, track/insight entry 를 *언제* 남길지 상기시키는 비차단 hook(`work-memory-check.sh`)을 더했다. `mso-repository-setup --hook` 은 hook 을 프로젝트 `.claude/scripts/` 로 copy-form 등록해 절대경로 의존 없이 CI·타 머신 이식성을 확보한다. 스킬 수는 8개 유지.

### Added

| 추가 | 내용 |
|------|------|
| `mso-work-memory` 넛지 hook | `hooks/work-memory-check.sh` — Stop/PreCompact 에서 비차단 넛지. (1) track 넛지: 결정 가치 있는 변경(`WM_WORTHY_PATHS`)이 최신 기록보다 앞서면 UD/AD/IN/TS 권유. (2) insight 넛지: 종결된 TS 이후 EP 회고가 없으면 episode 회고 권유 |
| `assets/work-memory-judgment.md` | 어떤 상황에 어떤 entry 를 남기는지 판단 *기준* 텍스트. 프로젝트 rules(CLAUDE.md/AGENTS.md)에 드롭인해 상시 로드 |

### Changed

| 변경 | 내용 |
|------|------|
| `mso-repository-setup --hook` | copy-form 으로 전환 — hook 스크립트를 `.claude/scripts/` 로 복사하고 settings.json 은 `$CLAUDE_PROJECT_DIR` 상대로만 참조(절대·스킬 경로를 커밋 파일에 박지 않음 → CI·타 머신 이식성). `--worthy-paths` 로 `WM_WORTHY_PATHS` 주입 지원 |
| `init.py` / SKILL.md / `settings-hook-snippet.json` | 3-hook(auditlog·worklog·work-memory-check) 체제 + copy-form 반영. 문서-구현 불일치 해소 |

## v0.3.1 (2026-06-04)

> **Utterance Grounding Layer 추가 — 자연어 운영 명령 레이어.** v0.3.0의 5개 스킬(Design/Ops/Infra) 위에, 오퍼레이터 자연어 발화를 실행 가능한 `GroundedCommand`로 변환하는 Runtime/NLU 레이어 3개 스킬을 더해 8개 스킬 체제로 확장했다. `mso-orchestration`은 자연어 운영 명령을 첫 라우팅 분기로 흡수한다.

### Added

| 추가 | 내용 |
|------|------|
| `mso-utterance-grounding` | 자연어 발화 → `GroundedCommand` 변환 Smart Tool. 4-slot pipeline(input_norm→rules→inference→script). Lv10 keyword 라우터 + Lv30 LLM fallback, analytics 누적 후 Lv20 경량 모델로 escalation-down |
| `mso-intent-analytics` | MSO 도메인 NLU 어휘 단일 정본. LinkML schema(`nlu_intent.yaml`) · TTL instances · SKOS taxonomy · intent matrix 소유. `lookup.py` lookup API(list_intents/lookup_intent/lookup_target) 제공 |
| `mso-conversation-analytics` | `turns.jsonl`을 DuckDB in-memory로 분석. 전환 행렬·퍼널·reprompt율·미해결 발화 측정 + Closed-loop 환류 보고서 + Tier Escalation 신호 생성 (`duckdb` 선택 의존성) |

### Changed

| 변경 | 내용 |
|------|------|
| 스킬 수 5 → 8 | Runtime/NLU 레이어 3개 스킬 추가 (Design/Ops/Infra 5개는 유지) |
| `mso-orchestration` 라우팅 | 자연어 운영 명령을 첫 분기(0번)로 흡수 → `mso-utterance-grounding` 디스패치 |
| `workflow_to_markdown.py` | 하드코딩된 discovery/development/testing phase 순서를 `_collect_phases_aggr`로 일반화. mermaid cross-phase goto 해석 · decision 끝 자동 edge 생략 · 중복 edge 제거 |

## v0.3.0 (2026-05-26)

> **스킬팩 전면 재설계 — Working System First.** v0.2.x의 복잡한 13개 스킬을 5개로 재편했다. `mso-repository-setup`, `mso-scaffold-design`, `mso-workflow-design`, `mso-work-memory`, `mso-orchestration`이 실제로 동작하는 단일 스킬팩을 구성한다. Python 스크립트 기반 CLI(`init.py`, `sf_node.py`, `wf_node.py`, `wm_node.py`)와 hook 자동 등록(`auditlog.py`, `worklog.py`)으로 provider-free 운영이 가능해졌다.

### Added

| 추가 | 내용 |
|------|------|
| `mso-repository-setup` | `agent-context/` 트리 부트스트랩 CLI(`init.py`). `--hook` 옵션으로 `.claude/settings.json` 자동 등록 |
| `mso-scaffold-design` | `index.yaml` SSOT. `sf_node.py` — show/scaffold/validate/inventory/tree 명령. sub_index 계층 참조 지원 |
| `mso-workflow-design` | workflow YAML SSOT. `wf_node.py` — show/scaffold/validate/harness-manifest. `workflow_to_markdown.py`, `workflow_to_mermaid.py` 변환 스크립트 |
| `mso-work-memory` | JSONL entry CLI(`wm_node.py`). 9종 타입, zvec 시맨틱 검색, relations 그래프 traversal |
| `hooks/auditlog.py` | PostToolUse hook — Bash·Edit·Write 호출을 `auditlog/AU-YYYY-MM-DD.jsonl`에 일별 append |
| `hooks/worklog.py` | Stop hook — 세션 종료를 `worklog/WL-YYYY-MM-DD.jsonl`에 일별 append |
| `install.sh` | 5개 스킬을 `~/.{claude,codex,gemini}/skills/`에 symlink 등록 |

### Changed

| 변경 | 내용 |
|------|------|
| 스킬 수 13 → 5 | v0.2.x 스킬 전체 폐기. 5개 스킬로 완전 재편 |
| `.skill-modules/` 구조 폐기 | 모든 스킬이 직접 `skills/` 하위에 위치. on-demand 로딩 없음 |
| `mso-orchestration` 역할 축소 | 실행자 → name-only 라우터. 실제 동작은 각 sub-skill |
| `agent-context/` 표준 구조 도입 | `index/`, `workflow/`, `work-memory/` 3개 축으로 정리 |
| Python 의존성 | `PyYAML>=6.0`, `jsonschema>=4.24.0` (stdlib 외 최소화) |

### Fixed

| 수정 | 내용 |
|------|------|
| `sf_node.py inventory` EXTRA 오탐 | `agent-context/` 디렉토리가 항상 unregistered로 감지되던 문제 수정 |
| `wm_node.py` DeprecationWarning | `datetime.utcnow()` → `datetime.now(timezone.utc)` 교체 |

---

## v0.2.3 (2026-05-13)

> **mso-task-execution → mso-harness-setup 흡수 + 리포지토리 구조 정리.** 실행 조율(execution_graph 소비, Fallback Policy, node snapshot)을 `mso-harness-setup`에 통합하여 스킬 수를 11 → 10개로 줄였다. 더불어 폐기된 훅, 중복 스크립트, 고아 마이그레이션 파일 등 15건을 정리했다.

### Changed

| 변경 | 내용 |
|------|------|
| **mso-task-execution 흡수** | 실행 조율·Fallback Policy Registry·wrapper module 명세를 `mso-harness-setup` Phase 6–7로 통합. `mso-task-execution` 스킬 삭제 |
| **mso-harness-setup 역할 확장** | 기존 Harness Design(Phase 1–5)에 Execution Orchestration(Phase 6–7) 추가. `build_plan.py`, `execution_plan.schema.json`, execution 관련 모듈 5개 이전 |
| **docs 전면 반영** | usage_matrix, getting-started, pipelines, README, architecture에서 `mso-task-execution` 참조를 `mso-harness-setup`으로 교체 |

### Removed

| 항목 | 이유 |
|------|------|
| `mso-task-execution` 스킬 | `mso-harness-setup`에 흡수 |
| `skills/mso-agent-audit-log/hooks/` (Python/sh 스크립트) | `skills/`에 정본 존재. `skills/`는 참조 문서 레이어 |
| `skills/mso-agent-audit-log/hooks/stop_hook.sh` | Stop hook 폐기 (v0.2.2에서 3-hook 체계로 대체) |
| `skills/mso-agent-audit-log/schema/migrate_*.sql` (3개) | 마이그레이션 완료. 스냅샷은 `history/`에서 관리 |
| `docs/diagrams/` | 빈 디렉토리 |
| `docs/knowledge-object-mapping.md` | v0.1.1 시대 산출물 |
| `skills/mso-workflow-optimizer/.env.local` | `.env.example` 중복 |

---

## v0.2.2 (2026-05-12 ~ 2026-05-13)

> **Runtime Harness Toolkit planning 추가 + audit-log 인프라 재설계.** provider runtime 위에 올라가는 semantic runtime governance layer를 `mso-harness-setup` 스킬로 정의했다. 동시에 `mso-agent-audit-log`를 감사 인프라의 단일 소유자로 재정의하고, 세션 훅을 스크립트 기반으로 전환하여 토큰 소비를 0으로 줄였다.

### Added — mso-harness-setup

| 추가 | 내용 |
|------|------|
| **신규 스킬** | `repository/skills/mso-harness-setup/` 추가 |
| **Workflow Repository Setup 스킬** | `repository/skills/mso-workflow-repository-setup/` 추가. workflow-design + scaffolding-design을 repository setup 계약으로 승격 |
| **Canonical Event Schema** | provider/native/capability/execution/semantic/governance/audit block을 분리한 `canonical_event.schema.json` 추가 |
| **YAML Runtime Spec** | adapter, policy, evaluator, escalation, checkpointing, audit 설정을 담는 `runtime_harness_config.schema.json` 및 예시 YAML 추가 |
| **Provider Adapter 명세** | Claude Code, Codex, OpenClaw, Hermes, LangGraph, OpenAI Agents SDK, Google ADK, MCP-based systems의 native event를 canonical lifecycle로 매핑하는 adapter contract 초안 |
| **Policy/Evaluator 명세** | capability/risk/lifecycle 기반 policy engine, semantic entropy/topology stability/loop risk evaluator 설계 |

### Changed — mso-orchestration 라우팅 확장

| 변경 | 내용 |
|------|------|
| **[F] Runtime Harness 설계 파이프라인 추가** | 트리거: "harness-setup", "runtime harness", "canonical event", "provider adapter", "event ontology", "semantic runtime" |
| **[F-0] Workflow Repository Setup 파이프라인 추가** | `workflow_repository.yaml`, `scaffolding_contract.md`, `memory_layer.md`, `harness_setup_input.yaml` 산출 |
| **mso-execution-design alias 제거** | deprecated symlink를 제거하고 `mso-task-execution` 본체만 유지 |
| **pack_config version 갱신** | `v0.2.2`, required skill에 `mso-harness-setup`, `mso-workflow-repository-setup` 추가 |

### 하위 호환 — Harness

- 기존 [A]~[E] 파이프라인 동작 변경 없음.
- `mso-harness-setup`은 planning/spec 스킬이며 runtime 실행 경로에 자동 삽입되지 않는다.
- provider-native payload는 canonical event 내부에서 별도 block으로 격리하는 방향만 정의했다.
- `mso-execution-design` 이름은 더 이상 required skill이 아니다. 실행 본체는 `mso-task-execution`이다.

---

### Added — mso-agent-audit-log 세션 훅 재설계 (2026-05-13)

| 추가 | 내용 |
|------|------|
| **`setup.py`** | DB 생성 + worklog 디렉터리 생성 + 세션 훅 주입을 한 번에 처리. `--target claude\|codex\|all`, `--dry-run` 지원 |
| **`session_start_hook.py`** | 최근 worklog 3개의 마지막 `##` 블록을 요약해 SessionStart 시 컨텍스트로 주입. Claude Code / Codex 런타임 자동 감지 |
| **`pre_compact_hook.py`** | transcript JSONL 파싱 → Write/Edit 파일 목록 + 마지막 assistant 메시지를 worklog에 직접 기록. Claude 호출 없음 |
| **`session_end_hook.py`** | `pre_compact_hook.py`와 동일 로직, `SessionEnd` 레이블로 기록 |
| **Codex 지원** | `.codex/hooks.json`에 `SessionStart`만 등록. `session_start_hook.py`가 stdin의 `model` 필드로 런타임 감지 → `{"systemMessage": "..."}` 출력 |
| **`inject_hooks.py` 리팩터** | `inject_claude` / `inject_codex` / `inject(unified)` 세 함수로 분리. `--target` 플래그로 대상 선택 |

### Changed — mso-agent-audit-log 역할 재정의

| 변경 | 내용 |
|------|------|
| **단일 소유자(SoT)** | DB 생성, 세션 훅 설정, 실행 로그 기록 세 책임을 통합. 다른 스킬은 읽기 전용 |
| **훅 이벤트 변경** | `Stop` hook 폐기 → `SessionStart · PreCompact · SessionEnd` 3-hook 체계로 전환 |
| **토큰 소비 0** | 기존: `additionalContext`를 통해 Claude가 worklog 작성(토큰 소비). 변경: 스크립트가 transcript를 직접 파싱해 worklog 기록 |
| **`mso-workflow-repository-setup` 연동** | Phase 4 거버넌스 훅 목록을 `SessionStart · PreCompact · SessionEnd`로 갱신. `setup.py` 호출로 일괄 초기화 |

### Deprecated

| 항목 | 내용 |
|------|------|
| **`Stop` hook** | `SessionEnd`로 대체. `Stop`은 더 이상 등록하지 않는다 |
| **`additionalContext` 방식 worklog 기록** | 스크립트 직접 파싱 방식으로 전환. Claude 호출 불필요 |

### 하위 호환 — 세션 훅

- 기존에 `Stop` hook이 등록된 프로젝트는 수동 제거 후 `setup.py --project-root <path> --target claude`로 재설정한다.
- `session_start_hook.py`는 `WORKLOG_DIR` 미설정 또는 worklog 파일 없으면 `exit(0)`으로 조용히 종료한다.
- Codex는 `PreCompact`/`SessionEnd`를 지원하지 않으므로 `SessionStart`만 등록한다.

---

## v0.2.1 (2026-05-08)

> **ai-collaborator 완전 흡수.** 별도 스킬로 운영되던 ai-collaborator(Codex·Claude·Gemini 멀티 프로바이더 CLI)를 `mso-agent-collaboration`으로 통합. 외부 의존성 제거, 라우팅 테이블에 [E] 파이프라인 추가.

### Changed — mso-agent-collaboration 기능 확장

| 변경 | 내용 |
|------|------|
| **ai_collaborator 패키지 이전** | `executor.py`·`swarm.py`·`bus.py`·`cli.py`·`providers.py`·`schemas.py`·`utils.py` 전체를 `scripts/ai_collaborator/`로 이전 |
| **collaborate.py 통합** | 멀티 프로바이더 CLI 진입점을 `scripts/collaborate.py`로 통합 |
| **보조 스크립트 이전** | `discover_models.py`·`normalize_results.py`·`embed_prd_to_tasks.py` → `scripts/` |
| **config/providers.yaml 이전** | Codex·Claude·Gemini 프로바이더 기본 설정을 `config/providers.yaml`로 이전 |
| **dispatch.py swarm 실행 구현** | `execute_dispatch`의 `swarm` 모드에서 티켓 `swarm_db`+`swarm_agents` 필드가 있을 때 `ai_collaborator.swarm.start_swarm_session` 직접 호출 |
| **SKILL.md 멀티 프로바이더 섹션 추가** | `collaborate.py` 빠른 시작, swarm 티켓 필드, 보조 유틸리티 명세 |

### Changed — mso-orchestration 라우팅 확장

| 변경 | 내용 |
|------|------|
| **[E] 멀티 프로바이더 실행 파이프라인 추가** | 트리거: "second opinion", "멀티 프로바이더", "여러 모델 비교", "collaborate" 등 |
| **description 트리거 키워드 추가** | "멀티 프로바이더", "second opinion", "provider 비교", "ai-collaborator" 등 |

### Deprecated

| 항목 | 내용 |
|------|------|
| **ai-collaborator 스킬 (v0.0.2)** | SKILL.md에 deprecated 표시. 동일 기능을 `mso-agent-collaboration`에서 사용 |

### 하위 호환

- `dispatch.py` `run`/`batch` 모드 동작 변경 없음. swarm 모드만 확장 실행 추가.
- `config/providers.yaml` 미수정 시 기본 프로바이더(codex/claude/gemini) 그대로 동작.

---

## v0.2.0 (2026-04-28)

> 스킬 13개 → 10개 통합 재편. 얇게 많이 → 굵게 적게. 프로세스 규약과 티켓 관리를 실제 소유자 스킬로 흡수하고, 전체 cross-reference 정합을 완료했다.

### Changed — 스킬 구조 재편

| 변경 | 내용 |
|------|------|
| **mso-vertex-design + mso-mental-model-design → `mso-mental-model`** | Directive Registry + Local Chart + mental_model_bundle 생성 + GT Angle Policy를 단일 진입점으로 통합 |
| **mso-process-template 배포** | Fallback Policy Registry → `mso-task-execution` 인라인. Hand-off 템플릿 6종(PRD/SPEC/ADR/HITL/Retrospective/Design Handoff) → `mso-agent-collaboration/templates/` |
| **mso-task-context-management → `mso-agent-collaboration` 흡수** | 티켓 lifecycle 스크립트 5개 + 모듈 3개(node-bootstrap/ticket-lifecycle/validation-archive) 통합. 티켓 생성·상태 전이·dispatch 단일 진입점 |

### Fixed — Cross-reference 정합

- `CLAUDE.md` MSO 정책 참조 경로 갱신 (`mso-process-template` → `mso-task-execution`/`mso-agent-collaboration`)
- `mso-skill-governance` registry-scan 필수 스킬 목록 10개 반영, `governance_baseline.json` v0.0.5 갱신
- `mso-mental-model/core.md` 제목·경로 참조 정합
- `mso-task-execution` 입력 출처 `mso-vertex-design` → `mso-mental-model` 갱신

---

## v0.1.3 (2026-04-01)

### 핵심 변경: 스킬 구조 전면 개편 + Agent Lightning 통합 (spec)

v0.1.x 시리즈 최대 규모의 구조 변경. 스킬 명칭 개편, 실행 책임 레이어 재설계, Agent Lightning 기능(OTel/Guardrails/NHI/APO) spec 수준 통합.

#### Part A: 스킬 명칭 개편

| 변경 | 내용 |
|------|------|
| **mso-mental-model-design → mso-vertex-design** | 디렉티브(Vertex) 설계 역할을 더 정확히 반영하는 명칭으로 변경. deprecated symlink(`mso-mental-model-design` → `mso-vertex-design`) v0.1.4에서 제거 예정 |
| **mso-execution-design → mso-task-execution** | 오케스트레이션 실행 역할 명칭 명확화. deprecated symlink(`mso-execution-design` → `mso-task-execution`) v0.1.4에서 제거 예정 |
| **global_links symlink 신규** | `00_agents_global_links/skills/mso-vertex-design`, `00_agents_global_links/skills/mso-task-execution` 추가 (repository 외부). `~/.claude/skills/`가 이 경로를 경유하여 글로벌 접근 |

#### Part B: 실행 책임 레이어 재설계

| 변경 | 내용 |
|------|------|
| **2레이어 분리** | mso-task-execution을 **Orchestration Core**(스킬 본체)와 **Runtime Wrapper Modules**(`_shared/` 하위)로 분리. 역할 과부하 해소 |
| **폴백 정책 SoT 이전** | 에러 유형·severity·max_retry 정책 정의가 mso-task-execution → **mso-process-template 소유**로 이전. task-execution은 참조·트리거만 담당 |
| **Runtime Role Registry 신설** | mso-process-template에 에이전트 역할 매핑 테이블 추가 (Provisioning/Execution/Handoff/Branching/Critic·Judge/Sentinel) |
| **Fallback Policy Registry 신설** | mso-process-template에 에러 유형별 severity·action·max_retry 테이블 추가 |
| **execution_graph.json 신설** | mso-workflow-topology-design Phase A6 산출물. `graph_id`, `schema_version("1.0")`, `nodes[]` 필수. CC-01 계약에 추가 |

#### Part C: Agent Lightning 통합 [spec-only]

| 변경 | 내용 |
|------|------|
| **wrapper.otel** | LLM 호출 전후 OTel Span 생성·종료. 로컬 OTLP stdout 출력 (opt-in: Phoenix). `trace_id` Core에 반환 후 node_snapshots optional 저장 |
| **wrapper.guardrails** | pre-snapshot JSON Schema 검증 + PII 스캔. 실패 시 auto-reprompt. v0.1.4+에서 외부 SDK 교체 검토 |
| **NHI Attestation** | mso-skill-governance Phase 5 추가. `nhi_policy.json` 정의, 위반 시 mso-task-execution으로 에스컬레이션 신호 전송. fail-open 정책 |
| **APO 피드** | mso-workflow-optimizer Phase 6 추가. Macro-loop(Run 단위) vs Micro-loop(프롬프트 단위) 경계 정의 |
| **trace_id 컬럼** | node_snapshots 테이블에 `trace_id TEXT` optional 컬럼 추가. DB schema v1.5.0 → **v1.6.0** |

### 수정 파일

**수정**

| 파일 | 변경 |
|------|------|
| `skills/mso-vertex-design/SKILL.md` | 명칭 변경 반영. 자기 참조 및 Pack 내 관계 업데이트 |
| `skills/mso-task-execution/SKILL.md` | 전면 재작성. 2레이어 구조(Orchestration Core + Wrapper Modules), 폴백 정책 참조형 에러 라우팅, 4단계 실행 프로세스 |
| `skills/mso-workflow-topology-design/SKILL.md` | Phase A6 추가 (execution_graph.json 산출). Pack 관계 명칭 업데이트. scoring_weights 자동 정규화 통일 |
| `skills/mso-agent-audit-log/SKILL.md` | schema_version 1.5.0 → 1.6.0. node_snapshots에 trace_id 컬럼 추가. Pack 관계 명칭 업데이트 |
| `skills/mso-skill-governance/SKILL.md` | Phase 5 NHI Attestation [spec-only] 추가. nhi_policy.json 구조 정의 |
| `skills/mso-workflow-optimizer/SKILL.md` | Phase 6 APO 피드 [spec-only] 추가. Macro-loop / Micro-loop 경계 정의 |
| `skills/mso-process-template/SKILL.md` | Runtime Role Registry + Fallback Policy Registry 추가. Pack 내 관계 신설 |
| `skills/mso-observability/SKILL.md` | Pack 내 관계 명칭 업데이트 (mso-vertex-design) |
| `README.md` | v0.1.3 반영. 스킬 아키텍처 테이블·다이어그램 업데이트 |
| `docs/changelog.md` | v0.1.3 변경 이력 추가 |

**신규**

| 파일 | 설명 |
|------|------|
| `skills/mso-vertex-design/` | mso-mental-model-design 디렉토리 명칭 변경 (신규 디렉토리로 이전) |
| `skills/mso-task-execution/` | mso-execution-design 디렉토리 명칭 변경 (신규 디렉토리로 이전) |
| `skills/mso-mental-model-design` | deprecated symlink → `mso-vertex-design` |
| `skills/mso-execution-design` | deprecated symlink → `mso-task-execution` |
| `00_agents_global_links/skills/mso-vertex-design` | 글로벌 링크 신규 (repository 외부 경로) |
| `00_agents_global_links/skills/mso-task-execution` | 글로벌 링크 신규 (repository 외부 경로) |

### 하위 호환

- **스킬 명칭**: deprecated symlink로 기존 참조 유지. **v0.1.4에서 symlink 제거** 예정.
- **execution_graph.json**: CC-01 추가 입력. 미제공 시 mso-task-execution이 경고 후 실행 계속.
- **trace_id**: node_snapshots nullable 컬럼. 기존 INSERT 쿼리 영향 없음.
- **`[spec-only]` 기능**: SKILL.md 규약 정의 완료, 스크립트 구현은 v0.1.4에서 진행.

---

## v0.1.2 (2026-03-31)

### 핵심 변경: Harness Convention v0.1.2 — 에이전트 런타임 협업 규약 전면 통합

에이전트 간 협업 규약을 표준화하고 4개 핵심 스킬에 통합. Execution Model 3종, compression_event 감지 체계, audit_ref 포인터 패턴, optimizer 제안 포맷 정의.

| 변경 | 내용 |
|------|------|
| **Execution Model** | `single_instance` / `bus` / `direct_spawn` 3종 표준 정의. 모든 topology 노드에 `execution_model` 필수, `optimizer_hint` null 초기화 MUST. |
| **initial_context 포맷** | 에이전트 소환 시 표준 포맷 확정. `run_id`, `phase`, `role`, `objective`, `policy`, `state_summary`, `handoff_from` 구조. 전체 히스토리 포함 금지(MUST NOT). |
| **handoff_context 포맷** | 에이전트 완료 시 표준 포맷 확정. `agent_id`, `phase_completed`, `status`, `output`, `state_updates`, `next_phase_suggestion` 구조. |
| **소환 트리거 5종** | `phase_enter`, `eval_point`, `drift_detected`, `guard_escalate`, `fan_out`. |
| **compression_event 스키마** | 압축 감지 이벤트 스키마 정의. 감지 시 실행 중단 금지(MUST NOT). `message_count`만으로도 기록 충분. |
| **audit_ref 포인터 패턴** | `{run_id}#{step}` 포인터만 에이전트 context에 유지. 원문은 `audit_global.db`에만 보관. |
| **optimization_proposal 포맷** | optimizer 제안 YAML 포맷 확정. `requires_human_approval: true` 항상(MUST). 자동 topology 변경 금지(MUST NOT). |
| **compression_events / guard_events 쿼리** | optimizer의 Phase 1 필수 조회 SQL 규약 추가. |
| **버그 수정** | `bind_directives.py` line 211: `registry_path`를 list가 아닌 `", ".join(...)` 문자열로 저장 (jsonschema `string` 타입 준수). |

### 수정 파일

**수정**

| 파일 | 변경 |
|------|------|
| `skills/mso-workflow-topology-design/core.md` | Execution Model 섹션 추가 (3종 정의 + 노드 YAML 포맷) |
| `skills/mso-workflow-topology-design/modules/module.node_design.md` | Output Pattern에 `execution_model`, `optimizer_hint` 필드 추가 |
| `skills/mso-agent-collaboration/core.md` | initial_context / handoff_context 포맷, 5개 소환 트리거, dispatch_mode:swarm=bus 규약 추가 |
| `skills/mso-workflow-optimizer/core.md` | compression_events / guard_events SQL 쿼리, optimization_proposal 포맷, `requires_human_approval: true` 규약 추가 |
| `skills/mso-agent-audit-log/core.md` | Harness Convention v0.1.2 섹션 추가 (compression_event 수용, audit_ref 포인터, 4개 기본 테이블) |
| `skills/mso-agent-audit-log/modules/module.schema-contract.md` | 4개 기본 테이블 정의, compression_event YAML 스키마, audit_ref 포인터 패턴 추가 |
| `skills/mso-vertex-design/scripts/bind_directives.py` | `registry_path` 저장 방식 list → 문자열 변환 버그 수정 (v0.1.3에서 mso-mental-model-design → mso-vertex-design 명칭 변경) |
| `docs/architecture.md` | Execution Model 섹션 추가 |
| `docs/changelog.md` | v0.1.2 변경 이력 추가 |
| `README.md` | v0.1.2 반영 |

### 하위 호환

- **Execution Model**: 기존 노드 YAML에 `execution_model` 미포함 시 기본값 `single_instance`로 해석. 기존 topology 파일 변경 불필요.
- **compression_event**: 신규 테이블. 기존 audit 흐름에 영향 없음.
- **optimization_proposal**: 신규 출력 포맷. 기존 레벨 리포트와 병행 출력 가능.
- **bind_directives.py**: 버그 수정. 기존에 list로 저장하던 `registry_path`를 문자열로 변환 — jsonschema 검증 통과.

---

## v0.1.1 (2026-03-28)

### 핵심 변경: Infrastructure Completion + Explicit Knowledge Foundation

v0.0.10 Phase 3 미착수 항목(Tool Registry, Observability 연동, Tool Lifecycle)을 완성하면서, v0.2.0(Explicit Knowledge Architecture)의 기초 개념을 프로토타입 수준으로 도입하는 브릿지 릴리스.

#### Part A: Infrastructure Completion

| 변경 | 내용 |
|------|------|
| **Tool Registry** | `tool_registry.json` 스키마 정의. Knowledge Object 구조(decisional/operational/relational) 포함. 첫 번째 명시지 객체. |
| **module.tool-lifecycle** | mso-skill-governance에 Tool Lifecycle 관리 모듈 추가. Local→Symlinked→Global 승격 판정 기준, 절차, 강등 정책 공식화. |
| **module.model-monitoring** | mso-observability에 모델 모니터링 모듈 추가. rolling_f1/latency_p95/error_rate 수집 + 신호 발생 규칙. |
| **CC-15 신설** | mso-observability → mso-skill-governance 승격 제안 계약. `promotion_suggestion` event로 tool-lifecycle 모듈 트리거. |
| **collect_observations.py 확장** | `detect_model_performance` + `detect_promotion_candidates` 함수 추가. 모델 모니터링 + 승격 후보 탐지 로직. |
| **observability_callback.schema.json 확장** | event_type에 `model_monitoring`, `promotion_suggestion` 추가. |
| **Symlink 규약 공식화** | `references/symlink-convention.md` — 경로 패턴, 생성 절차, 쓰기 권한, 충돌 방지 규칙. |

#### Part B: Explicit Knowledge Foundation

| 변경 | 내용 |
|------|------|
| **Knowledge Object Schema** | `knowledge_object.schema.json` — 결정형/실행형/연결형 3유형 분류 체계 + `ko_meta` 공통 메타데이터. |
| **Workspace Convention** | `mso-convention.default.yaml` + `mso-convention.schema.json` — 명시지(`mso-outputs/`)와 암묵지(`.mso-context/`)의 파일시스템 수준 분리. 프로젝트별 커스터마이징 가능. |
| **module.workspace-convention** | mso-skill-governance에 convention 로딩/검증/투영 모듈 추가. 3단계 우선순위(프로젝트 > 사용자 글로벌 > MSO 기본). |
| **Gate Output Schema** | `gate_output.schema.json` — situation/evidence/options 3블록. Gate as Knowledge Projector (v0.2.0)의 첫 번째 구체적 스키마. |
| **Semantic Handoff: self_assessment** | `handoff_payload.schema.json`에 `self_assessment` 블록 추가 (선택적). 발신 측이 행동 가능성을 자기 진단. |
| **KO 매핑 문서** | `docs/knowledge-object-mapping.md` — 기존 산출물의 명시지 분류 매핑표 + 개선 우선순위. |

### 수정 파일

**신규**

| 파일 | 설명 |
|------|------|
| `skills/mso-skill-governance/schemas/knowledge_object.schema.json` | 명시지 분류 체계 기초 스키마 |
| `skills/mso-skill-governance/schemas/tool_registry.schema.json` | KO 구조 포함 Tool Registry 스키마 |
| `skills/mso-skill-governance/schemas/mso-convention.schema.json` | Workspace Convention 검증 스키마 |
| `skills/mso-skill-governance/schemas/gate_output.schema.json` | Gate Output Schema |
| `skills/mso-skill-governance/defaults/mso-convention.default.yaml` | 기본 Workspace Convention |
| `skills/mso-skill-governance/modules/module.tool-lifecycle.md` | Tool Lifecycle 관리 모듈 |
| `skills/mso-skill-governance/modules/module.workspace-convention.md` | Convention 로딩/검증/투영 모듈 |
| `skills/mso-skill-governance/references/symlink-convention.md` | Symlink 경로 규약 참조 문서 |
| `skills/mso-observability/modules/module.model-monitoring.md` | 모델 모니터링 모듈 |
| `docs/knowledge-object-mapping.md` | 기존 산출물 KO 매핑 문서 |

**수정**

| 파일 | 변경 |
|------|------|
| `skills/mso-observability/scripts/collect_observations.py` | 모델 모니터링 + 승격 탐지 함수 추가 |
| `skills/mso-observability/schemas/observability_callback.schema.json` | event_type 2개 추가 |
| `skills/mso-observability/modules/modules_index.md` | model-monitoring 모듈 등록 |
| `skills/mso-skill-governance/scripts/_cc_defaults.py` | CC-15 등록, 버전 v0.1.1 |
| `skills/mso-skill-governance/scripts/validate_cc_contracts.py` | CC-15 매핑 + 검증 범위 확장 |
| `skills/mso-skill-governance/modules/modules_index.md` | tool-lifecycle, workspace-convention 모듈 등록 |
| `skills/mso-model-optimizer/schemas/handoff_payload.schema.json` | self_assessment 블록 추가 |
| `docs/pipelines.md` | CC-15 추가, mermaid 다이어그램 갱신 |
| `docs/changelog.md` | v0.1.1 변경 이력 추가 |
| `README.md` | v0.1.1 반영 |

### 하위 호환

- **CC-15**: 순수 추가. CC-01~14 변경 없음.
- **observability_callback.schema.json**: event_type enum에 2개 추가. 기존 event_type은 변경 없음.
- **handoff_payload.schema.json**: `self_assessment`는 선택적 필드. `required`에 미포함. 기존 payload와 완전 호환.
- **collect_observations.py**: 기존 함수 변경 없음. 신규 함수 2개 추가 + `build_events`에서 호출.
- **mso-convention.yaml**: 파일 미존재 시 기본 convention으로 fallback. 기존 워크플로우에 영향 없음.
- **tool_registry.json**: 파일 미존재 시 승격 탐지를 건너뜀. 기존 워크플로우 차단 없음.

---

## v0.1.0 (2026-03-24)

### 핵심 변경: mso-model-optimizer — Label Strategy + PEFT 통합

소량 라벨 환경에서도 Automation Escalation이 가능하도록 `mso-model-optimizer`를 대폭 확장.

#### Part 1: Label Strategy (Phase 1.5) 신설

| 변경 | 내용 |
|------|------|
| **Phase 1.5: Label Strategy (LS-0~3)** | 라벨 부족 시 최적 라벨 확보 전략을 자동 선택하는 Phase. LS-0(Zero-shot) → LS-1(Few-shot+증강) → LS-2(Active Learning) → LS-3(충분→직행) |
| **module.label-strategy.md** | Zero-shot NLI, Clustering, Active Learning, Weak Supervision, LLM 합성 데이터 전략을 통합한 라벨 확보 모듈 |
| **module.data-augmentation.md** | EDA, Back-Translation, LLM Paraphrase 3가지 증강 전략. 자동 선택 + 품질 검증(NLI 일치도) |
| **임베딩 캐싱** | kNN baseline 단계에서 계산된 임베딩을 `embeddings_cache.npy`로 저장, Phase 4 평가/Clustering/AL에서 재사용 |

#### Part 2: TL-20 PEFT 확장

| 변경 | 내용 |
|------|------|
| **TL-20 3경로 라우팅** | 경로 A(SetFit, 50~200), 경로 B(LoRA/QLoRA, 200~2K), 경로 C(표준 FT, 2K~10K) 자동 라우팅 |
| **SetFit 경로** | Sentence Transformer contrastive fine-tuning. 클래스당 8개 라벨로 GPT-3급 성능 |
| **LoRA/QLoRA 경로** | 저랭크 어댑터 파인튜닝. VRAM 10~20배 절감. QLoRA: 4-bit 양자화 |
| **NER 오버라이드** | NER/tagging 태스크는 per-entity 라벨 수 기반 라우팅 (< 500 → LoRA 강제) |
| **경로 간 강등** | SetFit → LoRA → 표준 FT → TL-10 순서 강등 정책 |

#### Part 3: Signal A 확장

| 변경 | 내용 |
|------|------|
| **effective_count** | `labeled + 0.7 × (augmented + weak + synthetic)`. 소스별 품질 가중치 적용 (인간=1.0, 증강=0.7, 합성=0.5, pseudo=0.3) |
| **labeled/unlabeled 분리** | `total_count` 단일 기준 → `labeled_count` + `unlabeled_count` 분리 |
| **deploy_spec 확장** | `reproducibility`에 `labeled_count`, `augmented_count`, `effective_count`, `label_strategy`, `training_route` 추가 |

#### Part 4: TL-30 DAPT 명시

| 변경 | 내용 |
|------|------|
| **Stage 1 명칭 변경** | "Domain Pretrain" → "Domain-Adaptive Pretraining (DAPT)" |
| **DAPT 자동 권고** | `unlabeled_count > 10K`이면 DAPT 권고, 사용자 승인 후 실행 |

### 수정 파일

**신규**

| 파일 | 설명 |
|------|------|
| `skills/mso-model-optimizer/modules/module.label-strategy.md` | Phase 1.5: LS-0~3 라벨 확보 전략 |
| `skills/mso-model-optimizer/modules/module.data-augmentation.md` | EDA, Back-Translation, LLM Paraphrase 증강 |
| `skills/mso-model-optimizer/docs/changelog.md` | 스킬 레벨 변경 이력 |
| `skills/mso-model-optimizer/docs/architecture.md` | 스킬 아키텍처 개요 |
| `skills/mso-model-optimizer/docs/getting-started.md` | 시나리오별 시작 가이드 |

**수정**

| 파일 | 변경 내용 |
|------|----------|
| `skills/mso-model-optimizer/SKILL.md` | Phase 1.5 삽입, TL-20 3경로, deploy_spec 확장, version: 0.1.0 |
| `skills/mso-model-optimizer/core.md` | 용어 5개 추가, Processing Rules 13개로 확장, Error Handling 강화 |
| `skills/mso-model-optimizer/modules/module.model-decision.md` | Signal A effective_count 기반, 소스 품질 가중치, base_model 가이드 확장 |
| `skills/mso-model-optimizer/modules/module.training-level.md` | TL-20 SetFit/LoRA/QLoRA 3경로, NER 오버라이드, TL-30 DAPT |
| `skills/mso-model-optimizer/modules/modules_index.md` | 신규 모듈 2개 등록 |
| `README.md` | v0.0.10 → v0.1.0, 변경 이력 + Roadmap 갱신 |
| `docs/changelog.md` | v0.1.0 섹션 추가 |

### 하위 호환

- v0.0.10의 5-Phase 구조는 유지. Phase 1.5는 Phase 1과 Phase 2 사이에 **조건부 삽입**되며, 라벨이 충분하면(LS-3) 기존과 동일하게 건너뜀.
- `dataset_stats.json`에 `labeled_count`, `unlabeled_count` 필드 추가. 기존 `total_count`는 유지되며, `label_strategy_output.json` 미존재 시 `total_count`로 fallback.
- TL-20의 기존 표준 Fine-tuning은 경로 C로 유지. 신규 경로 A(SetFit), B(LoRA)가 추가.
- `deploy_spec.json`의 `reproducibility` 블록에 선택 필드 추가. 기존 필수 필드 변경 없음.

---

## v0.0.10

### 핵심 변경

#### Part 1: mso-model-optimizer 스킬 신설

| 변경 | 내용 |
|------|------|
| **mso-model-optimizer 스킬 추가** | Smart Tool의 `slots/inference/` 슬롯을 채울 경량 특화 모델을 학습·평가·배포하는 스킬. 5-Phase 파이프라인 (트리거→데이터수집→TL판단→학습→평가→배포) |
| **Training Level (TL-10/20/30)** | TL-10: Rule/Heuristic, TL-20: 경량 파인튜닝, TL-30: 전체 학습. `TL-` 접두어로 Automation Level과 명시적 구분 |
| **deploy_spec.json** | 모델 배포 계약. reproducibility(재현성 메타데이터) + evaluation(평가 지표) + rollback(Fallback 전략) 포함 |
| **model-retraining 모듈** | data drift 감지 → 데이터 병합(Append/Window/Replace) → 재학습 → regression guard |
| **rollback 모듈** | rolling_f1/latency_p95/error_rate 모니터링 → Degradation 3단계 → Fallback(llm_passthrough/previous_version/rule_fallback) |

#### Part 2: Smart Tool 구조 표준

| 변경 | 내용 |
|------|------|
| **Smart Tool manifest.json** | Tool의 메타정보(name, version, lifecycle_state)와 슬롯 구조(input_norm/rules/inference/script)를 선언하는 표준 스키마 |
| **Thin Agent, Thick Smart Tools 패턴** | Agent는 orchestration에 집중, 실제 기능은 Smart Tool 내부로 이동하는 설계 원칙 공식화 |
| **Tool Lifecycle** | Local → Symlinked → Global 3단계 승격. pattern_stability + workspace_count + abstraction_score 기반 |
| **Tier Escalation vs Tool Lifecycle 직교 분리** | Tier Escalation = "어떤 수준으로 처리할 것인가"(처리 전략), Tool Lifecycle = "어디에 배치할 것인가"(배치 scope). 별개의 축 |

#### Part 3: CC-11~14 계약 추가

| 변경 | 내용 |
|------|------|
| **CC-11: workflow-optimizer → model-optimizer** | Tier Escalation 시 Handoff Payload 전달. activation_condition: model_replacement_needed=true |
| **CC-12: model-optimizer → audit-log** | 모델 평가 결과를 audit_global.db에 기록 (work_type: model_optimization/model_retraining/model_rollback) |
| **CC-13: model-optimizer → task-context** | deploy_spec.json 배포 지시를 TKT 티켓으로 등록 |
| **CC-14: observability → model-optimizer** | rolling_f1 모니터링 → 재학습 트리거. activation_condition: 배포된 모델 존재 시 |
| **CC_VERSION 0.0.10** | _cc_defaults.py 버전 갱신, validate_cc_contracts.py에 CC-11~14 매핑 추가 |

#### Part 4: mso-workflow-optimizer 연동

| 변경 | 내용 |
|------|------|
| **Tier Escalation → model-optimizer 연동** | SKILL.md에 model-optimizer 트리거 섹션 추가. Handoff Payload 생성 과정 명시 |
| **Pack 내 관계 확장** | model-optimizer 2행 추가 (→ Handoff, ↔ llm-as-a-judge 공유) |

### 수정 파일

**신규**

| 파일 | 설명 |
|------|------|
| `skills/mso-model-optimizer/SKILL.md` | 5-Phase 정의 + Handoff Payload + Rollback + Retraining |
| `skills/mso-model-optimizer/core.md` | Terminology + I/O Interface + Processing Rules |
| `skills/mso-model-optimizer/modules/modules_index.md` | Core + Operational 모듈 인덱스 |
| `skills/mso-model-optimizer/modules/module.model-decision.md` | 3-Signal Training Strategy 판단 |
| `skills/mso-model-optimizer/modules/module.training-level.md` | TL-10/20/30 실행 흐름 + 강등 정책 |
| `skills/mso-model-optimizer/modules/module.model-retraining.md` | 재학습 루프 + drift 감지 + regression guard |
| `skills/mso-model-optimizer/modules/module.rollback.md` | Degradation 정책 + Fallback 전략 |
| `skills/mso-model-optimizer/schemas/deploy_spec.schema.json` | 모델 배포 계약 스키마 |
| `skills/mso-model-optimizer/schemas/handoff_payload.schema.json` | workflow-optimizer → model-optimizer Handoff 스키마 |
| `skills/mso-model-optimizer/schemas/smart_tool_manifest.schema.json` | Smart Tool manifest 표준 스키마 |

**수정**

| 파일 | 변경 |
|------|------|
| `skills/mso-workflow-optimizer/SKILL.md` | Tier Escalation → model-optimizer 연동 섹션 추가 + Pack 내 관계 2행 추가 |
| `skills/mso-skill-governance/scripts/_cc_defaults.py` | CC-11~14 등록, CC_VERSION 0.0.10 |
| `skills/mso-skill-governance/scripts/validate_cc_contracts.py` | CC-11~14 매핑 + 검증 로직 |
| `skills/mso-skill-governance/SKILL.md` | CC 검증 범위 CC-14로 확장 |
| `docs/pipelines.md` | mermaid 다이어그램에 Model Optimizer + CC-11~14 추가, CC-11~14 계약 설명 |
| `docs/changelog.md` | v0.0.10 변경 이력 추가 |
| `README.md` | v0.0.10 반영 + Roadmap 조정 |

### 하위 호환 (v0.0.9 → v0.0.10)

- **mso-model-optimizer**: 순수 신규 스킬. 기존 워크플로우에 영향 없음
- **Smart Tool manifest**: 기존 tool에 manifest.json이 없어도 기존 동작에 영향 없음
- **CC-11~14**: 순수 추가. CC-01~10 변경 없음
- **CC-11 activation_condition**: Tier Escalation + model_replacement_needed 미발생 시 warn 처리 (파이프라인 차단 없음)
- **CC-14 activation_condition**: 배포된 모델 미존재 시 warn 처리
- **Handoff Payload**: workflow-optimizer goal에 `model_replacement_needed` 필드가 없으면 CC-11은 트리거되지 않음
- **Tool Lifecycle**: 기존 스킬에 lifecycle_state 개념이 부재하더라도 영향 없음. 신규 Smart Tool 생성 시부터 적용

---

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
