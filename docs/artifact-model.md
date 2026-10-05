# MSO Artifact Model

MSO는 Data Pipeline이 아니라 Repository Artifact Supply Chain을 관리한다.

파일도 데이터의 한 형태이지만 workflow는 데이터를 직접 소비하지 않는다. Agent는 repository 안의 Artifact를 읽고, 내부 표현을 Data로 파싱하거나 질의하고, 의미를 Knowledge로 해석한 뒤, 다시 새로운 Artifact로 직렬화한다.

```text
Artifact
  -> Read
Data
  -> Parse / Query / Reasoning
Knowledge
  -> Serialize
Artifact
```

- Artifact: repository에서 관리되는 소비/전달 단위
- Data: Artifact 내부의 표현 방식
- Knowledge: Data가 해석되었을 때 얻어지는 의미 계층

## Artifact Types

| Artifact Type | Examples | Primary Consumer | Primary Purpose |
|---|---|---|---|
| `knowledge_store` | `ontology.ttl`, `workflow.ttl`, SHACL, JSON Schema | Agent | 구조화된 지식과 관계를 저장하고 추론한다. |
| `event_store` | `work-memory.jsonl`, auditlog, worklog | Agent | 실행 기록과 이벤트를 누적해 work memory를 구성한다. |
| `local_database` | `cache.sqlite`, DuckDB cache | Agent | 빠른 조회와 질의를 제공한다. |
| `document` | `README.md`, `report.md`, `prompt.md` | Human + Agent | 사람이 읽고 수정하며 Agent context로도 활용한다. |
| `media` | `html`, `pdf`, `pptx`, `png`, `svg` | Human | repository 밖으로 전달되는 human-native deliverable이다. |
| `table` | `csv`, `tsv`, `xlsx` | Human + Agent | 사람도 열어 보는 표 형태 데이터다. |
| `tool` | `py`, `sh` | Agent | 에이전트가 실행하는 도구다. |

## Consumption Modes

Machine-native Artifact는 Agent가 직접 해석하고 실행하는 Artifact다. Knowledge Store, Event Store, Local Database가 여기에 속하며 RDF triple, SQL query, event replay, semantic search, SHACL validation 같은 연산 대상이 된다.

Hybrid Artifact는 사람과 Agent가 함께 사용하는 협업 인터페이스다. Markdown 문서와 prompt 문서는 사람이 수정할 수 있고 Agent는 context, reference, prompt로 사용할 수 있다.

Human-native Artifact는 사람이 소비하기 위해 생성된다. HTML, PDF, PPTX, PNG, SVG 등은 Agent 추론을 위한 데이터라기보다 workflow의 최종 결과를 전달하기 위한 rendering이다.

## Consumer Fit

Artifact를 만든다는 것은 그 Artifact를 소비할 Agent, Human, 또는 외부 전달 경로가 workflow 안에 존재한다는 뜻이어야 한다. 따라서 Artifact stream view는 단순한 파일 목록이 아니라, 생산된 Artifact가 적합한 소비자를 갖는지 검토하는 운영 화면이다.

Markdown 같은 `document` Artifact는 특히 소비자 확인이 필요하다. review, handoff, eval, prompt/context reuse, human decision 같은 소비자가 workflow 안에 없다면 기본 선택지는 만들지 않는 것이다. 나중에 다시 꺼내기 위한 목적이라면 Markdown을 계속 늘리기보다 사용 방식에 맞춰 `event_store` JSONL, `knowledge_store` TTL/schema, 또는 `local_database` SQLite로 구조화하는 편이 낫다.

디렉토리는 Artifact 소비 관계를 지원하는 구현 세부사항이다. 디렉토리를 먼저 만들고 workflow를 끼워 맞추는 것이 아니라, workflow topology와 artifact supply chain을 본 뒤 필요한 Artifact boundary만 남긴다. 소비자가 없는 Artifact가 많다면 디렉토리도 줄이거나 합쳐야 한다.

## Repository Workflow Topology

MSO repository에는 세 그래프가 동시에 존재한다.

1. Task Graph: task 간 실행 관계를 정의한다. 대표 관계는 `next`, `dependsOn`, `triggers`다.
2. Artifact Graph: artifact의 생성과 소비 관계를 정의한다. 대표 관계는 `consumes`, `produces`, `reads`, `writes`다.
3. Knowledge Graph: artifact 안에 저장되는 의미와 관계를 정의한다. RDF/OWL ontology, workflow topology, visual identity ontology, conversation ontology가 여기에 속한다.

Workflow는 Artifact를 흐르게 하고, Artifact는 Knowledge를 담으며, Knowledge는 Agent의 실행과 추론을 가능하게 한다.

MSO는 task 중심 Workflow, artifact 중심 Supply Chain, knowledge 중심 Semantic Graph를 하나의 repository 안에서 통합 관리하는 Repository Execution System을 목표로 한다.


## Artifact Provenance (v0.7 — ROADMAP §6)

모든 Artifact는 Provenance를 가진다. Knowledge Base(ontology TTL)도 Artifact이므로 동일하다.

| property | 의미 |
|---|---|
| `wf:author` | 작성/생성 주체 (≈ prov:wasAttributedTo) |
| `wf:version` | artifact 버전 |
| `wf:timestamp` | 생성/갱신 시각 — 실행 도구가 기록한다 (LLM 추정 금지) |
| `wf:validation` | 검증 상태/참조 |
| `wf:coverage` | 커버리지 0..1 |
| `wf:confidence` | 선언된 신뢰 확신도 0..1 — **Trust Score가 아니다** (Trust는 계산 전용) |

`wf:artifactType`은 TTL 명시 선언이 최우선이며, 관측기 추론은 미선언 fallback일 뿐이다.
Artifact 간 근거 계보는 `evidence_of` stream으로 표현되고,
`consumed_by ∘ produces_to = evidence_of` chain이 파생을 보충한다.

## Artifact 층: 개념과 규약 버전 (v0.13.0)

artifact는 TTL registry(`agent-context/index/artifacts.abox.ttl`)에서 두 층으로 정의한다. YAML 레지스트리는 두지 않는다.
어휘는 `mso-workflow-design/references/tbox/workflow-artifact-layer-tbox.ttl`, 형상은 `.../shapes/workflow-artifact-layer-shapes.ttl`이다.
기존 `wf:Artifact`/`wf:Stream`/`wf:artifactType`은 그대로이고 이 층은 그 위에 얹는 추가 어휘다.

| 층 | 클래스 | 가진 것 | 바뀌는가 |
|---|---|---|---|
| 개념 | `wf:RegisteredArtifact` (안정 IRI `art:<name>`) | description, `wf:hasArtifactType`, `wf:consumerType`, `wf:inModule`, `wf:artifactInstruction` | 정체성이라 규약이 바뀌어도 그대로. workflow의 Stream이 이 IRI를 가리킨다 |
| 규약 버전 | `wf:ArtifactConvention` (`art:<name>_cN`) | `wf:directoryTemplate`, `wf:namingConvention`, `wf:fileFormat`(각각 정확히 하나), 변수, 메타데이터 스키마, 유효 구간 | 한 번 커밋되면 세 요소는 바뀌지 않는다. 바꾸려면 새 버전을 만들고 이전 것에 `validUntil`과 `supersededBy`를 붙인다 |

- **템플릿**: 변수는 `[name]`이다(예: `[project]/blog/[date]/`, `[date]-post-[blog_title]`). 정규식이 아니라 템플릿이라 agent가
  이름을 **만들 수** 있고 검증기가 정규식으로 컴파일해 **검사**한다. 변수는 `wf:hasParam`으로 선언하고 형식은 `wf:paramType`
  (DateYmd, MonthYm, Slug, ProjectId, Hash, Integer, AnyToken) 또는 `wf:paramRegex` 중 하나다. 같은 변수는 두 템플릿에서 같은 값이다.
- **consumerType**: `Machine`(agent 친화) / `Hybrid` / `Human`(사람 친화) 중 정확히 하나. 유형의 audience(KnowledgeStore, EventStore,
  LocalDatabase, Tool = Machine / Table, Document = Hybrid / Media = Human)는 기본값이고, 소비 Execution의 `hasSubject`와 교차 점검한다.
- **producer/consumer는 저장하지 않는다.** workflow의 `wf:Stream`(`produces_to`/`consumed_by`)에서 도출한다. 소비하는데 생산자가 없으면
  Violation(`wf:externalSource true` 면제), 생산하는데 소비자가 없으면 Violation이다(사람이 소비하면 `hasSubject human` Execution으로 둔다).
- **유효 구간**: `validFrom`(포함)과 `validUntil`(제외)으로 어느 날짜의 항목이 어느 규약을 따르는지 정한다. 같은 개념의 규약은 구간이
  겹치면 Violation이다. 규약이 바뀐 시점 이전의 옛 항목은 위반이 아니라 이전 규약의 항목이며, 현행 규약 대비 갭으로 따로 센다.
- **변형 파일은 별도 artifact**다. `main.md → main_v1.md → main_v2.pass1.md`는 Execution이 소비하고 생산하는 서로 다른 artifact이고,
  계보는 workflow의 Stream이 맡는다(`references/queries/artifact-lineage.rq`).

검증은 `validate_artifact_layer.py`가 한다. SHACL/SPARQL에 더해 (1) 디렉토리 층(`index.yaml`)과의 교차 점검(`wf:inModule`, 템플릿 접두부),
(2) git HEAD와 비교한 규약 불변 검사, (3) `--scan`(항목 날짜로 유효 규약을 골라 파일 규약, 기간 밖, 레거시, 현행 미분류, 필수 메타데이터 누락과
현행 규약 대비 갭 집계)을 파이썬이 보조한다.

### PROV-O 정렬 (주석, D-23 / D-23a)

어휘 정본은 `wf:`이고 W3C PROV-O 정렬은 TBox **주석**으로만 문서화한다. `prov:`를 import하지 않고 공리로 단언하지도 않는다.

| MSO (`wf:`) | PROV-O | 비고 |
|---|---|---|
| `Execution` | `prov:Activity` | 설계 단계는 계획된 단계(`p-plan:Step`), 실행 기록은 `prov:Activity` |
| `Artifact` | `prov:Entity` | 설계 단계의 개념은 `p-plan:Variable`, 구체 파일은 `prov:Entity` |
| `consumed_by` | `prov:used`의 역 | Artifact→Execution 대 Activity→Entity |
| `produces_to` | `prov:wasGeneratedBy`의 역 | Execution→Artifact 대 Entity→Activity |
| `evidence_of` | `prov:wasDerivedFrom`의 역 | 입력→출력 대 파생→원천 |

equivalentClass를 단언하면 `prov:Activity`인 모든 것이 `wf:Execution`(SHACL 대상)이 되고 계획과 사건이 섞여서 주석으로만 둔다.
공리가 필요하면 별도 opt-in 파일로 분리한다.
