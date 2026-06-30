# Multi-Swarm Orchestrator (MSO) v0.6.4

MSO는 **Repository Execution System**이다.

Claude Code, Codex 같은 provider runtime을 대체하지 않는다. 그 위에서 repository 구조, workflow topology, artifact supply chain, work-memory를 선언하고 관측해 에이전트가 같은 작업을 이어갈 수 있는 실행 환경을 만든다.

> **MSO의 eval은 evolve를 위한 것이고, 그 eval과 evolve 또한 하나의 Oracle workflow다.**
> AI 시대의 workflow에는 고정된 phase 가 없다 — 대신 workflow와 Oracle이 순환한다. 산출물을 Oracle이 평가(eval)하고, 그 평가가 workflow 자신을 진화(evolve)시키며, 그 진화를 수행하는 oracle 또한 workflow다. 평가와 진화가 맞물려 도는 이 phase-less 루프, 그 순환 자체가 AI 시대의 phase다.

변경 이력은 [docs/changelog.md](docs/changelog.md)에 정리한다. README에는 현재 버전에서 사용자가 바로 알아야 할 업데이트만 요약한다.

## Current Version Update

> README에는 **현재 버전의 운영 의미**만 남긴다. 이전 버전의 상세 변경은 changelog로 이동한다.

### v0.6.4 (2026-07-01) — Decision/Validation loop gates

Workflow topology에서 `Eval`, `Decision`, `Validation`의 역할을 다시 분리했다. Eval은 산출물 품질/정합성 평가와 evolve 루프를 위한 gate이고, 결정적 검증이나 사람 승인/반려 루프는 Decision gate로 표현한다.

- **Eval gate**: `target`, `targetArtifact`, fail/pass branch, downstream `evolves` 흐름을 강제한다.
- **Validation decision gate**: TTL ABox에서 `wf:Decision + wf:Validation`으로 표현할 수 있으며, deterministic process/state 검증 루프의 제어점으로 인정한다.
- **User decision gate**: `decisionSubject="user"`인 승인/반려 루프도 통제된 HITL 루프로 인정한다.
- **Regression guard**: agent Decision만 있는 재귀 루프는 여전히 uncontrolled loop로 실패한다.

### v0.6.3 (2026-06-30) — Stop reminder throttle

Stop hook이 매 턴 사용자에게 같은 안내를 반복하는 문제를 줄이기 위해 `stop-check.sh` 상태 관리기를 추가했다. 첫 Stop에서는 reminder를 출력하고 `.claude/state/stop-check.state`를 남기며, 바로 다음 Stop에서는 조용히 종료하고 state를 지운다.

- **적용 범위**: 사용자에게 보이는 Stop reminder 출력만 억제한다.
- **비적용 범위**: `commit-work-memory.sh`는 계속 실행한다. work-memory 변경분 커밋 백스톱을 억제하지 않는다.
- **로컬 상태**: `.claude/state/`는 gitignore 대상이다.

### v0.6.2 (2026-06-30) — Worklog semantic boundary + cloud hand-off

`worklog` 의미를 Stop hook 자동 세션 로그가 아니라 **workflow TTL `node -> node` 실행 기록**으로 고정했다. `auditlog`는 도구 실행 사실, `worklog`는 workflow 레일을 따라 수행한 작업, `AD/IN/TS`는 레일 밖 판단과 예외 기록을 담당한다.

- **worklog 경계**: workflow node를 명시할 수 있을 때만 `worklog`를 작성한다. node 맥락이 없으면 `AD` 또는 `IN/TS` 후보로 기록하고 workflow TTL 갱신 후보로 환류한다.
- **hook 정책**: Stop/PreCompact는 `commit-work-memory.sh`만 수행한다. Stop hook은 worklog를 자동 생성하지 않는다. `work-memory-check`는 SessionStart(compact/resume)에서 기록 판단을 상기시킨다.
- **cloud hand-off**: Codex cloud 같은 ephemeral 환경에서는 hook side effect를 다음 에이전트 기억 보장으로 보지 않는다. cloud hand-off는 최종 답변, diff, 커밋 가능한 tracked file에 남는 기록을 기준으로 한다.
- **version ladder**: v0.6.1은 phase-less workflow 모델 구현 완료 패치다. v0.6.2는 work-memory/hook/cloud hand-off 운영 의미 정리 패치고, v0.6.3은 Stop reminder 출력 throttle 패치, v0.6.4는 Decision/Validation loop gate 정합화 패치다.

상세 변경은 [docs/changelog.md](docs/changelog.md)의 v0.6.4 항목을 본다.

## Core Philosophy

### Repository First

MSO의 실행 단위는 채팅 세션이 아니라 repository다. 에이전트는 매번 처음부터 탐색하는 대신, repository 안에 선언된 index, workflow, memory, ontology를 읽고 현재 작업의 위치를 파악한다.

### Workflow Before Directory

디렉토리를 먼저 만들고 그 안에 작업을 끼워 넣지 않는다. 먼저 workflow topology를 보고 어떤 task가 어떤 artifact를 생산하고 소비하는지 확인한다. 디렉토리는 그 artifact 흐름을 지원할 때만 유지한다.

소비자가 없는 artifact가 많다면, 디렉토리도 줄이거나 합쳐야 한다.

### Artifact Supply Chain

MSO는 Data Pipeline이 아니라 **Artifact Supply Chain**을 관리한다.

파일도 데이터의 한 형태지만 workflow는 데이터를 직접 소비하지 않는다. 에이전트는 repository 안의 Artifact를 읽고, 내부 표현을 Data로 파싱하거나 질의하고, 의미를 Knowledge로 해석한 뒤, 다시 새로운 Artifact로 직렬화한다.

```text
Artifact
  -> Read
Data
  -> Parse / Query / Reasoning
Knowledge
  -> Serialize
Artifact
```

Artifact stream review의 핵심 질문은 하나다.

> 이 Artifact를 소비하는 Agent, User, eval, handoff, 또는 delivery 경로가 workflow 안에 있는가?

Markdown document에 소비자가 없으면 생략한다. 장기 조회, 추론, 재사용이 목적이면 Markdown을 계속 늘리지 않고 JSONL, TTL/schema, SQLite 같은 machine-native Artifact로 구조화한다.

상세 모델은 [docs/artifact-model.md](docs/artifact-model.md)를 본다.

### Decision And Eval Separation

Decision gate와 Eval gate는 다르다.

Decision은 workflow의 진행과 분기를 제어한다. Eval은 산출물의 품질, 정합성, 수용 가능성을 평가한다. `oracle`은 Eval을 수행하는 주체 또는 권위 필드다. 순환 workflow 자체는 허용하지만, 산출물이 재귀적으로 소비되는 feedback loop에는 별도 Eval gate가 있어야 한다.

### TTL As Workflow SSOT

workflow topology의 정본은 TTL ABox다. YAML은 신규 작성 대상이 아니라 legacy migration input으로만 남긴다.

Mermaid Markdown, report, runtime analysis는 모두 파생 산출물이다. 관측 결과를 직접 고치지 않고 TTL 원본을 수정한 뒤 다시 생성한다.

### Work Memory As Operational Memory

MSO는 실행 기록을 단순 로그로만 보지 않는다. auditlog와 worklog는 자동으로 쌓고, 중요한 결정과 이슈는 `agent-decision`, `user-decision`, `issue-note`, `trouble-shooting`, `episode`, `pattern`, `principle`로 구조화한다.

작업 기억은 다음 세션의 context가 되고, 반복 실패와 구조적 drift를 발견하는 관측 입력이 된다.

## Repository Topology

MSO repository workflow를 설계할 때는 세 관점을 동시에 본다.

| Design Lens | 질문 | Shape Slot |
|---|---|---|
| Agentic Workflow | 어떤 agentic task가 어떤 순서와 조건으로 실행되는가? | step, decision, validation, next/branch edge |
| Artifact Supply Chain | 어떤 artifact가 생산되고, 누가 소비하며, 어디에 저장되는가? | directory, deliverable, artifact type, consumes/produces edge |
| Eval Gate | 어떤 산출물을 누가 어떤 기준으로 평가하고, 결과가 어떤 step과 report로 이어지는가? | eval, targetArtifact, orderTarget, orderArtifact, criteria |

이 세 관점은 graph shape requirements이며, workflow-design 대화에서는 이를 slot으로 본다. 비어 있는 slot이 있으면 에이전트는 바로 TTL을 채우기보다 필요한 질문을 던져 slot-filling을 유도하고, 충분히 채워진 뒤 안정적인 repository workflow topology로 기록한다.

MSO repository에는 세 그래프가 함께 존재한다.

| Graph | 역할 | 대표 산출물 |
|---|---|---|
| Task Graph | task 간 실행 관계를 정의한다. | `workflow/*.abox.ttl`, `workflow-views/` |
| Artifact Graph | artifact의 생성과 소비 관계를 정의한다. | `artifact-stream-views/`, `artifact-stream-report.md` |
| Knowledge Graph | artifact 안에 저장되는 의미와 관계를 정의한다. | ontology TTL, SHACL, work-memory projection |

이 세 그래프가 합쳐져 repository workflow topology를 이룬다.

## Artifact Types

| Type | Examples | Primary Consumer | Purpose |
|---|---|---|---|
| `knowledge_store` | `ontology.ttl`, `workflow.ttl`, SHACL, JSON Schema | Agent | 구조화된 지식과 관계를 저장하고 추론한다. |
| `event_store` | `work-memory.jsonl`, auditlog, worklog | Agent | 실행 기록과 이벤트를 누적한다. |
| `local_database` | `cache.sqlite`, DuckDB cache | Agent | 빠른 조회와 질의를 제공한다. |
| `document` | `README.md`, `report.md`, `prompt.md` | Human + Agent | 사람과 에이전트가 함께 읽고 수정하는 협업 인터페이스다. |
| `media` | `html`, `pdf`, `pptx`, `png`, `svg` | Human | 외부 전달을 위한 human-native deliverable이다. |

## What MSO Provides

| 문제 | MSO의 답 | 주요 파일 |
|---|---|---|
| 구조 없음 | repository index와 artifact registry | `index.yaml`, `agent-context/index/index.yaml` |
| 절차 없음 | TTL workflow topology | `agent-context/workflow/*.abox.ttl` |
| 소비 관계 불명확 | artifact stream observability | `agent-context/observability/graph/` |
| 결정/품질 판단 혼재 | decision/eval gate 분리 | workflow TTL, SHACL |
| 기억 없음 | work-memory JSONL + graph projection | `agent-context/work-memory/` |

## Skills

v0.5.0 기준 MSO는 다음 스킬을 중심으로 동작한다.

| Skill | 역할 |
|---|---|
| `mso-orchestration` | 사용자 요청을 MSO 하위 스킬로 라우팅한다. |
| `mso-repository-setup` | 새 repository에 `agent-context/` 구조와 hook을 부트스트랩한다. |
| `mso-scaffold-design` | repository index와 artifact registry를 관리한다. |
| `mso-workflow-design` | TTL workflow/artifact/eval node-edge shape와 migration tooling을 관리한다. |
| `mso-work-memory` | 작업 기억 JSONL, graph projection, validation을 관리한다. |
| `mso-graph-observability` | workflow, artifact stream, eval edge, runtime graph를 관측하고 개선 리포트를 만든다. |
| `mso-workflow-optimizer` | TTL workflow를 실행 가능한 graph artifact로 컴파일하는 방향을 담당한다. |
| `mso-intent-analytics` | UUG가 제공한 intent를 MSO action으로 dispatch하고 분석한다. |
| `mso-conversation-analytics` | de-routed 레거시 기능이다. 사용자/turn 패턴 분석은 UUG `uug-pattern-analytics` 흡수 대상이고, MSO runtime tier 신호는 `mso-intent-analytics`가 받는다. |

## Generated Structure

새 repository에 MSO를 적용하면 보통 다음 구조가 생긴다.

```text
agent-context/
├── index/
│   └── index.yaml
├── workflow/
│   └── *.abox.ttl
├── observability/
│   └── graph/
│       ├── README.md
│       ├── workflow-subgraph-index.md
│       ├── <workflow-scope>/
│       │   ├── repository-graph.md
│       │   ├── workflow-graph.md
│       │   └── artifact-stream-graph.md
│       ├── artifact-stream-report.md
│       ├── workflow-ssot-report.md
│       ├── class-layer-map.md
│       ├── property-map.md
│       └── runtime-analysis.md
└── work-memory/
    ├── schema.yaml
    ├── auditlog/
    ├── worklog/
    ├── track-record/
    └── insight-record/
```

## Quick Start

### Install

```bash
./install.sh
```

### Initialize A Repository

```bash
python3 skills/mso-repository-setup/scripts/init.py --hook . --provider codex \
  --worthy-paths "agent-context .codex .claude .gitmodules README.md"
```

Claude Code hook을 만들 때는 `--provider claude`를 사용한다.

### Validate Scaffold

```bash
python3 skills/mso-scaffold-design/scripts/sf_node.py validate .
```

### Generate Graph Observability

```bash
python3 skills/mso-graph-observability/scripts/observe_graph.py --root .
```

legacy workflow YAML이 남아 있는 repository에서만 TTL migration을 실행한다. TTL 검증이 끝난 뒤 legacy YAML은 제거한다.

```bash
python3 skills/mso-workflow-design/scripts/migrate_workflows_to_ttl.py agent-context/workflow
```

### Record Work Memory

```bash
python3 skills/mso-work-memory/scripts/wm_node.py new user-decision \
  --title "Artifact consumers determine repository boundaries" \
  --tags artifact-stream,consumer-fit

python3 skills/mso-work-memory/scripts/wm_node.py validate agent-context/work-memory
```

## Design Principles

**Provider Free.** MSO는 Claude Code, Codex 등 provider runtime 위에서 동작하지만 특정 provider에 종속되지 않는다.

**SSOT First.** index, workflow TTL, work-memory JSONL처럼 수정 가능한 원본과 Mermaid/report 같은 파생 산출물을 분리한다.

**Observable Before Automated.** 자동화보다 먼저 관측 가능해야 한다. workflow topology, artifact stream, runtime memory가 보이지 않으면 자동화는 drift를 키운다.

**Consumer Fit Over File Count.** 파일을 많이 만드는 것이 생산성이 아니다. 각 artifact가 적합한 소비자를 갖는지 확인하고, 없으면 생략하거나 더 적합한 machine-native artifact로 바꾼다.

**Working System First.** 완벽한 아키텍처보다 실제로 돌아가는 시스템을 먼저 만든다. 원칙은 실행과 관측을 통해 다듬는다.

## Dependencies

```text
python>=3.10
pyyaml>=6.0
rdflib>=7.0
pyshacl>=0.31
```

## References

- [docs/artifact-model.md](docs/artifact-model.md)
- [docs/changelog.md](docs/changelog.md)
- [skills/mso-graph-observability/SKILL.md](skills/mso-graph-observability/SKILL.md)
- [skills/mso-workflow-design/SKILL.md](skills/mso-workflow-design/SKILL.md)
- [skills/mso-work-memory/SKILL.md](skills/mso-work-memory/SKILL.md)
