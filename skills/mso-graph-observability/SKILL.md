---
name: mso-graph-observability
version: "0.4.3"
description: "MSO의 여러 운영 그래프를 관측한다. workflow TTL/ABox는 Mermaid Markdown topology/class/property view로 시각화하고, work-memory/auditlog/worklog/intent turn graph는 실패 흐름, 반복 실행, 이상 행동, 병목 패턴을 분석하는 관측 레이어로 확장한다."
---

# MSO Graph Observability

MSO의 **그래프 관측 레이어**다. `mso-workflow-design`이 workflow TTL ABox를 설계 원본으로 관리하고 `mso-work-memory`가 작업 기억과 로그를 축적한다면, 이 스킬은 그 그래프들을 읽어 사람이 운영 상태를 빠르게 파악할 수 있는 관측 산출물을 만든다.

Trigger phrases: graph observability, 그래프 관측, mso graph, workflow observability, 워크플로우 관측, workflow 시각화, work-memory 분석, auditlog 분석, 이상행동 관측, 실패 흐름 분석, workflow 실행 빈도, TTL graph, Mermaid view, ontology view, workflow topology.

원칙:

- 원본 그래프가 SSOT다. 관측 Markdown/metrics는 파생 산출물이므로 직접 편집하지 않는다.
- workflow topology 입력은 TTL ABox뿐이다. YAML은 legacy migration 입력일 뿐 Mermaid topology 생성 입력으로 쓰지 않는다.
- 관측 결과는 기본적으로 `agent-context/observability/graph/` 아래에 둔다.
- 시각적으로 보는 1차 대상은 workflow graph다.
- workflow별 sub-graph에서는 `wf:directory`/`wf:deliverables`를 Data node로 파생해 `task --produces--> data --consumes--> task` 데이터 흐름을 함께 보여준다.
- Data node는 `data_type`과 `location`을 가진 관측 노드다. 현재 TTL에서는 `wf:directory`를 `data_type=local_file`, `location=<dirPath>`로 해석하며, 이후 API endpoint나 MCP resource도 같은 Data node 계층으로 확장할 수 있다.
- work-memory, auditlog, worklog, intent turns는 별도 분석 리포트로 다룬다.
- 분석 목적은 “어떤 흐름에서 실패가 많았는가”, “어떤 workflow가 자주 실행되는가”, “에이전트가 어디서 반복/이탈/재시도하는가”를 드러내는 것이다.

## Graph Scopes

| Scope | Source | Output | Status |
|---|---|---|---|
| `workflow` | `agent-context/workflow/**/*.ttl`, workflow TBox | Mermaid topology/class/property views | implemented |
| `memory` | `agent-context/work-memory/**/*.jsonl`, relations graph | 실패/결정/해결 패턴 분석 | baseline implemented |
| `audit` | `agent-context/work-memory/auditlog/**/*.jsonl` | tool/event 이상행동, retry, blocked 흐름 분석 | baseline implemented |
| `worklog` | `agent-context/work-memory/worklog/**/*.jsonl` | 실행 빈도, 반복 workflow, 작업량 추세 분석 | baseline implemented |
| `intent` | `.mso-context/conversation/turns.jsonl` | utterance→intent 전환, reprompt, dispatch 실패 분석 | baseline implemented |

## Use Cases

- workflow phase/module dependency를 한 화면에서 확인한다.
- HITL/Validation/Step/Decision/Group 등의 노드 계층을 시각적으로 점검한다.
- workflow TBox의 property domain/range를 확인해 TTL 작성/리뷰 시 참조한다.
- 새 repo에 MSO를 붙인 뒤 `agent-context/workflow/*.ttl`의 현 상태를 리뷰 가능한 문서로 내보낸다.
- 특정 workflow 또는 phase에서 실패가 반복되는지 확인한다.
- 특정 에이전트/도구 호출이 같은 흐름에서 과도하게 재시도되는지 확인한다.
- 어떤 workflow가 많이 돌고, 어떤 흐름이 실행되지 않는지 운영 관점으로 본다.

## Inputs

현재 구현된 `workflow` scope 기본 입력:

- `agent-context/workflow/**/*.ttl`
- MSO 기본 workflow TBox: `skills/mso-workflow-design/references/tbox/workflow-tbox.ttl`

추가 TTL이 있으면 `--ontology`를 반복 지정한다.

## Outputs

기본 출력 디렉토리:

```bash
agent-context/observability/graph/
```

`workflow` scope 생성 파일:

- `README.md` — 생성 결과 인덱스
- `workflow-topology.md` — repository 전체 Phase, Module, Milestone 중심 topology graph
- `workflow-subgraph-index.md` — workflow scope별 sub-graph 인덱스
- `workflow-subgraphs/<workflow-scope>.md` — 특정 workflow 하나만 보는 Mermaid sub-graph. phase/node/process edge와 함께 Data node 기반 input/output 흐름을 표시
- `workflow-ssot-report.md` — legacy workflow YAML 대비 sibling `*.abox.ttl` 누락 여부. YAML-only workflow는 관측에서 제외됨을 경고
- `class-layer-map.md` — workflow ontology class hierarchy
- `property-map.md` — workflow ontology property domain/range map
- `runtime-analysis.md` — work-memory/auditlog/worklog/intent turn JSONL 기반 실패 hotspot, 실행 빈도, 반복 신호

## CLI

프로젝트 루트에서 실행한다.

```bash
python skills/mso-graph-observability/scripts/observe_graph.py --root .
```

예제 TTL만 대상으로 테스트할 때:

```bash
python skills/mso-graph-observability/scripts/observe_graph.py \
  --workflow-dir skills/mso-workflow-design/assets/examples \
  --output-dir /tmp/mso-graph-observability
```

추가 ontology/TBox를 포함할 때:

```bash
python skills/mso-graph-observability/scripts/observe_graph.py \
  --root . \
  --ontology path/to/extra.ttl
```

## Workflow

1. `agent-context/workflow/`에 workflow TTL ABox가 있는지 확인한다.
2. legacy YAML이 남아 있으면 `mso-workflow-design`의 migration script로 TTL ABox를 먼저 만든다.
3. 본 스킬의 CLI를 실행해 graph observability Markdown을 재생성한다.
4. 생성된 Mermaid 뷰에서 dependency 방향, phase 상태, node 연결 누락을 리뷰한다.
5. 문제를 발견하면 Markdown이 아니라 TTL 원본을 수정한 뒤 다시 생성한다.
6. `workflow-ssot-report.md`에 YAML-only workflow가 나오면 `mso-workflow-design`의 `migrate_workflows_to_ttl.py`로 sibling `.abox.ttl`을 먼저 만든다.

## Extension Direction

`memory`, `audit`, `worklog`, `intent` scope는 workflow처럼 복잡한 관계 구조를 시각화하는 대신 다음 리포트를 우선한다.

- failure hotspot: 실패/blocked/retry가 특정 workflow, phase, node, tool에 집중되는지
- repeated loop: 같은 ticket/run/intent가 반복 실행되는지
- abnormal agent behavior: 동일 파일/명령/도구를 짧은 시간에 반복하거나, validation 없이 destructive action에 접근하는지
- workflow usage: 자주 실행된 workflow, 실행되지 않는 workflow, 완료까지 오래 걸리는 workflow
- memory coverage: issue-note가 trouble-shooting으로 해결됐는지, AD/UD/TS/EP 연결이 누락됐는지

## Notes

- `wf:dependsOn`과 `wf:criticalDep`은 dependency 의미를 살려 `dependency target --> dependent` 방향으로 표현한다.
- `wf:hasNode`, `wf:hasWorkflowRef`, `wf:hasBranch`는 workflow별 sub-graph에서만 내부 구조 관계로 표현한다.
- `wf:next`와 `wf:gotoNode`는 repository 전체 topology에서는 숨기고, workflow별 sub-graph에서 phase 내부 실행 흐름과 조건부 feedback loop로 표현한다.
- `wf:directory`는 Data node로 파생한다. 현재는 `data_type=local_file`, `location=dirPath`로 표시한다. `role: output`은 `produces`, `role: input/reference`는 `consumes`, `role: input_output`은 양방향 edge로 표현한다.
- `wf:deliverables`는 output-only Data node로 표시한다. 현재는 `data_type=local_file`, `location=declared deliverable`, `detail=<deliverable>`로 렌더링하고 `declares` edge로 연결한다. 이후 schema가 확장되면 `data_type=api`/`mcp`/`database` 등으로 같은 표현을 재사용한다.
- 전체 repository graph는 `workflow-topology.md`에 생성하고, workflow scope별 sub-graph는 `workflow-subgraphs/`에 분리한다.
- sub-graph 분리는 scoped URI(`phase/<workflow>/<phase>`, `node/<workflow>/<node>`)를 기준으로 한다. unscoped legacy TTL은 repository graph에는 보이지만 workflow별 sub-graph에는 포함되지 않는다.
- 대규모 ontology에서는 `property-map.md`가 커질 수 있으므로 CLI 내부에서 보기 좋은 상한을 둔다.
- YAML-only workflow가 있을 때 exporter는 fallback하지 않는다. 관측 그래프에 없는 workflow는 SSOT drift로 보고 TTL 마이그레이션을 먼저 요구한다.
