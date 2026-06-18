---
name: mso-workflow-design
version: "0.3.4"
description: >
  Repository Scaffolding(directory/reference/convention) 위에서 워크플로우를
  규정한다. mso-scaffold-design이 정의한 디렉토리 구조(index.yaml)를 입력으로
  받아, 그 위에서 동작하는 step·decision·group 노드를 선언한다. 정본(SSOT-of-record)은
  TTL ABox 이고 YAML 은 무손실 편집 편의층이다(wf_to_ttl/ttl_to_wf 양방향).
  MOTIF 패턴(Phase/Step/Decision/Deliverable/Dependencies/Success Criteria/
  Key Decisions)으로 일관성을 강제하고, 노드 단위 스키마(references/schemas/)와
  wf_node.py 툴로 validate·scaffold를 지원한다. Mermaid 자동 시각화는
  관측성을 위한 후순위 산출물이다. 다음 상황에서 사용한다:
  (1) scaffold가 정의된 모듈에 워크플로우 규정 추가,
  (2) 기존 워크플로우의 step/decision 노드 추가·수정,
  (3) Discovery→Development→Testing 표준 흐름 정의,
  (4) HITL/HITLFE/HOTL/HOOTL 의사결정 노드 명시,
  (5) 모듈 간 dependencies 선언.
---

# MSO Workflow Design v2

**Primary**: Repository Scaffolding 위에 워크플로우(step·decision·group)를 규정한다. **정본(SSOT-of-record)은 TTL ABox** 이며, YAML 은 편집 편의층(authoring convenience)이다 — 양방향 무손실 컴파일.  
**Secondary**: 규정된 워크플로우를 Mermaid로 시각화한다 (관측성, 후순위).

> **워크플로 층위 어휘 (3층)**: `global`(전 프로젝트/엄브렐라 루트) = **UUG 영역**. MSO 는 한
> 프로젝트 안에서 **root-workflow**(프로젝트 루트, 모듈 조율) + **sub-workflow**(모듈 단위, `workflow_ref`)
> 만 다룬다. ⚠️ 과거 `global-workflow-template.yaml`은 실제로 root-workflow 라 `root-workflow-template.yaml`
> 로 개명. 시각화 소비자(`workflow_to_mermaid.py`)의 `--global`·`01-global-workflow.md` 어휘 정정은
> 2단계(소비자 이관)로 유보.

> **확장 네임스페이스 (`x_*`)**: MSO 구조를 baseline 으로 쓰는 소비자(예: MSM)는 도메인 필드를
> top-level `x_<consumer>:` 키에 둔다(OpenAPI `x-` 패턴). wf_node·wf_to_ttl 은 `x_*`/`x-*` 최상위
> 키를 **phase 가 아닌 확장으로 무시**한다 → 한 워크플로가 MSO 구조 검증을 통과하면서 소비자
> 실행 메타(예: MSM `x_msm`: inputs/outputs/runtime/governance)를 함께 실을 수 있다.

## Abstraction Principle

이 스킬은 **구조적 검증**과 **judge taxonomy** 만 강제한다. 네이밍 패턴·동사 어휘·phase 이름·directory role 어휘 등은 **프로젝트 영역**.

| 스킬이 강제하는 것 | 프로젝트가 정의하는 것 |
|----------------|------------------|
| `type ∈ {step, decision, validation, group, phase}` | `id` 네이밍 패턴 (예: `{abbr}-s-{NNN}`) |
| 노드 id unique, label 존재 | 모듈 약어 매핑 (acp/sdm/…) |
| `judge ∈ {HITL, HITLFE, HOTL, HOOTL}` | label 동사 어휘 (분석/생성/검증 …) |
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
| **mso-workflow-design** | scaffold 위 동작 시퀀스 규정 | `workflow/*-workflow-00.yaml` |

### 의존 규칙

1. **workflow YAML의 `directories.path`** 는 scaffold(`index.yaml`)에 등록된 디렉토리만 참조한다.
   - workflow 작성 시 새 경로가 필요하면 **scaffold(index.yaml)에 먼저 등록**.
2. **scaffold(index.yaml) 수정** 시 — 디렉토리 rename·삭제·이동이 발생하면 workflow YAML의 `directories.path`를 영향 분석한다.
3. **workflow YAML 수정** 시 — 새 directory role(`input`/`output`/`reference`/`instruction`) 사용이 발생하면 scaffold에 해당 경로가 존재하는지 검증한다.

> 한쪽 수정이 일어나면 다른 쪽 검토가 필수다.

## SSOT 원칙 (TTL-first)

> **TTL ABox(`*.abox.ttl`)가 SSOT-of-record 다. YAML 은 편집 편의층, md/mermaid 는 시각화 산출물이다.**
>
> 3층 위상: **TTL ABox**(정본·커밋 대상) → **YAML**(편집 편의·재생성 가능) → **md/mermaid**(시각화·읽기 전용).
>
> - **편집**: YAML 또는 TTL 어느 쪽이든 편집 가능(둘 다 무손실 변환). 단 **커밋되는 정본은 `.abox.ttl`** 이다.
> - **컴파일 (YAML → 정본)**: YAML 수정 후 `wf_to_ttl.py serialize`로 `.abox.ttl` 재생성 + `wf_to_ttl.py validate` 게이트 통과 → 커밋.
> - **역컴파일 (TTL → 편집층)**: TTL 직접 수정·생성 시 `ttl_to_wf.py`로 YAML 재생성(SHACL/비순환 게이트 통과분만 승격).
> - **무손실**: YAML↔TTL 은 그래프 동형(isomorphic) 수준의 양방향 무손실 — narrative meta(project/key_decisions/milestones/success_criteria) 포함 **전 문서**. 회귀 가드: `tests/test_wf_to_ttl.py::test_template_roundtrip_isomorphic`.
> - **시각화 재생성**: `workflow_to_mermaid.py --all`로 md 재생성(읽기 전용, 직접 편집 금지).
>
> ⚠️ md/YAML 을 정본처럼 직접 손대지 않는다 — 변경은 정본 `.abox.ttl`(또는 편집층 YAML→serialize)로 흐른다.

## Core Workflow

### Step 1. Scaffold

프로젝트 루트에 워크플로우 디렉토리 생성:

```bash
mkdir -p workflow/{scripts,diagrams}
cp .claude/skills/mso-workflow-design/assets/root-workflow-template.yaml \
   workflow/workflow-00.yaml
cp .claude/skills/mso-workflow-design/scripts/workflow_to_mermaid.py \
   workflow/scripts/
```

각 모듈마다:
```bash
mkdir workflow/[module-id]
cp .claude/skills/mso-workflow-design/assets/module-workflow-template-00.yaml \
   workflow/[module-id]/[module-id]-workflow-00.yaml
```

### Step 2. Define (MOTIF 패턴 적용)

각 module workflow YAML은 7개 필수 MOTIF를 따른다:

| Motif | Required Fields |
|-------|----------------|
| Phase Structure | 하나 이상의 phase (id 어휘는 프로젝트 — MSO 권장: discovery/development/testing) |
| Step Definition | `type: step` — `id`, `label`, `status`, `directories` (optional), `deliverables` |
| **Decision Node** | **`type: decision` — `judge` ∈ {HITL/HITLFE/HOTL/HOOTL}, HITL/HITLFE는 `owner` 필수, `description` 권장 (판정 주체가 검토할 항목 서술)** |
| **Validation Harness** | **`type: validation` — 자동 검증 게이트. `harness` (runner 식별자), `pass_criteria` 필수** |
| Deliverable Taxonomy | `type`, `location`, `status` |
| Dependencies | `requires` (입력), `provides` (출력) |
| Success Criteria | 측정 가능한 기준 (강제 개수는 프로젝트 컨벤션) |
| Key Decisions | `decision`, `rationale`, `status` |

#### Validation vs Decision

| 항목 | `decision` | `validation` |
|------|----------|------------|
| 의미 | 분기 판단 (사람/모델이 판단) | 자동 검증 하네스 (스크립트가 패스/실패 판정) |
| 필수 필드 | `judge`, `branches[].on` | `harness`, `pass_criteria` |
| Mermaid 형태 | 마름모 `{}` | 육각형 `{{}}` |
| 분기 | 가능 (branches 명시) | 일반적으로 단일 후속 (실패 시 별도 정책) |

### 다중 Workflow 패턴 (Repo당 N개 workflow)

하나의 레포에 여러 workflow 가 공존할 수 있다. (예: 정책 사이클, 데이터 파이프라인, 평가, 릴리즈, lifecycle 등)

**명명 컨벤션**:
```
agent-context/workflow/
├── workflow-00.yaml              # 기본/lifecycle (legacy 호환)
├── workflow-policy-cycle.yaml
├── workflow-data-pipeline.yaml
├── workflow-evaluation.yaml
└── workflow-release.yaml
```

→ 패턴: `workflow-<slug>.yaml`

**각 yaml 의 메타 (필수)**:
```yaml
workflow:
  id: lifecycle              # 전역 unique
  slug: lifecycle            # 파일명과 일치
  description: ...
```

**일괄 검증**:
```bash
wf_node validate-all agent-context/workflow/
wf_node validate-all agent-context/workflow/ --scaffold agent-context/index/index.yaml
wf_node validate-all . --pattern "*workflow*.yaml"   # 모듈 workflow 도 포함
```

각 workflow YAML은 독립 root 로 검증되며, 자체 계층 참조(workflow_ref) 트리를 가질 수 있다.

### 계층 참조 (Monorepo/Subrepo 패턴)

대형 워크플로우는 root → sub workflow 로 분리할 수 있다. root 의 phase 가 sub workflow 의 phase/group 을 entry point 로 위임한다 (subgraph 형태).

```yaml
# root workflow.yaml
phase-01-discovery:
  label: 발견 & 계획
  status: active
  workflows:
    - ref: 02.policy-engine/workflow/02.policy-engine-workflow-00.yaml#discovery
      module: 02.policy-engine        # required (scaffold module id 와 일치)
      harness_propagate: true             # default true
```

**규칙** (`workflow_ref.schema.yaml`):
- `ref` 와 `module` 모두 **required**.
- `ref` 의 file path 는 scaffold `module:{module}.path` 의 자손이어야 함 (cross-skill invariant).
- `ref` 의 anchor (`#...`) 는 sub 파일의 phase/group id 와 일치해야 함.
- sub 파일이 선언한 `module.id` 와 `module` 필드 값이 일치해야 함.
- 계층 depth 상한 **3** (root + 2단계). 순환 차단.
- node id 는 **계층 전역 unique**.

상세 정의 및 예제:
- [references/yaml-schema.md](references/yaml-schema.md) — **YAML 공식 문법 스펙** (step/decision/group/phase)
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

### Step 3-B. Graph Validation — TTL TBox/ABox + SHACL/DAG

워크플로 구조를 **DL TBox/ABox** 로 형식화한다(intent 쪽 `intent_taxonomy.ttl`=TBox /
`instances/intents.ttl`=ABox 와 동일 패턴·네임스페이스 계열 `mso.dev/ontology/`).

| 층위 | 파일 | 역할 |
|------|------|------|
| **schema (SSOT)** | [references/schemas/*.yaml](references/schemas/) | 노드 구조의 단일 진실원. 아래 TBox·SHACL 은 여기서 **생성**된다. |
| **TBox** (타입, 생성물) | [references/tbox/workflow-tbox.ttl](references/tbox/workflow-tbox.ttl) | 클래스 계층(Phase/Node⊃Step·Decision·Validation·Group, WorkflowRef/Module/Milestone) + property domain/range + 통제어휘(judge skos). |
| **제약** (생성물) | [references/shapes/workflow-shapes.ttl](references/shapes/workflow-shapes.ttl) | SHACL — 카디널리티·enum·required_when 조건부·range-class. ABox↔TBox 정합 게이트. |
| **ABox** (인스턴스, **SSOT-of-record**) | 프로젝트별 workflow (`a wf:Phase` …) `*.abox.ttl` | 실제 워크플로 정본. YAML 편집층에서 `serialize` 로 생성하거나 TTL 직접 저작. **커밋 대상은 이 파일.** |

> **schemas = SSOT, TBox/SHACL = 생성물**: `schemas/*.yaml` 의 `required`/`type`/`enum`/
> `required_when`/`judge_branch_conditions` 를 `scripts/schemas_to_tbox.py` 가 TBox+SHACL 로
> 변환한다(손 동기화 없음, drift 0). TTL 두 파일은 **직접 편집 금지** — schema 수정 후 재생성.
> ```bash
> python scripts/schemas_to_tbox.py          # 재생성
> python scripts/schemas_to_tbox.py --check  # schemas↔TTL drift 가드 (CI/테스트)
> ```
> 생성 못 하는 것(산문 invariant, branch.on judge-의존 유효성, 비순환성·교차-스킬)은
> wf_to_ttl.py SPARQL + 수작업으로 분리 유지. schema 없는 root 개념(dependsOn/Module/
> Milestone/directory)은 생성기 내 `_GRAPH_OVERLAY` 에 명시.

> **전환 상태(2026-06-18, TTL-first 확립)**: TTL ABox = SSOT-of-record. YAML↔TTL **전 문서 무손실**(그래프 동형) 확보 — narrative meta(project/key_decisions/milestones/success_criteria) + WorkflowRef(module/harness_propagate) + decision.branches(on/goto) + top-level 메타 블록(workflow/module/meta/metadata + 소비자 `x_*` 확장, `wf:MetaBlock` rawJson) 포함. 잔여 후속: mermaid/markdown/wf_node **소비자를 TTL 리더로 이관**(현재는 정본 TTL→YAML 재생성 후 기존 YAML 소비자 사용), group 중첩(nesting) 평탄화는 미해소 한계.

```bash
# 정본 컴파일: 편집층 YAML → SSOT-of-record ABox TTL
python wf_to_ttl.py serialize workflow/workflow-00.yaml > workflow/workflow-00.abox.ttl  # YAML → 정본 ABox (커밋 대상)
python wf_to_ttl.py validate  workflow/workflow-00.yaml [--json] # ABox↔TBox 정합 게이트, 위반 시 exit 1
python wf_to_ttl.py validate  workflow/workflow-00.yaml --index index/index.yaml  # +교차-스킬 경로(warning)
# 역컴파일: 정본/수기 TTL → 편집층 YAML (SHACL 게이트 통과분만)
python ttl_to_wf.py  workflow/workflow-00.abox.ttl -o workflow/workflow-00.yaml
```

> **방향 (TTL-first)**: TTL ABox 가 SSOT-of-record. `wf_to_ttl serialize`(YAML→TTL)는 **편집층 → 정본 컴파일**,
> `ttl_to_wf`(TTL→YAML)는 정본/수기 TTL 을 SHACL+비순환 게이트 통과 시 편집층 YAML 로 재생성하는 **양방향 무손실**.
> 게이트 실패 시 YAML 미출력(불량 승격 차단). 라운드트립: phases/nodes 스칼라·리스트·directories·**branches·workflow_ref(module/harness_propagate)·narrative meta·top-level 메타 블록(workflow/module/meta/`x_*`)** 전부 충실(그래프 동형). 단 group 노드 중첩은 평탄화(후속).

검증은 두 엔진으로 분담한다(SHACL 단독으로는 DAG 형상 전체를 못 잡는다):

| 검사 | 엔진 | 잡는 것 |
|------|------|--------|
| **로컬/정합 shape** | pyshacl (추론 off) | status·judge enum, validation=harness+pass_criteria, decision=judge, label 존재, dependsOn/hasNode/criticalDep/milestoneOf **range-class**(dangling ref 포함) |
| **전역 DAG** | rdflib SPARQL `ASK { ?x (wf:dependsOn\|wf:criticalDep)+ ?x }` | **비순환성** — 다운스트림 결과가 업스트림으로 재참조되는 의존 사이클을 오류로 판정. SHACL core 불가한 임의-깊이 도달성. |
| **교차-스킬**(`--index`) | SPARQL containment join (`STRSTARTS`) | `directories[].path` 가 scaffold(index) 모듈 fs 루트의 자손인지 — 미등록 경로는 warning. scaffold 해소는 `wf_node._resolve_scaffold` **재사용**(중복 로직 안 만듦). 기존 wf_node 내장 사본은 2단계에서 제거 대상. |

| 노드 속성 핵심 | 의미 |
|---|---|
| `wf:label` | 서술격 — '무엇인지'. directive 아님 |
| `wf:instruction` | **지시격** — 실행 주체가 '이걸 하라'는 명령 본문. **Step 필수**(없으면 비실행 노드) |
| `wf:directory` | step 의 directories[] (blank node: `wf:dirRole`+`wf:dirPath`). dirPath = 교차-스킬 멤버십 대상 |

**자기-검증 배선**: workflow 의 validation 노드에서 `harness: wf_shape_validator`
(= `python wf_to_ttl.py validate <this.yaml>`)로 가리키면 워크플로 자체 형상이 게이트가 된다.

> RDF 어휘: `wf: <https://mso.dev/ontology/workflow#>` — 클래스/property 전수는 TBox 참조.

### Step 4. Visualize (Optional, 후순위)

> 시각화는 관측성 산출물이다. 정본은 TTL ABox(YAML은 편집층)이며, 마크다운/Mermaid는 단순 변환물.  
> 워크플로우 규정·검증이 완료된 후에만 의미가 있다.

두 가지 변환 스크립트를 제공한다:

| 스크립트 | 출력 | 용도 |
|---------|------|------|
| `workflow_to_markdown.py` | 모듈별 **통합 마크다운 1개** (mermaid + 테이블 + 메타데이터) | 모듈 단위 문서화·리뷰 |
| `workflow_to_mermaid.py` | **프로젝트 전체 다이어그램 세트** (global/module/dependencies/deliverables/timeline) | 프로젝트 단위 관측성 |

#### 4-A. 모듈별 통합 마크다운 (`workflow_to_markdown.py`)

단일 모듈 YAML을 받아 mermaid 다이어그램 + phase 테이블(ID/Type/Title/State/Output/Validation) + 메타데이터를 하나의 .md로 출력한다.

```bash
python workflow_to_markdown.py workflow/04.vendor-x/04.vendor-x-workflow-00.yaml
# → workflow/04.vendor-x/04.vendor-x-workflow-00.md

python workflow_to_markdown.py workflow/04.vendor-x/04.vendor-x-workflow-00.yaml \
  -o workflow/04.vendor-x/04.vendor-x-workflow.md
```

- 노드 형태: step → `[]`, decision → `{}` (마름모), validation → `{{}}` (육각형), group → `([])`
- 상태별 색상: completed(녹색), active(주황), pending(연보라), blocked(분홍)
- Decision 노드의 `branches[].goto` 가 자동으로 edge로 변환됨 (on 라벨 포함)

**계층 통합 모드** (`--aggregate`): root → sub workflow 트리를 하나의 마크다운으로 통합.

```bash
python workflow_to_markdown.py workflow/workflow-00.yaml --aggregate -o aggregate.md
```

#### 4-B. 프로젝트 전체 시각화 세트 (`workflow_to_mermaid.py`)

```bash
cd workflow/scripts
python workflow_to_mermaid.py --all    # 자동으로 validate_workflow.py 선행 실행
```

`workflow_to_mermaid.py`는 변환 전 자동으로 `validate_workflow.py`를 호출한다.  
검증 실패 시 변환은 중단된다 (`--skip-validation`으로 강제 변환 가능하나 권장하지 않음).

생성되는 다이어그램:
- `01-global-workflow.md` — 프로젝트 5-phase flowchart
- `02-module-[id].md` — 모듈별 discovery/development/testing flow
- `03-dependencies-graph.md` — 모듈 간 의존성 그래프
- `04-deliverables-[id].md` — 산출물 트리
- `05-timeline-[id].md` — Gantt chart

개별 다이어그램만 생성:
```bash
python workflow_to_mermaid.py --global
python workflow_to_mermaid.py --module 01.ingestion
python workflow_to_mermaid.py --dependencies
```

**계층 subgraph 통합** (`--aggregate`): root → sub workflow 트리를 nested subgraph 형태의 단일 다이어그램으로 렌더링.

```bash
python workflow_to_mermaid.py --aggregate workflow/workflow-00.yaml
# → diagrams/06-aggregate-workflow-00.md
```

## YAML 작성 시 주의사항

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
디렉토리명 = `module.id` = YAML 파일명 prefix.  
예: `04.vendor-x/` 디렉토리 → `id: 04.vendor-x` → `04.vendor-x-workflow-00.yaml`

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
- [ ] HITL/HITLFE decision → `description`에 운영자가 검토할 항목 명시 (권장)
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
python wf_node.py show step
python wf_node.py show decision      # judge 결정 흐름 포함
python wf_node.py show validation    # 자동 검증 게이트

# 노드 스캐폴드 생성 (stdout 에 YAML 출력)
python wf_node.py scaffold step --id mymod-s-001
python wf_node.py scaffold decision --id mymod-d-001 --judge HITLFE
python wf_node.py scaffold validation --id mymod-v-001
python wf_node.py scaffold group --id mymod-g-001

# 워크플로우 YAML 전체 검증 (계층 참조 자동 해석)
python wf_node.py validate path/to/workflow.yaml

# 특정 노드만 검증
python wf_node.py validate path/to/workflow.yaml --node mymod-d-001

# Cross-skill 검증 (scaffold 와 정합성 검사)
python wf_node.py validate path/to/workflow.yaml --scaffold path/to/index.yaml

# Harness manifest 생성 (validation 노드 → CI 매니페스트)
python wf_node.py harness-manifest path/to/root_workflow.yaml --out ci-manifest.json
python wf_node.py harness-manifest path/to/root_workflow.yaml --format yaml
```

> `--id` 의 네이밍 패턴은 프로젝트 컨벤션 영역. 스킬은 unique·존재 여부만 검증한다.

scaffold 결과를 workflow YAML에 붙여 넣은 뒤 TODO 값을 채우면 된다.

## 의존성

```
pyyaml>=6.0
rdflib>=7.0      # wf_to_ttl.py — TTL 투영 + SPARQL DAG 검증
pyshacl>=0.31    # wf_to_ttl.py — 로컬 shape 검증 (미설치 시 SHACL만 skip, DAG 검증은 동작)
```

## 참고 자료

- **YAML 문법 스펙**: [references/yaml-schema.md](references/yaml-schema.md)
- **MOTIF 패턴 상세**: [references/motif-patterns.md](references/motif-patterns.md)
- **Gate Levels (HITL/HITLFE/HOTL/HOOTL)**: [references/gate-levels.md](references/gate-levels.md)
- **Workflow Patterns**: [references/workflow-patterns.md](references/workflow-patterns.md)
- **변환 스크립트 (모듈 통합 .md)**: [scripts/workflow_to_markdown.py](scripts/workflow_to_markdown.py)
- **변환 스크립트 (전체 시각화 세트)**: [scripts/workflow_to_mermaid.py](scripts/workflow_to_mermaid.py)
- **root-workflow 템플릿**: [assets/root-workflow-template.yaml](assets/root-workflow-template.yaml)
- **모듈 템플릿**: [assets/module-workflow-template-00.yaml](assets/module-workflow-template-00.yaml)
