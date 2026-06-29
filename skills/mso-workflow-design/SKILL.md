---
name: mso-workflow-design
version: "0.4.0"
description: >
  Repository Scaffolding(directory/reference/convention) 위에서 워크플로우를
  규정한다. mso-scaffold-design이 정의한 디렉토리 구조(index.yaml)를 입력으로
  받아, 그 위에서 동작하는 step·decision·group 노드를 선언한다. 정본(SSOT-of-record)은
  TTL ABox 이다. YAML 은 신규 작성/역생성 대상이 아니라 legacy migration input 으로만
  허용한다.
  MOTIF 패턴(Phase/Step/Decision/Deliverable/Dependencies/Success Criteria/
  Key Decisions)으로 일관성을 강제하고, 노드 단위 스키마(references/schemas/)와
  TTL ABox와 graph observability 툴로 validate·observe를 지원한다. Mermaid 자동 시각화는
  관측성을 위한 후순위 산출물이다. 다음 상황에서 사용한다:
  (1) scaffold가 정의된 모듈에 워크플로우 규정 추가,
  (2) 기존 워크플로우의 step/decision 노드 추가·수정,
  (3) Discovery→Development→Testing 표준 흐름 정의,
  (4) HITL/HITLFE/HOTL/HOOTL 의사결정 노드 명시,
  (5) 모듈 간 dependencies 선언.
---

# MSO Workflow Design v2

**Primary**: Repository Scaffolding 위에 워크플로우(step·decision·group)를 규정한다. **정본(SSOT-of-record)은 TTL ABox** 이다. YAML 은 legacy migration input 으로만 허용하며, TTL→YAML 역생성 경로는 제공하지 않는다.
**Secondary**: 규정된 워크플로우를 Mermaid로 시각화한다 (관측성, 후순위).

> **워크플로 층위 어휘 (3층)**: `global`(전 프로젝트/엄브렐라 루트) = **UUG 영역**. MSO 는 한
> 프로젝트 안에서 **root-workflow**(프로젝트 루트, 모듈 조율) + **sub-workflow**(모듈 단위, `workflow_ref`)
> 만 다룬다. 과거 `global-workflow-template.yaml`은 legacy migration template으로만 취급한다.

> **확장 네임스페이스 (`x_*`)**: MSO 구조를 baseline 으로 쓰는 소비자(예: MSM)는 도메인 필드를
> top-level `x_<consumer>:` 키에 둔다(OpenAPI `x-` 패턴). wf_node·wf_to_ttl 은 `x_*`/`x-*` 최상위
> 키를 **phase 가 아닌 확장으로 무시**한다 → 한 워크플로가 MSO 구조 검증을 통과하면서 소비자
> 실행 메타(예: MSM `x_msm`: inputs/outputs/runtime/governance)를 함께 실을 수 있다.

## Abstraction Principle

이 스킬은 **구조적 검증**과 **judge taxonomy** 만 강제한다. 네이밍 패턴·동사 어휘·phase 이름·directory role 어휘 등은 **프로젝트 영역**.

| 스킬이 강제하는 것 | 프로젝트가 정의하는 것 |
|----------------|------------------|
| `type ∈ {step, decision, validation, oracle, group, phase}` | `id` 네이밍 패턴 (예: `{abbr}-s-{NNN}`) |
| 노드 id unique, label 존재 | 모듈 약어 매핑 (acp/sdm/…) |
| `judge ∈ {HITL, HITLFE, HOTL, HOOTL, AGENT}` | label 동사 어휘 (분석/생성/검증 …) |
| `branches.on ∈ judge_branch_conditions[judge]` | `phase.id` 어휘 (discovery/development/testing …) |
| HITL/HITLFE → owner 필수, HITLFE → threshold 필수 | `directories.role` 어휘 (input/output/reference/…) |
| status ∈ {completed, active, pending} | `success_criteria` 강제 여부·개수 |
| `directories[].path` 존재 | `owner` 형식 (이메일/팀명/…) |

> 프로젝트별 컨벤션은 [assets/conventions-example.md](assets/conventions-example.md) 를 복사·수정해 `docs/` 또는 `CLAUDE.md` 에 둔다.

## Cross-Reference: mso-scaffold-design ↔ mso-workflow-design

두 스킬은 **양방향 의존** 관계다.

| 스킬 | 책임 | 산출물 |
|------|------|--------|
| **mso-scaffold-design** | Repository 구조(directory/reference/convention) 규정 | `index.yaml` (정본) |
| **mso-workflow-design** | scaffold 위 동작 시퀀스 규정 | `workflow/*.abox.ttl` |

### 의존 규칙

1. **workflow TTL ABox의 `wf:dirPath`** 는 scaffold(`index.yaml`)에 등록된 디렉토리만 참조한다.
   - workflow 작성 시 새 경로가 필요하면 **scaffold(index.yaml)에 먼저 등록**.
2. **scaffold(index.yaml) 수정** 시 — 디렉토리 rename·삭제·이동이 발생하면 workflow TTL의 `wf:dirPath`를 영향 분석한다.
3. legacy YAML을 import할 때만 `migrate_workflows_to_ttl.py`를 사용한다. import가 끝난 뒤 신규 변경은 TTL에서 한다.

> 한쪽 수정이 일어나면 다른 쪽 검토가 필수다.

## SSOT 원칙 (TTL-first)

> **TTL ABox(`*.abox.ttl`)가 SSOT-of-record 다. YAML 은 legacy migration input, md/mermaid 는 시각화 산출물이다.**
>
> 3층 위상: **TTL ABox**(정본·커밋 대상) → **md/mermaid**(시각화·읽기 전용). YAML은 이 흐름 바깥의 일회성 import 입력이다.
>
> - **편집**: 신규 workflow 변경은 TTL ABox에서 한다.
> - **마이그레이션 (YAML → TTL)**: 기존 YAML이 남아 있을 때만 `migrate_workflows_to_ttl.py`로 sibling `.abox.ttl`을 생성한다.
> - **역생성 금지**: TTL → YAML 생성기는 제공하지 않는다. YAML을 되살리면 SSOT 경계가 다시 흔들린다.
> - **관측 재생성**: `mso-graph-observability`로 repository topology와 workflow별 sub-graph를 재생성한다.
>
> ⚠️ md/YAML 을 정본처럼 직접 손대지 않는다 — 변경은 정본 `.abox.ttl`로 흐른다.

## Core Workflow

### Step 1. Scaffold

프로젝트 루트에 workflow SSOT 디렉토리 생성:

```bash
mkdir -p agent-context/workflow
```

신규 workflow는 `agent-context/workflow/workflow-<slug>.abox.ttl`로 작성한다. 기존 YAML이 남아 있는 repository만 migration script로 TTL ABox를 만든다.

### Step 2. Define (MOTIF 패턴 적용)

각 workflow TTL ABox는 7개 필수 MOTIF를 RDF instance로 표현한다:

| Motif | Required Fields |
|-------|----------------|
| Phase Structure | 하나 이상의 phase (id 어휘는 프로젝트 — MSO 권장: discovery/development/testing) |
| Step Definition | `type: step` — `id`, `label`, `status`, `directories` (optional), `deliverables` |
| **Decision Gate** | **`type: decision` — process branch/진행 판단. `judge` ∈ {HITL/HITLFE/HOTL/HOOTL/AGENT}, HITL/HITLFE는 `owner` 필수** |
| **Validation Harness** | **`type: validation` — 자동 검증 게이트. `harness` (runner 식별자), `pass_criteria` 필수** |
| **Oracle Gate** | **`type: oracle` — 산출물 판단/품질평가 게이트. `oracle_type` ∈ {user/agent/metric}, `criteria` 필수. feedback loop의 drift 개입점** |
| Deliverable Taxonomy | `type`, `location`, `status` |
| Dependencies | `requires` (입력), `provides` (출력) |
| Success Criteria | 측정 가능한 기준 (강제 개수는 프로젝트 컨벤션) |
| Key Decisions | `decision`, `rationale`, `status` |

#### Decision vs Validation vs Oracle

| 항목 | `decision` | `validation` | `oracle` |
|------|----------|------------|----------|
| 의미 | process branch/진행 판단 | 자동 검증 하네스 | 산출물 판단/품질평가 권위 |
| 필수 필드 | `judge`, `branches[].on` | `harness`, `pass_criteria` | `oracle_type`, `criteria` |
| 역할 | user/agent decision gate | script/test runner | user/agent/metric oracle gate |
| loop 통제 | 단독으로 drift loop를 끊지 않음 | 검증 실행 근거 | feedback loop의 개입점 |

#### Oracle 필수 패턴: `artifact --check--> oracle --order--> agentTask`

Oracle 노드는 반드시 다음 두 관계를 선언해야 한다.

| 방향 | TTL 프로퍼티 | 의미 |
|------|------------|------|
| **check (입력)** | `wf:directory dirRole=input` 또는 `wf:targetArtifact` | 평가 대상 artifact |
| **order (출력)** | `wf:orderTarget` | 평가 통과 시 order를 받을 downstream step id |

`validate_abox.py` 가 이 두 조건을 강제한다 (`.abox.ttl` 저장 시 PostToolUse hook 자동 실행).
`observe_graph.py --root .` 도 동일 hook에서 자동 실행되어 subgraph/artifact-stream-views 등 observability 산출물을 재생성한다.

**Slot-filling Oracle**: `wf:hasSlot` + `wf:EntitySlot` 을 선언하면 slot-filling 방식으로 동작한다. 모든 슬롯(`slotFilled=true`)이 충족될 때 `wf:orderArtifact`를 생성하고 `orderTarget` step에 전달한다. 이 경우 `orderArtifact`도 필수다.

```ttl
# 예시 — slot-filling oracle
<wf:node/my-d-001> a wf:Oracle, wf:Node ;
    wf:label "문서 선별 게이트" ;
    wf:oracleType "user" ;
    wf:evaluator "owner@example.com" ;
    wf:targetArtifact "01.raw-data/" ;          # check 대상
    wf:orderTarget "my-s-007" ;                 # order 수신 step
    wf:orderArtifact "01.raw-data/manifest.csv" ;
    wf:hasSlot <wf:node/my-d-001_slot_cluster_a>,
               <wf:node/my-d-001_slot_quality> ;
    wf:threshold "ALL hasSlot[*].slotFilled == true" ;
    wf:onFail "my-s-005" .                      # 재수집 경로

<wf:node/my-d-001_slot_cluster_a> a wf:EntitySlot ;
    wf:slotName "cluster_a" ;
    wf:slotConstraint "selected_docs >= 5" ;
    wf:slotFilled false .
```

**공급망 주의**: `orderTarget` step이 oracle의 `orderArtifact`를 소비하려면 해당 step의 `wf:directory` 에 `dirRole=input` 으로 선언해야 공급망 뷰에서 연결이 보인다. oracle의 `wf:orderTarget`만 선언하면 제어 흐름은 맞지만 artifact stream이 끊겨 보인다.

**bypass 방지**: oracle 하위 step(corpus 정리, QA 생성 등)이 oracle 이전 artifact(`raw-data/`)를 직접 소비하면 oracle을 우회하는 `next` 엣지가 공급망에서 자동 추론된다. oracle 이후에만 실행돼야 하는 step은 oracle의 `orderArtifact`를 input으로 추가해 의존 관계를 명시한다.

### 다중 Workflow 패턴 (Repo당 N개 workflow)

하나의 레포에 여러 workflow 가 공존할 수 있다. (예: 정책 사이클, 데이터 파이프라인, 평가, 릴리즈, lifecycle 등)

**명명 컨벤션**:
```
agent-context/workflow/
├── workflow-lifecycle.abox.ttl
├── workflow-policy-cycle.abox.ttl
├── workflow-data-pipeline.abox.ttl
├── workflow-evaluation.abox.ttl
└── workflow-release.abox.ttl
```

→ 패턴: `workflow-<slug>.abox.ttl`

각 workflow scope는 phase/node URI에 포함한다. 예: `wf:phase/lifecycle/discovery`, `wf:node/lifecycle/lc-s-010`.

**legacy YAML 일괄 마이그레이션**:
```bash
python skills/mso-workflow-design/scripts/migrate_workflows_to_ttl.py agent-context/workflow
python skills/mso-workflow-design/scripts/migrate_workflows_to_ttl.py agent-context/workflow --check
```

각 workflow TTL ABox는 독립 그래프로 관측되며, repository 전체 graph와 workflow별 sub-graph가 `mso-graph-observability`에서 생성된다.

### 계층 참조 (Monorepo/Subrepo 패턴)

대형 워크플로우는 root → sub workflow 로 분리할 수 있다. root 의 phase 가 sub workflow 의 phase/group 을 entry point 로 위임한다 (subgraph 형태).

TTL ABox에서는 `wf:hasWorkflowRef`와 `wf:WorkflowRef` instance로 계층 참조를 표현한다. legacy YAML의 `phase.workflows[]`는 migration 시 같은 RDF 관계로 투영된다.

**규칙** (`workflow_ref.schema.yaml`):
- `ref` 와 `module` 모두 **required**.
- `ref` 의 file path 는 scaffold `module:{module}.path` 의 자손이어야 함 (cross-skill invariant).
- `ref` 의 anchor (`#...`) 는 sub 파일의 phase/group id 와 일치해야 함.
- sub 파일이 선언한 `module.id` 와 `module` 필드 값이 일치해야 함.
- 계층 depth 상한 **3** (root + 2단계). 순환 차단.
- node id 는 **계층 전역 unique**.

상세 정의 및 예제:
- [references/yaml-schema.md](references/yaml-schema.md) — legacy YAML migration input 문법 스펙
- [references/motif-patterns.md](references/motif-patterns.md) — 전체 MOTIF 패턴
- [references/gate-levels.md](references/gate-levels.md) — Judge 4-level taxonomy, decision matrix, Mermaid 스타일
- [references/workflow-patterns.md](references/workflow-patterns.md) — Workflow Pattern (Local File Versioning, Git Versioning)

> **MOTIF vs Pattern**: MOTIF는 `id`, `judge` 같은 **필드 구조**가 고정된 단위.  
> Pattern은 Local File Versioning처럼 **사이클 형태**는 같지만 edit 단계 내용이 모듈마다 다른 더 큰 단위.

### Step 3. Validate (필수)

변환 전에 반드시 MOTIF 패턴 준수 검증 실행:

```bash
cd workflow/scripts
python validate_workflow.py            # 전체 검증
python validate_workflow.py --module 04.vendor-x  # 단일 모듈
python validate_workflow.py --strict   # warning까지 error로 승격
```

검증 실패 시 변환 단계로 진행할 수 없다.

### Step 3-B. Graph Validation — TTL TBox/ABox + SHACL/Feedback Loop Control

워크플로 구조를 **DL TBox/ABox** 로 형식화한다(intent 쪽 `intent_taxonomy.ttl`=TBox /
`instances/intents.ttl`=ABox 와 동일 패턴·네임스페이스 계열 `mso.dev/ontology/`).

| 층위 | 파일 | 역할 |
|------|------|------|
| **schema (SSOT)** | [references/schemas/*.yaml](references/schemas/) | 노드 구조의 단일 진실원. 아래 TBox·SHACL 은 여기서 **생성**된다. |
| **TBox** (타입, 생성물) | [references/tbox/workflow-tbox.ttl](references/tbox/workflow-tbox.ttl) | 클래스 계층(Phase/Node⊃Step·Decision·Validation·Group, WorkflowRef/Module/Milestone) + property domain/range + 통제어휘(judge skos). |
| **제약** (생성물) | [references/shapes/workflow-shapes.ttl](references/shapes/workflow-shapes.ttl) | SHACL — 카디널리티·enum·required_when 조건부·range-class. ABox↔TBox 정합 게이트. |
| **ABox** (인스턴스, **SSOT-of-record**) | 프로젝트별 workflow (`a wf:Phase` …) `*.abox.ttl` | 실제 워크플로 정본. 신규 변경은 TTL에서 직접 수행한다. **커밋 대상은 이 파일.** |

> **schemas = SSOT, TBox/SHACL = 생성물**: `schemas/*.yaml` 의 `required`/`type`/`enum`/
> `required_when`/`judge_branch_conditions` 를 `scripts/schemas_to_tbox.py` 가 TBox+SHACL 로
> 변환한다(손 동기화 없음, drift 0). TTL 두 파일은 **직접 편집 금지** — schema 수정 후 재생성.
> ```bash
> python scripts/schemas_to_tbox.py          # 재생성
> python scripts/schemas_to_tbox.py --check  # schemas↔TTL drift 가드 (CI/테스트)
> ```
> 생성 못 하는 것(산문 invariant, branch.on judge-의존 유효성, 교차-스킬)은
> wf_to_ttl.py SPARQL + 수작업으로 분리 유지. schema 없는 root 개념(dependsOn/Module/
> Milestone/directory)은 생성기 내 `_GRAPH_OVERLAY` 에 명시.

> **전환 상태(2026-06-27, TTL-only 확립)**: TTL ABox = SSOT-of-record. YAML은 legacy migration input으로만 남긴다. TTL→YAML 역생성기는 제거했고, 관측/운영은 TTL graph를 직접 읽는다.

```bash
# 레거시 일괄 마이그레이션: workflow YAML → sibling *.abox.ttl
python migrate_workflows_to_ttl.py agent-context/workflow
python migrate_workflows_to_ttl.py agent-context/workflow --check  # CI drift gate
```

> **방향 (TTL-only)**: TTL ABox 가 SSOT-of-record. `wf_to_ttl.py`는 migration backend로만 남는다. 일반 운영자는 `migrate_workflows_to_ttl.py`를 사용하고, migration 이후에는 TTL만 수정한다.

검증은 두 엔진으로 분담한다. 순환 자체는 금지하지 않는다. 다만 산출물이 재귀적으로 소비되는 loop 안에 별도 `oracle` gate가 없으면 uncontrolled feedback loop로 본다. `decision` gate는 진행/분기를 제어하지만, 산출물 품질·정합·수용 가능성의 권위는 `oracle` gate가 담당한다:

| 검사 | 엔진 | 잡는 것 |
|------|------|--------|
| **로컬/정합 shape** | pyshacl (추론 off) | status·judge enum, validation=harness+pass_criteria, decision=judge, label 존재, dependsOn/hasNode/next/gotoNode/criticalDep/milestoneOf **range-class**(dangling ref 포함) |
| **Feedback loop control** | SHACL-SPARQL + rdflib SPARQL | `wf:dependsOn` 또는 `wf:next`/`wf:gotoNode` 순환 중 별도 `wf:Oracle` gate가 없는 loop를 오류로 판정. |
| **교차-스킬**(`--index`) | SPARQL containment join (`STRSTARTS`) | `directories[].path` 가 scaffold(index) 모듈 fs 루트의 자손인지 — 미등록 경로는 warning. scaffold 해소는 `wf_node._resolve_scaffold` **재사용**(중복 로직 안 만듦). 기존 wf_node 내장 사본은 2단계에서 제거 대상. |

| 노드 속성 핵심 | 의미 |
|---|---|
| `wf:label` | 서술격 — '무엇인지'. directive 아님 |
| `wf:instruction` | **지시격** — 실행 주체가 '이걸 하라'는 명령 본문. **Step 필수**(없으면 비실행 노드) |
| `wf:directory` | step 의 directories[] (blank node: `wf:dirRole`+`wf:dirPath`). dirPath = 교차-스킬 멤버십 대상 |

**자기-검증 배선**: legacy YAML migration 단계에서는 validation 노드에서 `harness: wf_shape_validator`
(= `python wf_to_ttl.py validate <this.yaml>`)로 가리킬 수 있다. TTL-only 운영 단계에서는 graph observability와 TTL validation harness로 대체한다.

> RDF 어휘: `wf: <https://mso.dev/ontology/workflow#>` — 클래스/property 전수는 TBox 참조.

### Step 4. Visualize (Optional, 후순위)

> 시각화는 관측성 산출물이다. 정본은 TTL ABox이며, 마크다운/Mermaid는 단순 변환물.
> 워크플로우 규정·검증이 완료된 후에만 의미가 있다.

기본 관측은 `mso-graph-observability`가 담당한다:

```bash
python skills/mso-graph-observability/scripts/observe_graph.py --root .
```

생성되는 핵심 산출물:
- `workflow-topology.md` — repository 전체 workflow graph. phase/module/milestone 수준의 topology를 보여주며, 내부 node 실행 흐름은 workflow별 sub-graph에서만 펼친다.
- `workflow-subgraph-index.md` — workflow scope별 sub-graph 인덱스
- `workflow-subgraphs/<scope>.md` — 특정 workflow 하나만 보는 Mermaid sub-graph
- `workflow-ssot-report.md` — legacy YAML 대비 sibling TTL 누락 보고

`workflow_to_markdown.py`와 `workflow_to_mermaid.py`는 legacy YAML compatibility tooling이다. 신규 관측 경로에서는 사용하지 않는다.

## Legacy YAML Migration 주의사항

### Nested list with dict 금지
```yaml
# Bad — YAML 파싱 오류
deliverables:
  - engine.py:
    - Metric: Faithfulness

# Good — 평면 string으로
deliverables:
  - "engine.py (Faithfulness metric)"
```

### Module ID 일관성
디렉토리명 = `module.id` = workflow scope prefix.
예: `04.vendor-x/` 디렉토리 → `id: 04.vendor-x` → `workflow-04.vendor-x.abox.ttl`

### Dependencies는 모듈 ID로 참조
```yaml
dependencies:
  - requires: 상담 데이터 분석 결과
    source: 01.ingestion
    status: ready
  - provides: 라우팅 정책
    consumers: [04.vendor-x]
```

## 검증 체크리스트

**Scaffold 정합성 (먼저 확인)**
- [ ] `directories.path` 에 쓴 경로가 `index.yaml`(scaffold)에 등록되어 있는가
- [ ] scaffold가 최근 변경됐다면 영향 받은 workflow YAML을 재검증했는가

**Workflow 구조 (스킬이 검증)**
- [ ] 각 노드에 `type` ∈ {step, decision, validation, group} 명시
- [ ] 각 노드에 `id` 명시 (워크플로우 **계층 전역** unique)
- [ ] 각 노드에 `label` 명시
- [ ] 분기·판단 지점은 `type: decision` 노드로 분리
- [ ] 자동 검증 게이트(스키마 검증·테스트 러너·KPI 체크 등)는 `type: validation` 노드로 분리
- [ ] 각 decision 에 `judge` ∈ {HITL/HITLFE/HOTL/HOOTL} 명시
- [ ] HITL/HITLFE → `owner` 필수, HITLFE → `threshold` 필수
- [ ] HITL/HITLFE decision → `description`에 운영자가 선택할 branch/진행 판단 항목 명시 (권장)
- [ ] 각 validation 에 `harness` (runner 식별자), `pass_criteria` 명시
- [ ] `branches[].on` 이 judge 별 허용 조건에 속함
- [ ] phase 에 `status` ∈ {completed, active, pending}

**계층 참조 (스킬이 검증)**
- [ ] `phase.workflows[]` 항목에 `ref`, `module` 모두 명시 (required)
- [ ] `ref` 의 file path 가 scaffold module path 의 자손 (cross-skill, `--scaffold` 옵션으로 확인)
- [ ] `ref` 의 anchor (`#...`) 가 sub 파일의 phase/group id 와 일치
- [ ] 계층 depth ≤ 3, 순환 참조 없음
- [ ] 동일 harness runner id 가 여러 validation 노드에 등장 시 의도 확인 (WARN)

**프로젝트 컨벤션 (프로젝트가 정의·검증)**
- [ ] `id` 네이밍 패턴 (예: `{module-abbr}-s-{NNN}`)
- [ ] label 동사 어휘 일관성
- [ ] phase id 어휘 (discovery/development/testing 등)
- [ ] `directories.role` 어휘 (input/output/reference/instruction 등)
- [ ] `success_criteria` 강제 phase·개수
- [ ] dependencies·key_decisions 필수성

## Node Schema & Tool (wf_node.py)

노드 유형별 YAML 스키마 파일과 이를 읽는 CLI 툴.

### 스키마 파일 (`references/schemas/`)

| 파일 | 대상 노드 | 핵심 정의 |
|------|---------|---------|
| `step.schema.yaml` | `type: step` | 필수 필드 + structural invariants |
| `decision.schema.yaml` | `type: decision` | judge 4-level, conditional fields, branches.on 허용 조건, `description` |
| `validation.schema.yaml` | `type: validation` | 자동 검증 게이트. `harness`, `pass_criteria`, `on_fail` |
| `group.schema.yaml` | `type: group` | 필수 필드, steps 중첩 |
| `phase.schema.yaml` | phase | 필수 필드, status enum, default_judge, `workflows[]` (sub workflow ref) |
| `workflow_ref.schema.yaml` | phase.workflows[] | 계층 참조. `ref` (file#anchor), `module` (required), `harness_propagate` |

### wf_node.py 사용법

```bash
# 스키마 조회
# legacy YAML import 전 검증
python wf_node.py validate path/to/workflow.yaml
python wf_node.py validate path/to/workflow.yaml --scaffold path/to/index.yaml

# legacy YAML → TTL ABox import
python migrate_workflows_to_ttl.py agent-context/workflow
python migrate_workflows_to_ttl.py agent-context/workflow --check
```

> `--id` 의 네이밍 패턴은 프로젝트 컨벤션 영역. 스킬은 unique·존재 여부만 검증한다.

`wf_node.py scaffold`는 legacy YAML migration 보조용으로만 사용한다. 신규 workflow 생성은 TTL ABox로 한다.

## 의존성

```
pyyaml>=6.0
rdflib>=7.0      # TTL graph parsing + feedback-loop SPARQL 검증
pyshacl>=0.31    # migration gate 로컬 shape/feedback-loop 검증
```

## 참고 자료

- **legacy YAML migration input 스펙**: [references/yaml-schema.md](references/yaml-schema.md)
- **MOTIF 패턴 상세**: [references/motif-patterns.md](references/motif-patterns.md)
- **Gate Levels (HITL/HITLFE/HOTL/HOOTL)**: [references/gate-levels.md](references/gate-levels.md)
- **Workflow Patterns**: [references/workflow-patterns.md](references/workflow-patterns.md)
- **마이그레이션 스크립트 (YAML → TTL SSOT)**: [scripts/migrate_workflows_to_ttl.py](scripts/migrate_workflows_to_ttl.py)
- **관측 스킬**: `mso-graph-observability` — repository topology + workflow별 sub-graph 생성
- **legacy root-workflow 템플릿**: [assets/root-workflow-template.yaml](assets/root-workflow-template.yaml)
- **legacy 모듈 템플릿**: [assets/module-workflow-template-00.yaml](assets/module-workflow-template-00.yaml)
