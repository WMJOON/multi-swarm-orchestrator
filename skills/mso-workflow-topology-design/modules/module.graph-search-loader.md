# module.graph-search-loader

> Source: v0.0.7-2 §3 Graph Search Loader
> `mso-workflow-topology-design` Mode B의 상세 구현 참조.

## Purpose

저장된 워크플로우 레지스트리에서 Intent 기반 검색으로 기존 Topology를 불러온다.
신규 설계(Mode A) 없이 실행 가능한 워크플로우를 즉시 반환한다.

---

## 레지스트리 데이터 구조

```json
{
  "workflow_id": "wf-001",
  "intent_embedding": [...],
  "intent_text": "시장 조사 보고서 작성",
  "topology_motif": "chain",
  "topology_type": "linear",
  "vertex_template": [
    {"id": "T1", "label": "PlannerAgent", "vertex_type": "agent"},
    {"id": "T2", "label": "ResearchAgent", "vertex_type": "agent"},
    {"id": "T3", "label": "Summarizer", "vertex_type": "model"},
    {"id": "T4", "label": "Writer", "vertex_type": "skill"}
  ],
  "edges": [
    {"from": "T1", "to": "T2"}, {"from": "T2", "to": "T3"}, {"from": "T3", "to": "T4"}
  ],
  "execution_metrics": {
    "frequency": 12,
    "success_rate": 0.95,
    "avg_cost_usd": 0.03,
    "topology_stability": 0.92
  },
  "domain_tags": ["research", "report"],
  "created_at": "",
  "updated_at": ""
}
```

---

## 검색 점수 계산

```
search_score = similarity_score × 0.6 + success_rate × 0.4
```

| 조건 | 처리 |
|------|------|
| search_score ≥ 0.7 | 자동 선택 |
| 0.6 ≤ search_score < 0.7 | 사용자 확인 요청 |
| search_score < 0.6 | Mode A fallback |

---

## Vertex Binding 규칙

| vertex_type | 매핑 소스 |
|-------------|----------|
| `agent` | 현재 환경 사용 가능한 Agent 목록 |
| `skill` | `{workspace}/.mso-context/available_skills.json` |
| `tool` | 현재 세션 Tool 목록 |
| `model` | `{mso-workflow-topology-design}/configs/model-catalog.yaml` |

바인딩 실패 Vertex는 `unbound_vertices[]`에 기록하고 Mode A fallback 트리거.

---

## 스크립트 참조

| 작업 | 스크립트 |
|------|---------|
| 레지스트리 검색 | `{mso-workflow-topology-design}/scripts/graph_search.py --intent "..." --top-k 3 --registry <path>` |
| 레지스트리 등록/갱신 | `{mso-workflow-topology-design}/scripts/registry_upsert.py --workflow-spec <path> --intent "..." --registry <path>` |
| execution_metrics 갱신 | `{mso-workflow-topology-design}/scripts/registry_upsert.py --workflow-id <id> --metrics <json> --registry <path>` |

---

## 레지스트리 경로

`{workspace}/.mso-context/workflow_registry.json`
