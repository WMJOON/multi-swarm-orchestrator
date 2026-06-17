# Multi-Swarm Orchestrator (MSO) v0.3.4

MSO는 **filesystem/repository 중심 agentic workflow compiler**다.

Claude Code, Codex 같은 provider runtime을 대체하지 않는다. 그 위에서 **repository 구조·workflow·작업 기억을 선언하면, 에이전트가 실행 가능한 형태로 컴파일**한다.

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
| 절차 없음 | Workflow Schema 명문화 + HITL 수준 명시 | `workflow/*.yaml` |
| 기억 없음 | Hook 기반 Execution Context 자동 적재 | `work-memory/` JSONL |

---

## v0.3.0의 네 가지 핵심 전환

### 1. Filesystem/Repository 중심 Agentic Workflow Compiler

MSO는 repository를 에이전트의 실행 컨텍스트로 취급한다. 선언이 컴파일 대상이다.

```
선언 (YAML)                       컴파일 산출물
─────────────────────             ──────────────────────────────
index.yaml                    →   모듈·디렉토리 구조 SSOT
  + sf_node.py validate            스키마 검증 / 파일시스템 대조

workflow/*.yaml               →   phase · step · decision · validation 노드
  + wf_node.py validate            스키마 검증 / judge 수준 검증
  + wf_node.py harness-manifest    CI manifest (validation 노드 추출)
  + wf_to_ttl.py validate          ABox(TTL) 투영 → SHACL(shape) + SPARQL(비순환 DAG)

TTL TBox/ABox                 ↔   workflow 형상의 그래프 표현 (파생)
  schemas/*.yaml = SSOT            schemas_to_tbox.py → tbox/ + shapes/ 생성(drift 가드)
  ttl_to_wf.py                     역방향: TTL → SHACL 게이트 → YAML 승격(ingestion)

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

`index.yaml`과 workflow YAML은 선언으로 끝나지 않는다. Claude Code hook이 세션 중 도구 사용과 세션 종료를 감지하여 실행 컨텍스트를 `work-memory`에 자동으로 적재한다.

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
    └── Stop · PreCompact (기록 판단 넛지)
            → hooks/work-memory-check.sh
            → track/insight entry 기록 시점을 비차단으로 상기 (로깅이 아니라 판단 트리거)
```

`init.py --hook`이 `.claude/settings.json`에 세 hook(auditlog · worklog · work-memory-check)을 등록한다. 앞의 둘은 도구 사용 이력과 세션 종료를 자동 누적하고, work-memory-check는 기록할 결정이 쌓였는지 판단해 상기시킨다.

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
| track-record | user-decision | `UD` | 사람이 내린 결정과 승인 |
| track-record | trouble-shooting | `TS` | 문제 해결 과정 |
| insight-record | episodes | `EP` | 주목할 경험과 관찰 |
| insight-record | patterns | `PT` | 반복 패턴과 공통 구조 |
| insight-record | principles | `PR` | 도출된 원칙과 규칙 |

**기록 판단 넛지 (hook)**

자동 기록은 *무엇을 했는지*를 남기지만, track/insight entry를 *언제 남길지*는 판단이 필요하다. 그 판단 트리거가 없으면 수동 기록은 쉽게 누락된다. `hooks/work-memory-check.sh`가 Stop·PreCompact에서 비차단으로 그 판단을 상기시킨다.

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
    └── workflow-00.yaml          ← 기본 workflow
    └── workflow-feature-a.yaml  ← 기능별 workflow
    └── workflow-release.yaml    ← 릴리즈 workflow

# phase 내 sub workflow 참조
phase:
  workflows:
    - ref: "workflow-release.yaml#P02.validation"
      module: "01.core"
```

**Compile-time Topology 제약 (Rail · Checkpoint · Guardrail)**

workflow YAML의 세 가지 노드 타입이 에이전트의 실행 경로를 컴파일 타임에 제약한다.

| 노드 타입 | 역할 | 컴파일 타임 검증 |
|----------|------|-----------------|
| `step` | **Rail** — 실행 경로. phase → step 순서가 directed path를 구성한다 | node id 전역 unique · 의존 관계 |
| `validation` | **Checkpoint** — 통과 기준이 선언된 게이트. `wf_node.py harness-manifest`가 validation 노드만 추출해 CI manifest를 생성한다 | 필수 필드 검증 |
| `decision` | **Guardrail** — `judge` 수준으로 에이전트 자율성 한계를 명시한다. HITL이면 사람 없이 진행 불가 | judge 값 검증 · owner 필수 여부 |

```
wf_node.py validate workflow.yaml
    → rail: phase/step 순서 · node id 전역 unique 검증
    → checkpoint: validation 노드 필수 필드 검증
    → guardrail: decision judge 수준 · owner 필수 여부 검증

wf_node.py harness-manifest workflow.yaml
    → validation 노드만 수집 → ci-manifest.json (CI가 소비하는 checkpoint 목록)
```

---

## 스킬 구성

v0.3.1은 **Design → Ops → Infra → Runtime/NLU** 네 레이어에 걸쳐 8개 스킬이 동작한다.
v0.3.0의 5개 스킬(Design/Ops/Infra) 위에, 오퍼레이터 자연어 발화를 실행 가능한 명령으로 grounding하는 **Utterance Grounding Layer** 3개 스킬이 추가됐다.

```
사용자 요청
    │
    ▼
mso-orchestration          ← 단일 진입점 · 트리거 매칭 · 라우팅
    │
    ├── [Design]
    │   ├──> mso-scaffold-design     index.yaml SSOT · sf_node.py
    │   └──> mso-workflow-design     workflow YAML · wf_node.py · Mermaid 변환
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
| `mso-workflow-design` | Design | `wf_node.py`, `workflow_to_mermaid.py`, `wf_to_ttl.py`·`schemas_to_tbox.py`·`ttl_to_wf.py` (TTL TBox/ABox 검증) |
| `mso-work-memory` | Infra | `wm_node.py`, `hooks/auditlog.py`, `hooks/worklog.py`, `hooks/work-memory-check.sh` |
| `mso-intent-analytics` *(§11)* | Data+Runtime | `src/lookup.py`(registry), `src/pipeline.py`(뒷단 dispatch), `references/schemas/nlu_intent.yaml` (LinkML) |
| `mso-conversation-analytics` *(de-routed)* | Observability | `src/analytics.py` (DuckDB) — UUG 흡수 대기, 직접 호출만 |

> **§11 NLU 경계 재편**: utterance→intent 분류(앞단)는 UUG(`01_user-utterance-grounding`)로 흡수, intent→action(뒷단 slot/dispatch)만 MSO(`mso-intent-analytics`). 구 `mso-utterance-grounding` 해체, `mso-intent-registry`→`mso-intent-analytics` 개명. 7 스킬.

---

## 생성되는 구조

```
project/
├── agent-context/
│   ├── index/
│   │   └── index.yaml              ← scaffold SSOT (mso-scaffold-design)
│   ├── workflow/
│   │   └── workflow-00.yaml        ← workflow SSOT (mso-workflow-design)
│   └── work-memory/
│       ├── schema.yaml             ← entry 스키마 정의
│       ├── auditlog/               ← AU-*.jsonl (hook 자동 기록 — 도구 사용)
│       ├── worklog/                ← WL-*.jsonl (hook 자동 기록 — 세션 종료)
│       ├── track-record/
│       │   ├── issue-note/         ← IN-*.jsonl
│       │   ├── agent-decision/     ← AD-*.jsonl
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

### workflow 정의

```bash
WF=~/.claude/skills/mso-workflow-design/scripts/wf_node.py
python3 $WF scaffold phase --id "P01.discovery"
python3 $WF scaffold decision --id "d-001" --judge HITL
python3 $WF validate agent-context/workflow/workflow-00.yaml
python3 $WF harness-manifest agent-context/workflow/workflow-00.yaml --out ci-manifest.json
```

### work-memory 기록

```bash
export WORKMEM_DIR=./agent-context/work-memory
WM=~/.claude/skills/mso-work-memory/scripts/wm_node.py
python3 $WM new issue-note --title "timeout 누락 발견" --tags "policy,timeout"
python3 $WM stats
python3 $WM graph IN-0001 --depth 2
```

---

## 설계 원칙

**Working System First.** 완벽한 아키텍처보다 실제로 돌아가는 시스템을 먼저 만든다. v0.3.0은 5개 스킬이 실제로 동작하는 것을 검증한 milestone이고, v0.3.1은 그 위에 자연어 발화를 실행 가능한 GroundedCommand로 변환하는 Utterance Grounding Layer 3개 스킬을 더해 8개 스킬 체제로 확장한 milestone이다.

**YAML이 SSOT.** `index.yaml`과 workflow YAML이 정본이다. Markdown·Mermaid는 변환 산출물이지, 편집 대상이 아니다.

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
