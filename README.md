# Multi-Swarm Orchestrator (MSO) v0.4.0

MSO는 **filesystem/repository 중심 agentic workflow compiler**다.

Claude Code, Codex 같은 provider runtime을 대체하지 않는다. 그 위에서 **repository 구조·workflow·작업 기억을 선언하면, 에이전트가 실행 가능한 형태로 컴파일**한다.

---

## v0.4.0 Dataflow Observability Patch

v0.4.0은 workflow sub-graph에서 산출물/입력 데이터 흐름을 볼 수 있게 만든 관측성 패치다. 실행 노드만 보던 그래프에 Data node를 파생해, workflow를 task 묶음이 아니라 **data stream topology**로 관측한다.

- `wf:directory`를 `data_type=local_file`, `location=<dirPath>` Data node로 파생한다. `role: input/reference`는 `data --upstream--> task`, `role: output`은 `task --downstream--> data`, `role: input_output`은 양방향 stream으로 표시한다.
- `wf:deliverables`는 선언 산출물 Data node로 표시하고 `task --downstream--> data` edge로 연결한다. 현재는 local file deliverable 힌트로 렌더링한다.
- 같은 target Data id로 연속되는 stream은 하나의 workflow로 보고, 분기되거나 다른 방식으로 소비되는 stream은 별도 workflow boundary 후보로 해석한다.
- workflow별 관측 뷰는 `integrated`, `workflow`, `data-stream`으로 나뉜다. `data-stream`은 supply chain을, `workflow`는 그 supply chain에서 파생한 `((start)) --next--> task --next--> ((end))` spine을, `integrated`는 둘을 함께 보여준다.
- GitHub Mermaid 호환성을 위해 classic flowchart shape를 사용한다: task `["label"]`, data `(["label"])`, decision `{{"label"}}`, oracle `[/"label"\]`.
- workflow별 sub-graph에서 phase membership은 `hasNode` edge 대신 Mermaid `subgraph` containment로 렌더링한다.
- Mermaid label에 `id: <node-id>`를 노출해 사용자가 특정 node id를 지목해 수정 요청할 수 있게 한다.
- Data node label은 `DATA`와 `id`만 표시한다. `location: index:<data-id>`와 실제 path/API/MCP resource `locator:`는 graph 아래 `Data Node Index` 표로 분리한다.
- repository-level topology는 계속 phase/module/milestone 중심으로 유지하고, Data node 흐름은 workflow별 sub-graph에서만 펼친다.
- 이후 API endpoint, MCP resource, database table 같은 비파일 입력/출력도 같은 Data node 계층으로 확장한다.

## v0.4.0 Decision/Oracle Gate Separation Patch

v0.4.0는 workflow topology에서 **process decision**과 **artifact oracle**을 분리한 패치다. 순환 자체는 허용하지만, 산출물이 재귀 소비되는 feedback loop에는 별도 Oracle gate가 있어야 한다.

- `decision`은 진행/분기를 제어한다. user decision은 HITL/HITLFE/HOTL/HOOTL, agent decision은 AGENT judge로 표현한다.
- `oracle`은 산출물 품질·정합·수용 가능성을 평가한다. `oracle_type`은 user/agent/metric을 지원한다.
- `wf_to_ttl.py`와 generated SHACL은 DAG를 강제하지 않고, Oracle gate 없는 uncontrolled feedback loop만 오류로 판정한다.
- workflow subgraph에는 `wf:next`와 branch `gotoNode` 흐름을 표시하고, repository topology는 phase/module/milestone 수준으로 유지한다.

## v0.4.0 TTL-only Workflow Observability Patch

v0.4.0은 workflow SSOT 경계를 더 엄격하게 고정한 패치다. YAML은 신규 작성/역생성 대상이 아니라 **legacy migration input**으로만 남긴다.

- `mso-graph-observability`는 TTL ABox만 topology 입력으로 사용하고, repository 전체 graph와 workflow별 sub-graph를 함께 생성한다.
- `workflow-ssot-report.md`는 legacy YAML 중 sibling `.abox.ttl`이 없는 항목을 drift로 표시한다.
- `ttl_to_wf.py` 역생성 경로를 제거했다. legacy YAML 흡수는 `migrate_workflows_to_ttl.py`만 사용한다.
- multi-workflow repository에서 같은 phase/node id가 충돌하지 않도록 URI를 workflow scope로 분리한다.
- work-memory는 JSONL SSOT를 유지하되, curated entries를 TTL ABox로 projection하고 SHACL로 relation/lifecycle target 타입을 검증한다.

## v0.4.0 Graph Observability + Codex hook adapter 정식화

v0.4.0은 workflow TTL-first 체제 위에 **graph observability**를 기본 내장하고, Codex hook adapter의 중복/잡음 문제를 정리한 정식 버전이다.

- `mso-graph-observability`를 추가해 workflow graph는 Mermaid view로, work-memory/auditlog/worklog/intent turn은 runtime analysis로 관측한다.
- graph observability 산출물은 `agent-context/observability/graph/` 아래에 둔다.
- Codex hook adapter는 `Stop`/`PreCompact`에서 worklog만 기록하고, 기록 판단 넛지는 `SessionStart(compact|resume)`에만 둔다.
- §11 NLU 경계 재편을 정식 버전에 포함한다. utterance→intent는 UUG, intent→action은 MSO가 맡는다.

## v0.3.6 TTL-first + Decision Governance 적용

v0.3.6은 `mso-v0.3.6-PLAN.md`의 work-memory decision governance를 정식 `repository/`로 승격하고, workflow 정본을 TTL ABox로 확정한 패치 버전이다.

- work-memory에 `alternatives-record`(AR)와 `user-decision.boundary/criterion` 거버넌스 컨벤션을 포함한다.
- `mso-repository-setup`은 신규 프로젝트에 `work-memory/track-record/alternatives-record/`를 부트스트랩한다.
- workflow의 SSOT는 `workflow/*.abox.ttl`이다. YAML은 legacy migration input이고 `migrate_workflows_to_ttl.py`로 한 번 흡수한다.
- provider-free 적용면은 v0.3.5의 Claude 성능 비회귀 원칙을 유지한다.

## v0.3.5 Provider-Free 적용

v0.3.5는 Claude Code의 기존 성능과 hook 동작을 유지하면서 Codex에서도 같은 MSO 스킬셋을 사용할 수 있도록 적용면을 정리한 패치다.

- 글로벌 동기화 대상에 `~/.codex/skills`를 포함해 MSO 스킬이 Claude Code와 Codex에 동일하게 전파된다.
- `mso-intent-analytics`, `mso-conversation-analytics`가 글로벌 스킬 허브와 설치 스크립트에 포함된다.
- `mso-repository-setup scripts/init.py --hook`의 기본 provider는 여전히 `claude`다. 기존 `.claude/settings.json`, `PostToolUse`, `Stop`, `SessionStart` hook 생성 방식은 바꾸지 않았다.
- Codex에서 hook이 필요한 경우에만 `--provider codex`를 명시해 `.codex/hooks.json`과 `.codex/scripts/`를 생성한다.
- Codex hook은 현재 확인된 lifecycle hook 중심으로만 등록한다. Claude Code 전용 `PostToolUse` 감사로그는 Claude 경로에만 유지한다.

---

## MSO가 해결하는 문제

AI 에이전트가 repository에서 작업할 때 세 가지 문제가 반복된다.

1. **구조 없음**: 에이전트가 매번 codebase를 재탐색한다. 모듈이 무엇이고 디렉토리가 어떤 역할인지 명시되지 않으면 컨텍스트가 낭비된다.
2. **절차 없음**: 어떤 작업을 어떤 순서로, 누가 결정하고, 언제 사람이 개입하는지가 암묵적이다. 에이전트가 혼자 판단하거나, 불필요하게 모든 것을 사람에게 묻는다.
3. **기억 없음**: 세션이 끝나면 어떤 도구를 썼고, 어떤 결정을 내렸고, 무엇을 배웠는지가 사라진다. 동일한 실패가 반복된다.

MSO는 이 세 문제에 각각 하나씩 대응한다.

| 문제 | MSO의 답 | 핵심 파일 |
|------|----------|----------|
| 구조 없음 | Directory Index 명문화 | `index.yaml` |
| 절차 없음 | Workflow Schema 명문화 + HITL 수준 명시 | `workflow/*.abox.ttl` |
| 기억 없음 | Hook 기반 Execution Context 자동 적재 | `work-memory/` JSONL |

---

## v0.3.0의 네 가지 핵심 전환

### 1. Filesystem/Repository 중심 Agentic Workflow Compiler

MSO는 repository를 에이전트의 실행 컨텍스트로 취급한다. 선언이 컴파일 대상이다.

```
선언 / 그래프                     컴파일 산출물
─────────────────────             ──────────────────────────────
index.yaml                    →   모듈·디렉토리 구조 SSOT
  + sf_node.py validate            스키마 검증 / 파일시스템 대조

workflow/*.abox.ttl           →   phase · step · decision · validation 노드
  + observe_graph.py               repository graph + workflow sub-graph 관측
  + migrate_workflows_to_ttl.py    legacy YAML → TTL ABox 정본 마이그레이션

Markdown · Mermaid            ←   변환 산출물 (직접 편집 금지)
```

workflow의 `decision` 노드는 `judge` 필드로 자동화 수준을 4단계로 명시한다.

| judge | 의미 |
|-------|------|
| `HITL` | 사람이 검토 후 진행 |
| `HITLFE` | 사람이 검토, 에이전트가 초안 |
| `HOTL` | 에이전트가 실행, 사람이 나중에 검토 |
| `HOOTL` | 에이전트가 실행, 사람에게 보고만 |

### 2. Index + Workflow 기반 Execution Context 자동 적재

`index.yaml`과 workflow TTL ABox는 선언으로 끝나지 않는다. provider hook이 세션 중 도구 사용과 세션 종료를 감지하여 실행 컨텍스트를 `work-memory`에 자동으로 적재한다.

```
Claude Code 세션
    │
    ├── PostToolUse (Bash | Edit | MultiEdit | Write)
    │       → hooks/auditlog.py
    │       → work-memory/auditlog/AU-YYYY-MM-DD.jsonl
    │         {"tool_name", "tool_input", "session_id", "timestamp", ...}
    │
    ├── Stop (세션 종료)
    │       → hooks/worklog.py
    │       → work-memory/worklog/WL-YYYY-MM-DD.jsonl
    │         {"session_id", "timestamp", "hook_event_name", ...}
    │
    └── SessionStart(compact/resume) (기록 판단 넛지)
            → hooks/work-memory-check.sh
            → track/insight entry 기록 시점을 비차단으로 상기 (로깅이 아니라 판단 트리거)
```

`init.py --hook`이 `.claude/settings.json`에 세 hook(auditlog · worklog · work-memory-check)을 등록한다. 앞의 둘은 도구 사용 이력과 세션 종료를 자동 누적하고, work-memory-check는 기록할 결정이 쌓였는지 판단해 상기시킨다.

Codex 환경에서는 다음처럼 등록한다.

```bash
python3 skills/mso-repository-setup/scripts/init.py --hook . --provider codex \
  --worthy-paths "agent-context .codex .claude .gitmodules README.md"
```

이 명령은 `.codex/scripts/`에 hook 스크립트를 복사하고 `.codex/config.toml`에
`Stop`·`PreCompact` worklog와 `SessionStart(compact|resume)` 기록 판단 넛지를 등록한다.
`.codex/hooks.json`은 중복 실행 방지를 위한 빈 compatibility 파일로 함께 생성한다.
Claude Code 전용 `PostToolUse` auditlog는 Claude 설정에만 둔다.

### 3. Work-Memory 구조화 Logging

work-memory는 자동 기록(hook)과 수동 기록(`wm_node.py`) 두 층으로 구성된다. 모든 entry는 JSONL 포맷이며 `schema.yaml`이 스키마를 정의한다.

**자동 기록 (hook)**

| 타입 | 파일 패턴 | 트리거 |
|------|----------|--------|
| auditlog | `AU-YYYY-MM-DD.jsonl` | PostToolUse: Bash·Edit·Write |
| worklog | `WL-YYYY-MM-DD.jsonl` | Stop (세션 종료) |

**수동 기록 (wm_node.py new)**

| 카테고리 | 타입 | prefix | 용도 |
|---------|------|--------|------|
| track-record | issue-note | `IN` | 발견된 이슈·버그 |
| track-record | agent-decision | `AD` | 에이전트가 내린 결정과 근거 |
| track-record | alternatives-record | `AR` | 결정 전 옵션·득실·권고안 |
| track-record | user-decision | `UD` | 사람 또는 metric oracle 이 내린 결정과 승인 |
| track-record | trouble-shooting | `TS` | 문제 해결 과정 |
| insight-record | episodes | `EP` | 주목할 경험과 관찰 |
| insight-record | patterns | `PT` | 반복 패턴과 공통 구조 |
| insight-record | principles | `PR` | 도출된 원칙과 규칙 |

**기록 판단 넛지 (hook)**

자동 기록은 *무엇을 했는지*를 남기지만, track/insight entry를 *언제 남길지*는 판단이 필요하다. 그 판단 트리거가 없으면 수동 기록은 쉽게 누락된다. `hooks/work-memory-check.sh`가 SessionStart(compact/resume)에서 비차단으로 그 판단을 상기시킨다.

| 넛지 | 조건 | 권유 |
|------|------|------|
| track | 결정 가치 있는 변경(`WM_WORTHY_PATHS`)이 최신 기록보다 앞섬 | UD/AD/IN/TS 작성 |
| insight | 종결된 TS 이후 회고(EP)가 없음 | EP → PT → PR 추상화 |

판단 *기준*(어떤 상황에 어떤 entry를 남기나)은 `assets/work-memory-judgment.md`를 프로젝트 rules(CLAUDE.md/AGENTS.md)에 드롭인해 상시 로드한다.

### 4. Sub-Index + 1:N Workflow + Compile-time Topology 제약

**계층 구조 (sub_index)**

대규모 repository는 단일 `index.yaml`로 표현하기 어렵다. MSO는 모듈 단위로 `sub_index`를 선언해 계층 참조를 지원한다 (최대 depth 3).

```yaml
# root index.yaml
modules:
  - id: 01.core
    path: 01.core/
    sub_index: 01.core/agent-context/index/index.yaml   # 모듈 자체 index
```

`sf_node.py validate`는 root → sub_index를 재귀 해석하여 전역 id unique 검증, 경계 침범 검사를 수행한다. sub_index가 있는 모듈은 root에서 `subdirs/key_files/references`를 비워야 한다 — 선언 위치가 컴파일 타임에 강제된다.

**1:N Workflow**

하나의 index.yaml 구조에 여러 workflow가 대응한다. phase는 `workflows[].ref`로 sub workflow를 참조할 수 있다.

```
index.yaml (1)
    └── workflow-lifecycle.abox.ttl   ← 기본 workflow
    └── workflow-feature-a.abox.ttl   ← 기능별 workflow
    └── workflow-release.abox.ttl     ← 릴리즈 workflow

# phase 내 sub workflow 참조
phase:
  workflows:
    - ref: "workflow-release.abox.ttl#P02.validation"
      module: "01.core"
```

**Compile-time Topology 제약 (Rail · Checkpoint · Guardrail)**

workflow TTL ABox의 세 가지 노드 타입이 에이전트의 실행 경로를 컴파일 타임에 제약한다. YAML은 legacy migration input으로만 둔다.

| 노드 타입 | 역할 | 컴파일 타임 검증 |
|----------|------|-----------------|
| `step` | **Rail** — 실행 경로. phase → step 순서가 directed path를 구성한다 | node id 전역 unique · 의존 관계 |
| `validation` | **Checkpoint** — 통과 기준이 선언된 게이트. `wf_node.py harness-manifest`가 validation 노드만 추출해 CI manifest를 생성한다 | 필수 필드 검증 |
| `decision` | **Guardrail** — `judge` 수준으로 에이전트 자율성 한계를 명시한다. HITL이면 사람 없이 진행 불가 | judge 값 검증 · owner 필수 여부 |

```
observe_graph.py --root .
    → repository 전체 workflow topology와 workflow별 sub-graph 생성

migrate_workflows_to_ttl.py agent-context/workflow --check
    → legacy YAML이 남아 있을 때 TTL ABox import drift 검증
```

---

## 스킬 구성

v0.4.0은 **Design → Observability → Ops → Infra → Optimizer → Runtime/NLU** 여섯 레이어에 걸쳐 9개 스킬이 동작한다.
v0.3.0의 5개 스킬(Design/Ops/Infra) 위에, workflow TTL을 LangGraph artifact로 컴파일하는 **Optimizer**, 여러 운영 그래프를 관측하는 **Graph Observability**, UUG가 제공한 intent를 실행 가능한 명령으로 dispatch/analytics 하는 **Runtime/NLU 후단**이 붙는다.

```
사용자 요청
    │
    ▼
mso-orchestration          ← 단일 진입점 · 트리거 매칭 · 라우팅
    │
    ├── [Design]
    │   ├──> mso-scaffold-design     index.yaml SSOT · sf_node.py
    │   └──> mso-workflow-design     workflow TTL ABox SSOT · wf_node.py · Mermaid 변환
    │
    ├── [Observability]
    │   └──> mso-graph-observability workflow/memory/audit/worklog/intent graph 관측
    │
    ├── [Optimizer]
    │   └──> mso-workflow-optimizer  workflow TTL → LangGraph artifact + work-memory ContextPack
    │
    ├── [Ops]
    │   └──> mso-repository-setup   agent-context/ 부트스트랩 · hook 등록
    │
    ├── [Infra]
    │   └──> mso-work-memory        JSONL entry · auditlog · worklog · graph
    │
    └── [Runtime/NLU — §11 재편]
        │   앞단(utterance→intent) = UUG(uug-grounding, 01_user-utterance-grounding, repo 밖)
        ├──> mso-intent-analytics  registry SoT(lookup) + 뒷단 dispatch(pipeline)
        └──> mso-conversation-analytics  ⚠ de-routed — 분석 메서드 UUG 흡수 대기 (직접 호출만)
```

| 스킬 | 레이어 | 핵심 스크립트 |
|------|--------|-----------|
| `mso-orchestration` | — | — |
| `mso-repository-setup` | Ops | `init.py` |
| `mso-scaffold-design` | Design | `sf_node.py` |
| `mso-workflow-design` | Design | `migrate_workflows_to_ttl.py`, TTL ABox conventions |
| `mso-graph-observability` | Observability | `observe_graph.py` — workflow Mermaid view + runtime JSONL analysis |
| `mso-workflow-optimizer` | Optimizer | `compile_workflow.py` — TTL→LangGraph, ContextPack, writeback queue |
| `mso-work-memory` | Infra | `wm_node.py`, `wm_to_ttl.py`, hooks |
| `mso-intent-analytics` *(§11)* | Data+Runtime | `src/lookup.py`(registry), `src/pipeline.py`(뒷단 dispatch), `references/schemas/nlu_intent.yaml` (LinkML) |
| `mso-conversation-analytics` *(de-routed)* | Observability | `src/analytics.py` (DuckDB) — UUG 흡수 대기, 직접 호출만 |

> **§11 NLU 경계 재편**: utterance→intent 분류(앞단)는 UUG(`01_user-utterance-grounding`)로 흡수, intent→action(뒷단 slot/dispatch)만 MSO(`mso-intent-analytics`). 구 `mso-utterance-grounding` 해체, `mso-intent-registry`→`mso-intent-analytics` 개명. v0.4.0 기준 9 스킬.

---

## 생성되는 구조

```
project/
├── agent-context/
│   ├── index/
│   │   └── index.yaml              ← scaffold SSOT (mso-scaffold-design)
│   ├── workflow/
│   │   └── workflow-lifecycle.abox.ttl ← workflow SSOT (mso-workflow-design)
│   ├── observability/
│   │   └── graph/                  ← Mermaid view + runtime analysis (mso-graph-observability)
│   └── work-memory/
│       ├── schema.yaml             ← entry 스키마 정의
│       ├── graph/
│       │   └── work-memory.abox.ttl ← JSONL projection + SHACL validation artifact
│       ├── auditlog/               ← AU-*.jsonl (hook 자동 기록 — 도구 사용)
│       ├── worklog/                ← WL-*.jsonl (hook 자동 기록 — 세션 종료)
│       ├── track-record/
│       │   ├── issue-note/         ← IN-*.jsonl
│       │   ├── agent-decision/     ← AD-*.jsonl
│       │   ├── alternatives-record/← AR-*.jsonl
│       │   ├── user-decision/      ← UD-*.jsonl
│       │   └── trouble-shooting/   ← TS-*.jsonl
│       └── insight-record/
│           ├── episodes/           ← EP-*.jsonl
│           ├── patterns/           ← PT-*.jsonl
│           └── principles/         ← PR-*.jsonl
├── .claude/
│   └── settings.json               ← PostToolUse · Stop · PreCompact hook 등록
└── .gitignore
```

---

## 빠른 시작

### 설치

```bash
bash install.sh          # ~/.claude/skills/ 에 symlink 등록
bash install.sh --all    # Claude + Codex + Gemini 전체
```

### 새 프로젝트 init + hook 등록

```bash
python3 ~/.claude/skills/mso-repository-setup/scripts/init.py \
  --target /path/to/project \
  --name "My Project" \
  --id "my-project-01"

python3 ~/.claude/skills/mso-repository-setup/scripts/init.py \
  --hook /path/to/project
```

### scaffold 정의

```bash
SF=~/.claude/skills/mso-scaffold-design/scripts/sf_node.py
python3 $SF scaffold module --id "01.core"       # stdout → index.yaml 에 붙여넣기
python3 $SF validate agent-context/index/index.yaml
python3 $SF inventory agent-context/index/index.yaml
python3 $SF tree agent-context/index/index.yaml
```

### workflow 관측 / legacy migration

```bash
python3 ~/.claude/skills/mso-graph-observability/scripts/observe_graph.py --root .

# legacy YAML 이 남아 있는 repository에서만 사용
python3 ~/.claude/skills/mso-workflow-design/scripts/migrate_workflows_to_ttl.py agent-context/workflow --check
```

### work-memory 기록

```bash
export WORKMEM_DIR=./agent-context/work-memory
WM=~/.claude/skills/mso-work-memory/scripts/wm_node.py
python3 $WM new issue-note --title "timeout 누락 발견" --tags "policy,timeout"
python3 $WM stats
python3 $WM graph IN-0001 --depth 2

WMG=~/.claude/skills/mso-work-memory/scripts/wm_to_ttl.py
python3 $WMG validate agent-context/work-memory --ttl-out agent-context/work-memory/graph/work-memory.abox.ttl
```

---

## 설계 원칙

**Working System First.** 완벽한 아키텍처보다 실제로 돌아가는 시스템을 먼저 만든다. v0.3.0은 5개 스킬이 실제로 동작하는 것을 검증한 milestone이고, v0.4.0은 UUG 경계 재편 이후 9개 스킬 체제와 graph observability 기준을 정식 repository에 승격한 milestone이다.

**TTL이 workflow SSOT.** `index.yaml`과 workflow `*.abox.ttl`이 정본이다. YAML은 legacy migration input이고, Markdown·Mermaid는 변환 산출물이지 편집 대상이 아니다.

**Provider-free.** Claude Code, Codex, Gemini CLI 어디서나 동일한 스킬과 스크립트가 동작한다.

**HITL 우선.** 에이전트는 제안하고, 사람이 결정한다. `judge` 필드로 자동화 수준을 명시적으로 통제한다.

---

## 의존성

```
Python 3.10+
PyYAML >= 6.0
jsonschema >= 4.24.0
```

---

## 참고

- [docs/getting-started.md](docs/getting-started.md) — 상세 사용법 (설치부터 hook 검증까지)
- [docs/architecture.md](docs/architecture.md) — 스킬 간 관계 · 데이터 흐름 · 파일시스템 레이아웃
- [docs/changelog.md](docs/changelog.md) — 버전별 변경 이력
- 각 `skills/*/SKILL.md` — 스킬별 상세 명세
