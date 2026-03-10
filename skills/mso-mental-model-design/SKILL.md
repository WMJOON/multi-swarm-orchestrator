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

---

## 저장 경로

| 경로 | 역할 |
|------|------|
| `{workspace}/.mso-context/vertex_registry/<domain>/` | Directive 저장소 (사용자 확장 가능) |
| `{mso-mental-model-design}/directives/` | 기본 제공 Directive (seed) |
| `{workspace}/.mso-context/active/<run_id>/20_mental-model/directive_binding.json` | Run별 노드↔directive 바인딩 |

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
  --registry {workspace}/.mso-context/vertex_registry \
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
2. `{workspace}/.mso-context/vertex_registry/<domain>/` 하위에 저장
3. frontmatter 유효성 검증 후 등록

**스크립트:**
```
python3 {mso-mental-model-design}/scripts/register_directive.py \
  --file <directive.md> \
  --registry {workspace}/.mso-context/vertex_registry
```

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

---

## Quick Example

**Input**: topology에 4개 노드 (PlannerAgent, ResearchAgent, Summarizer, Writer), Chain motif

**Phase 1** → registry 검색: PlannerAgent → `dir-005-goal-decomposition` (framework), ResearchAgent → `dir-012-web-research` (instruction), Summarizer → `dir-020-extractive-summary` (prompt), Writer → 후보 없음
**Phase 2** → 3개 자동 바인딩, Writer는 `unbound_nodes[]`에 기록
**Phase 3** → 사용자와 `dir-021-report-writer` (instruction) 신규 작성 → 등록 → 재바인딩
**결과** → `directive_binding.json` 생성 (4/4 바인딩 완료)
