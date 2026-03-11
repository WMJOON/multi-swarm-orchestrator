---
name: mso-mental-model-design
description: |
  Vertex Registry — 도메인별 directive(framework/instruction/prompt)를 택소노미로 관리하고
  topology vertex에 바인딩한다. 워크플로우 레지스트리(mso-workflow-topology-design Mode B)와 상호보완.
  Use when topology nodes need domain-specific thinking models, execution instructions, or prompt templates,
  or when new directives need to be registered, searched, or taxonomized.
---

# mso-mental-model-design

> Vertex Registry. Topology가 **구조**(Motif + Vertex 타입)를 정의하면, 이 스킬이 각 Vertex에
> **도메인 지식**(directive)을 바인딩한다.

---

## 핵심 정의

| 개념 | 정의 |
|------|------|
| **Directive** | Vertex에 바인딩되는 도메인 지식 단위. MD 파일(frontmatter + body)로 저장 |
| **Vertex Registry** | Directive를 택소노미로 분류·검색·관리하는 저장소 |
| **Directive Binding** | Run 실행 시 topology 노드 ↔ directive 매핑 |
| **Local Chart** | 도메인별 저장된 의미 좌표계. 축(axis) semantic 정의 + 기존 vertex 좌표 캐시. `chart.json`으로 저장되며 신규 vertex 추가 시 전체 재연산 불필요 |
| **Chart Projection** | 새 vertex 개념 → 기존 chart 각 축과의 유사도 계산(K번) → `axis_coord[]` 산출. N×N 전체 재연산 대신 1×K 투영만 수행 |
| **Sparsity 원칙** | 주도 축 ≥ 0.7 (이상적으로 ≥ 0.8), 나머지 보조 축 ≤ 0.3. 1 vertex = 1 핵심 관심사(concern) 원칙 |
| **Purpose** | 차트 Bootstrap 기준점. 문제 공간 경계·제약 조건·좌표계 기준을 정의. 지나치게 넓으면 의미 공간 확산으로 구조 안정성 저하 |
| **LLM 의미 근사** | 실제 Embedding 모델 대신 LLM이 프롬프트 쌍의 의미 유사도를 0.0~1.0으로 직접 판단. Embedding 모델 기반으로 추후 교체 가능 |

### Directive 유형

| type | 역할 | 적합 vertex_type |
|------|------|-----------------|
| `framework` | 사고 모델·분석 프레임워크 | agent |
| `instruction` | 실행 절차·규칙 | agent, skill |
| `prompt` | LLM 프롬프트 템플릿 | model |

---

## Directive MD 파일 구조

```markdown
---
id: dir-001
type: framework
name: MECE Decomposition
domain: analysis
taxonomy_path: [analysis, decomposition]
concepts: [mutually_exclusive, collectively_exhaustive]
applicable_vertex_types: [agent]
applicable_motifs: [fork_join, diamond]
---

# MECE Decomposition

(body: 프레임워크 설명, 적용 절차, 예시 등)
```

**필수 frontmatter**: `id`, `type`, `name`, `domain`, `taxonomy_path`
**선택 frontmatter**: `concepts`, `applicable_vertex_types`, `applicable_motifs`, `related`
**Chart 연동 frontmatter**: `axis`, `axis_coord` (Local Chart에 등록된 vertex는 필수)

---

## 저장 경로

| 경로 | 역할 |
|------|------|
| `~/.mso-registry/<domain>/` | **글로벌** Directive 저장소 — 워크플로우·프로젝트 간 공유 |
| `~/.mso-registry/<domain>/chart.json` | 도메인 Local Chart (축 정의 + vertex 좌표 캐시) |
| `~/.mso-registry/<domain>/orthogonality.json` | 직교성 검증 결과 + similarity_matrix |
| `{mso-mental-model-design}/directives/` | 스킬 내장 seed Directive (초기값) |
| `{workspace}/.mso-context/active/<run_id>/20_mental-model/directive_binding.json` | Run별 노드↔directive 바인딩 (워크스페이스 로컬) |

### Registry 해석 순서

| 순서 | 경로 | 설명 |
|------|------|------|
| 1 | `~/.mso-registry/<domain>/` | 글로벌 — 프로젝트 간 공유 |
| 2 | `{workspace}/.mso-context/vertex_registry/<domain>/` | 워크스페이스 로컬 fallback |
| 3 | `{mso-mental-model-design}/directives/` | 스킬 내장 seed |

머지 전략: UNION (글로벌 우선, id 충돌 시 글로벌 우선)

---

## 실행 프로세스

### Phase 1: Topology 입력 + Registry 탐색

1. `workflow_topology_spec.json`에서 `nodes[]`를 읽는다
2. 각 노드의 `vertex_type`, `assigned_dqs`, 소속 `motif`를 파악한다
3. Vertex Registry에서 해당 조건에 맞는 directive 후보를 검색한다

**검색 우선순위:**
1. `applicable_vertex_types` 일치
2. `applicable_motifs` 일치
3. `domain` 일치
4. `taxonomy_path` 깊이 (구체적일수록 우선)

**스크립트:**
```
python3 {mso-mental-model-design}/scripts/search_directives.py \
  --registry ~/.mso-registry \
  --vertex-type agent --motif chain --domain analysis
```

**when_unsure**: 후보가 없으면 `domain: "general"` fallback 검색. 그래도 없으면 unbound 기록.

**산출물**: `candidates[{ node_id, directive_candidates[] }]`

---

### Phase 2: Directive Binding

1. 각 노드에 최적 directive를 선택한다 (자동 또는 사용자 확인)
2. 1 node : 1+ directive 바인딩 가능 (다중 렌즈)
3. 바인딩 결과를 `directive_binding.json`에 기록한다

**자동 선택 기준:**
- 후보가 1개 → 자동 바인딩
- 후보가 2개 이상 → `taxonomy_path` 깊이 + domain 정확도 기준 상위 선택
- 후보가 0개 → `unbound_nodes[]`에 기록

**when_unsure**: 2개 이상 후보가 동점 → 사용자에게 선택 요청.

**산출물**: `directive_binding.json`

---

### Phase 3: Directive 신규 등록 (선택)

기존 registry에 적합한 directive가 없을 때 새로 생성·등록한다.

1. 사용자와 협의하여 directive MD 파일 작성
2. `~/.mso-registry/<domain>/` 하위에 저장
3. frontmatter 유효성 검증 후 등록

**스크립트:**
```
python3 {mso-mental-model-design}/scripts/register_directive.py \
  --file <directive.md> \
  --registry ~/.mso-registry
```

---

### Mode C vs D — 진입 조건

| 조건 | 선택 Mode |
|------|----------|
| `~/.mso-registry/<domain>/chart.json` 존재 | **Mode C** (Projection) |
| 파일 미존재 | **Mode D** (Bootstrap) |

---

### Mode C: Chart Projection (신규 vertex → 기존 chart 투영)

도메인 Local Chart가 이미 존재할 때, 새 개념을 전체 재연산 없이 기존 좌표계에 투영한다.

**입력:**
- 새 vertex 개념 설명 (자유 텍스트)
- 대상 `chart_id` 또는 `chart.json` 경로

**처리:**
1. `chart.json`에서 axes[] 목록 읽기
2. 각 축(axis)에 대해 "이 개념과 이 축의 의미 유사도는 0.0~1.0?" 판단 → `axis_coord[]` 생성
3. **Sparsity 검증**: 주도 축 ≥ 0.7 / 나머지 ≤ 0.3 조건 확인
   - 실패 시 → 개념 분리 권장 (1개 개념이 2개 축에 걸쳐 있음)
4. 기존 vertex와 cosine similarity 계산 → 중복 여부 판단 (threshold > 0.5 경고)
5. 검증 통과 시 → `chart.json` vertices에 append
6. Directive MD 파일 생성 (`axis`, `axis_coord` frontmatter 포함)

**스크립트:** `project_vertex.py` — 현재 미구현. LLM이 직접 처리 6단계를 실행.

**산출물:** 업데이트된 `chart.json` + 새 directive MD 파일

**when_unsure**: 주도 축이 2개 이상(동점) → 사용자에게 어느 축이 주축인지 확인 후 결정.

---

### Mode D: Chart Bootstrap (도메인 차트 최초 생성)

특정 도메인의 Local Chart가 존재하지 않을 때, 처음부터 좌표계를 구성한다.

**Purpose → Prompts → (LLM 근사 Embedding) → Orthogonality → Decomposition → Clustering → Merge → chart.json**

> **Note**: 이 파이프라인은 실제 Embedding 모델 대신 LLM 의미 판단으로 근사한다.
> 추후 Sentence Embedding 모델 기반으로 교체 가능 (현재 미구현).

**입력:**
- **Purpose**: 문제 공간 경계 + 분석 목적 (예: "AICC 시장 경쟁 구조 분석")
- 도메인 이름 (예: `ir-deck`, `analysis`, `nlu`)

**처리:**

**Step 0: Purpose 정의**
- 분석할 문제 공간(problem space) 경계를 1~2문장으로 명시
- 좌표계 기준점 역할 — 이후 모든 프롬프트·축은 Purpose에 부합해야 함
- Purpose가 지나치게 넓으면 프롬프트 의미 공간이 확산되어 구조 안정성 저하 → 범위 좁히기

**Step 1: Framework Prompt Generation**
- Purpose 기반으로 분석 관점(프레임워크) 프롬프트 대량 생성: P = {p₁, p₂, ..., pₙ}
- 초기 단계에서 의미 중복·경계 불명확은 자연스러운 현상 — 이후 단계에서 해소
- 목표: 문제 공간을 충분히 탐색하는 프롬프트 커버리지 확보

**Step 2: LLM 의미 근사 (Embedding 대체)**
- 실제 벡터화 대신 LLM이 프롬프트 쌍마다 의미 유사도를 0.0~1.0으로 직접 판단
- "p₁과 p₂의 핵심 분석 관심사가 얼마나 겹치는가?" → 수치 산출
- **제약 조건 (K > N 근사)**: 분석 축 수 N이 실제 의미 차원을 초과하면 강제 중복 발생 →
  N을 의미 공간이 자연스럽게 지지하는 수준(보통 5~12개)으로 제한

**Step 3: Orthogonality Measurement**
- 각 프롬프트 쌍의 LLM 추정 유사도 계산 → similarity matrix 구성
- avg_similarity ≤ 0.1 목표

**Step 4: Atomic Decomposition & 루프**
- 4a. 유사도 > 0.4인 프롬프트 쌍을 하위 개념으로 분해: pᵢ → {pᵢ₁, pᵢ₂, ..., pᵢₘ}
- 4b. Step 3로 돌아가 새 similarity matrix 계산
- 4c. avg_similarity ≤ 0.1 충족 시 Step 5 진행 / 미달 시 4a 반복

**Step 5: Clustering → 축 유도**
- 의미적으로 유사한 원자 단위를 클러스터링 → 각 클러스터 = 1개 의미 축(axis)
- 각 축의 semantic 레이블 정의

**Step 6: Merge + Relation Mapping**
- 클러스터 내 원자 단위를 병합 → 대표 프레임워크(directive) 정의
- 프레임워크 간 계층·참조 관계 정의 (`related` frontmatter)
- 결과 구조:
  ```
  Purpose
    ├ Axis-A: Technology
    │    ├ dir-001 (framework)
    │    └ dir-002 (framework)
    ├ Axis-B: Market
    │    └ dir-003 (framework)
    └ Axis-C: Customer
         └ dir-004 (framework)
  ```

**Step 7: axis_coord 배정 + chart.json 저장**
- 각 원자 vertex에 대해 주도 축 0.8~0.9 / 나머지 0.0~0.1 배정
- `orthogonality.json` 함께 저장 (similarity_matrix 포함)

**chart.json 필수 필드:** `chart_id`, `domain`, `version`, `created_at`, `axes[]` (index/id/label/semantic), `vertices{}` (id/name/axis/axis_coord/assembled_from/directive_path), `metrics` (n_axes/n_vertices/avg_similarity/max_similarity)

실물 예시: `~/.mso-registry/ir-deck/chart.json` 참조.

**스크립트:** `bootstrap_chart.py` — 현재 미구현. LLM이 Step 0~7을 직접 실행하여 `chart.json`을 수동 작성.

**산출물:** `chart.json` + `orthogonality.json` + 각 vertex별 directive MD 파일

**when_unsure**: 축 수 결정이 어려울 때 → 개념 목록의 자연 클러스터 수 기준 결정(보통 5~12개).

---

## Directive Binding 출력 형식

```json
{
  "run_id": "...",
  "bindings": [
    {
      "node_id": "T1",
      "vertex_type": "agent",
      "directives": [
        {
          "directive_id": "dir-001",
          "directive_path": "analysis/dir-001-mece-decomposition.md",
          "type": "framework",
          "binding_rationale": "Fork/Join motif에 MECE 분해 적용"
        }
      ]
    }
  ],
  "unbound_nodes": [],
  "metadata": {
    "created_at": "",
    "registry_path": ""
  }
}
```

상세 스키마: [schemas/directive_binding.schema.json](schemas/directive_binding.schema.json)

---

## Pack 내 관계

| 연결 | 스킬 | 설명 |
|------|------|------|
| ← | `mso-workflow-topology-design` | topology spec의 nodes[].vertex_type, motif를 소비하여 directive 검색 |
| → | `mso-execution-design` | CC-02: directive_binding.json의 bindings[]를 execution_graph 노드에 매핑 |
| ↔ | `mso-process-template` | 참조: process-template의 templates/는 `domain: "mso-governance"` directive로 인식 가능 (합치지 않음) |
| ← | `mso-observability` | 환류: directive 효과 분석 결과 반영 (사용자 승인 필요) |

---

## 상세 파일 참조 (필요 시에만)

| 상황 | 파일 |
|------|------|
| Directive frontmatter 규칙 | [modules/module.directive-taxonomy.md](modules/module.directive-taxonomy.md) |
| Vertex Binding 상세 | [modules/module.vertex-binding.md](modules/module.vertex-binding.md) |
| 출력 스키마 검증 | [schemas/directive_binding.schema.json](schemas/directive_binding.schema.json) |
| Directive frontmatter 스키마 | [schemas/directive.frontmatter.schema.json](schemas/directive.frontmatter.schema.json) |
| Registry 검색 | `python3 {mso-mental-model-design}/scripts/search_directives.py --registry <path> --vertex-type <type>` |
| Directive 등록 | `python3 {mso-mental-model-design}/scripts/register_directive.py --file <path> --registry <path>` |
| Directive Binding 생성 | `python3 {mso-mental-model-design}/scripts/bind_directives.py --topology <path> --registry <path> --output <path>` |
| **[Mode C] 신규 vertex 투영** | `python3 scripts/project_vertex.py --domain <domain> --id <id> --name "<이름>" --axis <축> --coords '<[...]>'` |
| **[Mode D] 차트 최초 생성** | `python3 scripts/bootstrap_chart.py --domain <domain> --purpose "<목적>" --axes '<[{id,label,semantic}]>'` |
| **글로벌 registry 초기화** | `python3 scripts/init_global_registry.py` |

---

## Quick Example

**Input**: topology에 4개 노드 (PlannerAgent, ResearchAgent, Summarizer, Writer), Chain motif

**Phase 1** → registry 검색: PlannerAgent → `dir-005-goal-decomposition` (framework), ResearchAgent → `dir-012-web-research` (instruction), Summarizer → `dir-020-extractive-summary` (prompt), Writer → 후보 없음
**Phase 2** → 3개 자동 바인딩, Writer는 `unbound_nodes[]`에 기록
**Phase 3** → 사용자와 `dir-021-report-writer` (instruction) 신규 작성 → 등록 → 재바인딩
**결과** → `directive_binding.json` 생성 (4/4 바인딩 완료)
