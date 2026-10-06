# Multi-Swarm Orchestrator (MSO) v0.13.1

MSO는 **Repository Execution System**이다.

Claude Code, Codex 같은 provider runtime을 대체하지 않는다. 그 위에서 repository 구조, workflow topology, artifact supply chain, work-memory를 선언하고 관측해 에이전트가 같은 작업을 이어갈 수 있는 실행 환경을 만든다.

> **MSO의 eval은 evolve를 위한 것이고, 그 eval과 evolve 또한 하나의 Oracle workflow다.**
> AI 시대의 workflow에는 고정된 phase 가 없다 — 대신 workflow와 Oracle이 순환한다. 산출물을 Oracle이 평가(eval)하고, 그 평가가 workflow 자신을 진화(evolve)시키며, 그 진화를 수행하는 oracle 또한 workflow다. 평가와 진화가 맞물려 도는 이 phase-less 루프, 그 순환 자체가 AI 시대의 phase다.

변경 이력은 [docs/changelog.md](docs/changelog.md)에 정리한다. README에는 현재 버전에서 사용자가 바로 알아야 할 업데이트만 요약한다.

## Current Version Update

> README에는 **현재 버전의 운영 의미**만 남긴다. 이전 버전의 상세 변경은 changelog로 이동한다.

### v0.13.1 (2026-10-06) — v0.7 workflow를 LangGraph로 그대로 컴파일하고, 로컬 AI 서빙 엔진을 고른다

`mso-workflow-optimizer`가 v0.7 Rail/Stream workflow(`wf:Execution`·`wf:Rail`·`wf:Start/End`)를 어댑터 없이 컴파일한다. `hasSubject=human` 노드는 결정 없이는 멈추고,
되돌림 루프는 `loop_limit`에서 멈춘다. 로컬 슬롯은 ollama·vLLM·SGLang·LM Studio·oMLX 중에서 정책(`local_engine`)이나 `--local-engine`으로 고른다.
v0.7 제어 흐름 추출의 정본은 `mso-workflow-design`의 `wf_v07.control_graph`(>=0.13.0)이고 optimizer는 이를 소비한다.
Python 의존성은 `requirements.txt`(+ 선택 `requirements-langgraph.txt`)로 선언하며, venv는 저장소에 두지 않고 `bash install.sh --venv`가 `~/.mso/venv`에 만든다. 상세는 changelog.

### v0.13.0 (2026-10-05) — 여러 저장소를 횡단하며 작업하고, 맥락을 TTL 지식 그래프로 찾는다

작업은 한 저장소에서 끝나지 않는다. 엄브렐러 repo 아래에 서브모듈과 별도 경로의 저장소가 여럿 있고, 한 세션이 그 사이를 오가며 일한다.
그런데 결정, 산출물, 실행 흐름이 저장소마다 따로 기록되면 "이 파일은 어떤 규약으로 어떤 작업에서 만들어졌나", "이 결정은 어떤 이슈에서
나왔나"를 찾을 수 없다. v0.13.0은 **여러 저장소를 횡단하면서 작업할 수 있게** 하고, 이를 위해 작업 맥락을 **TTL 형태의 지식 그래프**로
구조화해 서로 연결하고 질의로 찾을 수 있게 한다.

**여러 저장소를 횡단하는 방식**

| 무엇을 | 어떻게 횡단하나 | 도구 |
|---|---|---|
| 작업 기록(결정, 이슈, 해결, 회고) | 어느 저장소에서 일했든 **그 저장소의** work-memory에 기록하고 커밋한다. 등록부 `linked-repos.yaml`이 서브모듈과 별도 경로를 묶는다 | `wm_node.py --repo/--repo-name`, `commit-work-memory.sh`(autocommit 옵트인) |
| 산출물 규약(어디에 어떤 이름과 형식으로 만드는가) | 프로젝트의 **하나의 registry**(`artifacts.abox.ttl`)가 여러 저장소의 산출물을 정의한다. 디렉토리 템플릿에 저장소 경로가 들어가고 `wf:inModule`로 모듈에 연결한다 | `validate_artifact_layer.py` |
| 실행 흐름(누가 무엇을 소비하고 생산하는가) | workflow `*.abox.ttl` 한 곳의 `wf:Stream`이 여러 저장소의 artifact 개념 IRI를 잇는다 | `artifact-lineage.rq` |
| 기록 누락 점검 | 여러 저장소에 작업 흔적이 있는데 기록이 비어 있는지 한 번에 본다 | `wm_link.py status`, `work-memory-check.sh` |

**TTL 지식 그래프로 맥락을 찾는다.** 작업 기록은 JSONL이 정본이고 관계 그래프(TTL projection)로 투영된다. 산출물 규약과 실행 흐름은 처음부터 TTL이다.
세 층이 같은 어휘(`wf:`, PROV-O 정렬 주석)로 이어지므로 아래 질문에 답할 수 있다.

| 찾고 싶은 맥락 | 어디서 답하나 | 도구 |
|---|---|---|
| 이 결정은 어떤 이슈나 사고에서 나왔나, 어떤 회고로 이어졌나 | work-memory 관계 그래프(`caused-by`, `resolved-by`, `analyzed-in` 등) | `wm_node.py graph <id> --repo-name <이름>` |
| 지금 하는 작업과 관련된 과거 기록은 | work-memory context pack | `wm_context.py node` / `query` |
| 이 파일은 어떤 규약을 따르고 그 규약은 언제 바뀌었나 | artifact 규약 버전과 유효 구간, 파일 규약 스캔 | `validate_artifact_layer.py --scan` |
| 이 artifact는 어떤 실행을 거쳐 만들어졌나 | workflow Stream(소비와 생산) | `references/queries/artifact-lineage.rq` |

**함께 바뀐 것**
- 신규 스킬 `mso-work-memory-link`가 연관 저장소 등록, 자동 커밋 켜기/끄기, 훅 사본 갱신, 점검을 맡는다.
- artifact 층은 개념(안정 IRI)과 규약 버전(이름 규약, 형식, 디렉토리 템플릿, 유효 구간)으로 나뉘고, `consumerType`(Machine / Hybrid / Human), 템플릿 변수,
  메타데이터 스키마, 규약 불변(git HEAD 비교)을 SHACL/SPARQL로 검증한다. YAML 레지스트리는 두지 않는다.
- PROV-O 정렬은 TBox 주석으로 확장했다(D-23a). 공리로 단언하거나 `prov:`를 import하지 않는다.
- `sf_node.py` 등 8개 스크립트가 python 3.9에서 `X | None` 문법으로 죽어 scaffold-check 훅이 조용히 실패하던 문제를 고쳤다.

**현재 범위.** 기록, 커밋, 점검, 산출물 규약, 실행 흐름은 여러 저장소를 가로질러 한 세션에서 다룬다. 다만 work-memory 자체의 **그래프 조회와 검색은 저장소 단위**다
(`--repo-name`으로 저장소를 골라 한 번에 한 저장소씩). 여러 저장소의 work-memory를 하나의 그래프로 합쳐 한 번에 질의하는 기능은 아직 없다.
디렉토리 층(`index.yaml`)과 artifact 층의 연결(`wf:inModule`)도 임시 문자열이다. 자세한 한계는 [changelog](docs/changelog.md)의 Known Gaps에 있다.

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

MSO repository에는 다음 그래프가 함께 존재한다 (v0.7.0 Repository Graph).

| Graph | 역할 | 대표 산출물 |
|---|---|---|
| Execution Rail (Control Plane) | Execution 간 실행·분기·주체 전환(`wf:Rail`)을 정의한다. | `workflow/*.abox.ttl`, `observability/graph/<scope>/execution-rail.md` |
| Artifact Stream Graph (Data Plane) | Artifact의 소비·생산·근거 계보(`wf:Stream`)를 정의한다. | `observability/graph/<scope>/artifact-stream-graph.md`, `observability/artifact-stream-report.md` |
| Knowledge Graph | artifact 안에 저장되는 의미와 관계를 정의한다. | ontology TTL, SHACL, work-memory projection |

Execution Rail + Artifact Stream Graph = **Repository Graph** 이며, 여기에 Semantic 계층(RDF→RDFS→OWL→SHACL)이 의미와 제약을, Trust/Provenance 계층이 신뢰도 계산을 얹는다.

## Artifact Types

| Type | Examples | Primary Consumer | Purpose |
|---|---|---|---|
| `knowledge_store` | `ontology.ttl`, `workflow.ttl`, SHACL, JSON Schema | Agent | 구조화된 지식과 관계를 저장하고 추론한다. |
| `event_store` | `work-memory.jsonl`, auditlog, worklog | Agent | 실행 기록과 이벤트를 누적한다. |
| `local_database` | `cache.sqlite`, DuckDB cache | Agent | 빠른 조회와 질의를 제공한다. |
| `document` | `README.md`, `report.md`, `prompt.md` | Human + Agent | 사람과 에이전트가 함께 읽고 수정하는 협업 인터페이스다. |
| `media` | `html`, `pdf`, `pptx`, `png`, `svg` | Human | 외부 전달을 위한 human-native deliverable이다. |
| `table` | `csv`, `tsv`, `xlsx` | Human + Agent | 사람도 열어 보는 표 형태 데이터다. |
| `tool` | `py`, `sh` 스크립트 | Agent | 에이전트가 실행하는 도구다. |

v0.13.0부터 artifact는 TTL registry에서 **개념(안정 IRI)과 규약 버전**으로 정의하고, 개별 artifact마다 소비자 유형
`consumerType`(Machine / Hybrid / Human)을 선언한다. 위 표의 Primary Consumer는 유형의 기본값이다. 자세한 모델은
[docs/artifact-model.md](docs/artifact-model.md)를 본다.

## What MSO Provides

| 문제 | MSO의 답 | 주요 파일 |
|---|---|---|
| 구조 없음 | repository index와 artifact registry | `index.yaml`, `agent-context/index/index.yaml` |
| 절차 없음 | TTL workflow topology | `agent-context/workflow/*.abox.ttl` |
| 소비 관계 불명확 | artifact stream observability | `agent-context/observability/` (리포트) + `observability/graph/` (시각화) |
| 결정/품질 판단 혼재 | decision/eval gate 분리 | workflow TTL, SHACL |
| 신뢰 근거 없음 | provenance + trust 계산 (저장 아님) | `trust_v07.py`, `observability/trust-report.md` |
| 기억 없음 | work-memory JSONL + graph projection | `agent-context/work-memory/` |

## Skills

v0.5.0 기준 MSO는 다음 스킬을 중심으로 동작한다.

| Skill | 역할 |
|---|---|
| `mso-orchestration` | 사용자 요청을 MSO 하위 스킬로 라우팅한다. |
| `mso-repository-setup` | 새 repository에 `agent-context/` 구조와 hook을 부트스트랩한다. |
| `mso-scaffold-design` | repository index와 artifact registry를 관리한다. |
| `mso-workflow-design` | TTL workflow/artifact/eval node-edge shape와 migration tooling을 관리한다. |
| `mso-work-memory` | 작업 기억 JSONL, graph projection, validation을 관리한다. 연관 저장소(`--repo`) 기록·커밋을 지원한다. |
| `mso-work-memory-link` | 연관 저장소 work-memory 등록·점검(status/add/autocommit/sync-hooks/verify). |
| `mso-graph-observability` | workflow, artifact stream, eval edge, runtime graph를 관측하고 개선 리포트를 만든다. |
| `mso-workflow-observation` | workflow observation alias. `mso-graph-observability`의 workflow scope를 호출해 `execution-rail.md`, `artifact-stream-graph.md`, `repository-graph.md`를 생성한다. |
| `mso-workflow-optimizer` | TTL workflow를 실행 가능한 graph artifact로 컴파일하는 방향을 담당한다. |
| `mso-intent-analytics` | UUG가 제공한 intent를 MSO action으로 dispatch하고 분석한다. |
| `mso-conversation-analytics` | de-routed 레거시 기능이다. 사용자/turn 패턴 분석은 UUG `uug-pattern-analytics` 흡수 대상이고, MSO runtime tier 신호는 `mso-intent-analytics`가 받는다. |

## Generated Structure

새 repository에 MSO를 적용하면 보통 다음 구조가 생긴다.

```text
agent-context/
├── index/
│   ├── index.yaml                  # 디렉토리 층 SSOT
│   └── artifacts.abox.ttl          # artifact 층 SSOT (v0.13.0, 선택)
├── workflow/
│   └── *.abox.ttl
├── observability/
│   └── graph/
│       ├── README.md
│       ├── workflow-subgraph-index.md
│       ├── <workflow-scope>/
│       │   ├── repository-graph.md
│       │   ├── execution-rail.md
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
    ├── insight-record/
    └── linked-repos.yaml           # 연관 저장소 등록부 (v0.13.0, 선택)
```

## Quick Start

### Install

```bash
./install.sh --codex
```

### Initialize A Repository

```bash
python3 skills/mso-repository-setup/scripts/init.py --hook . --provider codex \
  --worthy-paths "agent-context .mso .codex .gitmodules AGENTS.md README.md"
```

Claude Code hook을 만들 때는 `--provider claude`를 사용한다. Antigravity hook을 만들
때는 `--provider antigravity`를 사용한다 (`.agents/hooks.json` 등록, 상세는
[docs/getting-started.md](docs/getting-started.md)).

### Validate Scaffold

```bash
python3 skills/mso-scaffold-design/scripts/sf_node.py validate .
```

### Generate Graph Observability

```bash
python3 skills/mso-graph-observability/scripts/observe_graph.py --root .
```

### Expose Workflow Observation

```bash
python3 skills/mso-workflow-observation/scripts/mso-workflow-observation.py --root .
```

### Validate / Materialize / Trust (v0.7)

```bash
# TTL ABox(SSOT) 직접 검증 — v0.6/v0.7 자동 감지
python3 skills/mso-workflow-design/scripts/validate_abox.py agent-context/workflow

# property chain 파생 (consumed_by ∘ produces_to = evidence_of) → .inferred.ttl
python3 skills/mso-workflow-design/scripts/materialize_v07.py agent-context/workflow

# Trust 계산 + Oracle Decision 제안 (계산 전용 — TTL 비저장)
python3 skills/mso-workflow-design/scripts/trust_v07.py agent-context/workflow \
  --report agent-context/observability/trust-report.md
```

v0.6 ABox는 v0.7로 마이그레이션한다 (sibling `.v07.abox.ttl` 생성 후 검토·교체):

```bash
python3 skills/mso-workflow-design/scripts/migrate_abox_v06_to_v07.py agent-context/workflow
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

### Link Related Repositories (v0.13.0)

엄브렐러 repo 루트에서 연 세션도 하위·별도 경로 MSO 저장소의 work-memory에 기록하고 커밋한다.

```bash
LINK=skills/mso-work-memory-link/scripts/wm_link.py
python3 $LINK status                      # 등록·발견된 저장소, autocommit, 훅 사본 일치, git 건강
python3 $LINK add mso ~/path/to/mso --autocommit
python3 $LINK autocommit child-repo on
python3 $LINK sync-hooks                  # 훅 사본 vs 스킬 최신판 비교(기본 dry-run, --apply 로 교체)
python3 $LINK verify

# 연관 저장소에 기록
python3 skills/mso-work-memory/scripts/wm_node.py new agent-decision --title "..." --repo-name child-repo
```

서브모듈 중 work-memory가 있는 곳은 자동 발견되며 자동 커밋은 꺼져 있다. 켜려면 `autocommit on`으로 등록부에 항목을 만든다.
push는 하지 않고 서브모듈 포인터도 건드리지 않는다.

### Validate The Artifact Layer (v0.13.0)

```bash
# artifact registry(TTL)와 workflow Stream을 SHACL/SPARQL로 검증하고, 실제 파일이 규약에 맞는지 스캔한다
python3 skills/mso-workflow-design/scripts/validate_artifact_layer.py --root . --scan [--json out.json]

# workflow의 경로·locator 참조가 index와 registry에 매핑되는지 점검
python3 skills/mso-scaffold-design/scripts/check_artifact_index.py --root . [--suggest]

# 변형 파일의 계보: registry + workflow ABox에 artifact-lineage.rq 를 실행한다
# (skills/mso-workflow-design/references/queries/artifact-lineage.rq)
```

## Design Principles

**Provider Free.** MSO는 Claude Code, Codex, Antigravity 등 provider runtime 위에서 동작하지만 특정 provider에 종속되지 않는다.

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

시험은 python 3.11 이상 환경을 권장한다(일부 시험이 `tomllib`을 쓰고 SHACL 시험은 `pyshacl`이 필요하다). 스크립트 자체는 python 3.9에서도 동작한다.

## References

- [docs/artifact-model.md](docs/artifact-model.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/getting-started.md](docs/getting-started.md)
- [docs/changelog.md](docs/changelog.md)
- [skills/mso-graph-observability/SKILL.md](skills/mso-graph-observability/SKILL.md)
- [skills/mso-workflow-design/SKILL.md](skills/mso-workflow-design/SKILL.md)
- [skills/mso-work-memory/SKILL.md](skills/mso-work-memory/SKILL.md)
- [skills/mso-work-memory-link/SKILL.md](skills/mso-work-memory-link/SKILL.md)
- [skills/mso-scaffold-design/SKILL.md](skills/mso-scaffold-design/SKILL.md)
