# 시작하기

## 디렉토리 구조

```
.skill-modules/                      ← 설치 후 ~/.skill-modules/mso-skills/ 심링크
├── mso-skill-governance/            ← 계약 검증, 구조 점검
├── mso-workflow-topology-design/    ← 목표 → 노드 구조 (Mode A: 신규 설계, Mode B: Graph Search)
├── mso-mental-model/                ← Vertex Registry: directive 택소노미·바인딩
│   └── directives/                  ← seed directives (analysis, general)
├── mso-agent-collaboration/         ← 티켓 관리 + 멀티에이전트 디스패치 (branch/merge)
│   ├── templates/                   ← PRD.md, SPEC.md, ADR.md
│   └── scripts/                     ← collaborate.py, ai_collaborator/
├── mso-agent-audit-log/             ← 감사 인프라 SoT (DB + 세션 훅 + 실행 로그)
│   ├── hooks/                       ← session_start_hook.py, pre_compact_hook.py, session_end_hook.py
│   ├── scripts/                     ← setup.py, init_db.py, inject_hooks.py, append_from_payload.py
│   └── history/                     ← 스키마 버전 스냅샷
├── mso-observability/               ← 관찰, 환류 (패턴 분석)
│   └── templates/                   ← HITL_ESCALATION_BRIEF.md, RUN_RETROSPECTIVE.md
├── mso-workflow-optimizer/          ← 워크플로우 성과 평가, Automation Level 판단
│   ├── modules/                     ← process-optimizing, llm-as-a-judge 등
│   ├── configs/                     ← llm-model-catalog.yaml
│   ├── schemas/                     ← optimizer_result.schema.json
│   └── scripts/                     ← select_llm_model.py
├── mso-model-optimizer/             ← Smart Tool 경량 모델 학습·평가·배포
│   ├── modules/                     ← model-decision, training-level, retraining, rollback
│   └── schemas/                     ← deploy_spec, handoff_payload, smart_tool_manifest
├── mso-workflow-repository-setup/   ← Workflow Repository + Scaffold + Memory Layer 설정
├── mso-harness-setup/               ← Runtime Harness + 실행 조율 (canonical event · policy · evaluator · execution_graph)
└── _shared/                         ← 공통 유틸 (runtime_workspace.py)
skills/
├── mso-orchestration/               ← 진입점 스킬 (→ ~/.claude/skills/mso-orchestration 심링크)
└── mso-agent-audit-log/             ← 감사 인프라 참조 문서 레이어
rules/
└── ORCHESTRATOR.md                  ← 불변 정책
docs/
├── architecture.md                  ← Git-Metaphor 모델, 전체 아키텍처
├── pipelines.md                     ← 3대 파이프라인, CC 계약, 티켓 생명주기
├── getting-started.md               ← 이 문서
├── usage_matrix.md                  ← Phase × Swarm × Role 매트릭스
└── changelog.md                     ← 버전별 변경 이력
```

각 스킬 디렉토리의 `SKILL.md` 파일만 확인하면 해당 스킬의 목적, 입출력, 실행 절차를 모두 파악할 수 있다. `modules/`나 `schemas/`는 상세 구현 확인 시에만 참조한다.

v0.0.3부터는 별도 `config.yaml` 없이 동작한다. 환경별 오버라이드는 `MSO_WORKSPACE_ROOT`, `MSO_OBSERVATION_ROOT`, `MSO_OBSERVER_ID`로만 처리한다.

---

## 0. 감사 인프라 초기화 (레포 설정 시 1회)

새 프로젝트 레포에서 MSO를 사용하기 전에 감사 DB와 세션 훅을 초기화한다.

```bash
python3 ~/.skill-modules/mso-skills/mso-agent-audit-log/scripts/setup.py \
  --project-root <repository_root> \
  --target claude    # claude | codex | all
```

한 번에 수행하는 작업:
1. `{repository}/00.agent_log/logs/` 디렉터리 생성
2. `{repository}/.mso-context/audit_global.db` 스키마 초기화
3. `{repository}/.claude/settings.json`에 `SessionStart · PreCompact · SessionEnd` 훅 주입 (멱등)

Codex도 함께 설정하려면 `--target all`을 사용한다.

---

## {repository} 디렉토리 구조

MSO 런타임 산출물은 기본적으로 `{repository}/.mso-context` 하위에 기록된다.

```text
{repository}/
├── .mso-context/
│   ├── audit_global.db              ← 전체 감사 데이터 SoT
│   ├── workflow_registry.json       ← Run 인덱스
│   ├── config/
│   │   └── policy.yaml
│   ├── active/
│   │   └── <run_id>/
│   │       ├── manifest.json
│   │       ├── 10_topology/         ← workflow_topology_spec.json
│   │       ├── 20_mental-model/     ← directive_binding.json
│   │       ├── 30_execution/        ← execution_plan.json
│   │       ├── 40_collaboration/    ← task-context/tickets/
│   │       ├── 50_audit/            ← snapshots/
│   │       ├── 60_observability/    ← callback-*.json
│   │       ├── 70_governance/
│   │       └── optimizer/           ← goal.json, handoff_payload.json
│   └── archive/
├── .claude/
│   └── settings.json                ← SessionStart·PreCompact·SessionEnd 훅
└── 00.agent_log/
    └── logs/                        ← worklog-YYYYMMDD.md
```

> 스킬 내부 경로 표기: `{스킬명}/*` (예: `{mso-workflow-optimizer}/scripts/select_llm_model.py`)

---

## 1. 워크플로우 설계 (Design)

두 가지 경로가 있다. 유사한 워크플로우가 레지스트리에 있으면 **Mode B**(검색)를 먼저 시도하고, 없으면 **Mode A**(신규 설계)로 진행한다.

### Mode B: Graph Search (기존 워크플로우 로딩)

```bash
RUN_ID="YYYYMMDD-msowd-onboarding"

# 레지스트리에서 유사 워크플로우 검색
python3 {mso-workflow-topology-design}/scripts/graph_search.py \
  --intent "사용자 온보딩 프로세스 설계" \
  --top-k 3 \
  --registry {repository}/.mso-context/workflow_registry.json
```

similarity ≥ 0.6이면 검색된 워크플로우로 진행. 아니면 Mode A로 fallback.

### Mode A: 신규 설계

```bash
RUN_ID="YYYYMMDD-msowd-onboarding"

# 목표(Goal)를 입력하면 노드 구조(Topology)가 생성된다.
python3 {mso-workflow-topology-design}/scripts/generate_topology.py \
  --run-id "$RUN_ID" \
  --skill-key msowd \
  --case-slug onboarding \
  --goal "사용자 온보딩 프로세스 설계"

# 각 노드에 directive를 바인딩한다 (Vertex Registry 검색).
python3 {mso-mental-model}/scripts/bind_directives.py \
  --topology {repository}/.mso-context/active/$RUN_ID/10_topology/workflow_topology_spec.json \
  --registry {repository}/.mso-context/vertex_registry \
  --output {repository}/.mso-context/active/$RUN_ID/20_mental-model/directive_binding.json

# 두 결과를 통합하여 execution_graph를 생성한다.
python3 {mso-harness-setup}/scripts/build_plan.py \
  --run-id "$RUN_ID" \
  --skill-key msowd \
  --case-slug onboarding
```

---

## 2. 티켓 운영 (Ops)

```bash
TASK_ROOT="{repository}/.mso-context/active/$RUN_ID/40_collaboration/task-context"

python3 {mso-agent-collaboration}/scripts/create_ticket.py \
  "온보딩 플로우 구현" \
  --path "$TASK_ROOT"

python3 {mso-agent-collaboration}/scripts/archive_tasks.py \
  --path "$TASK_ROOT"
```

---

## 3. 멀티 프로바이더 실행 (Multi-Provider)

Codex·Claude·Gemini CLI로 동일 프롬프트를 동시에 전송하거나, 프로바이더별 역할을 분리하여 실행한다.
`mso-agent-collaboration` 스킬에 포함된 `collaborate.py`를 사용한다.

```bash
COLLAB=~/.skill-modules/mso-skills/mso-agent-collaboration/scripts

# 프로바이더 상태 확인
python3 "$COLLAB/collaborate.py" status

# 전체 프로바이더에 동일 프롬프트 전송 (second opinion)
python3 "$COLLAB/collaborate.py" run --all \
  --context ./PRD.md \
  -m "PRD를 시니어 리뷰어 관점에서 비평해줘" \
  --format json

# 프로바이더별 역할 분리
python3 "$COLLAB/collaborate.py" run --context ./PRD.md --tasks \
  "codex@gpt-5:아키텍처 가정 검토:arch" \
  "claude@sonnet:구현 리스크 식별:risk" \
  "gemini@gemini-2.5-pro:실현 가능성 확인:feasibility" \
  --format json

# Swarm 세션 (tmux 기반 장기 실행)
python3 "$COLLAB/collaborate.py" swarm init --db ./.ai-collab/swarm.db
python3 "$COLLAB/collaborate.py" swarm start \
  --db ./.ai-collab/swarm.db \
  --session team-a \
  --agents planner:claude,coder:codex,reviewer:gemini
```

티켓에서 swarm을 자동 실행하려면 frontmatter에 추가:

```yaml
---
id: TKT-0001
title: 멀티 에이전트 분석
status: todo
tags: [swarm]
swarm_db: ./.ai-collab/swarm.db
swarm_session: team-a
swarm_agents: planner:claude,coder:codex,reviewer:gemini
---
```

---

## 4. 검증 (Validation)

```bash
# 스키마 정합성 확인
python3 {mso-skill-governance}/scripts/validate_schemas.py \
  --run-id "$RUN_ID" \
  --skill-key msogov \
  --case-slug onboarding \
  --json

# 전체 거버넌스 점검
python3 {mso-skill-governance}/scripts/validate_all.py \
  --run-id "$RUN_ID" \
  --skill-key msogov \
  --case-slug onboarding

# 설계 → 운영 → 인프라 통합 테스트
python3 {mso-skill-governance}/scripts/run_sample_pipeline.py \
  --goal "테스트 파이프라인" \
  --task-title "샘플 티켓" \
  --skill-key msowd \
  --case-slug onboarding
```
