# module.vertex-binding

## Purpose

Topology 노드에 directive를 바인딩하는 검색·선택·매핑 규칙을 정의한다.

---

## 검색 순서

1. `applicable_vertex_types`에 노드의 `vertex_type` 포함 여부
2. `applicable_motifs`에 노드 소속 `motif` 포함 여부
3. `domain` 일치
4. `taxonomy_path` 깊이 (구체적일수록 우선)

모든 조건은 AND가 아닌 가중 점수 방식:
```
match_score = vertex_type_match × 0.4 + motif_match × 0.3 + domain_match × 0.2 + depth × 0.1
```

---

## 바인딩 규칙

| 후보 수 | 처리 |
|---------|------|
| 0 | `general` domain fallback → 재검색. 여전히 0이면 `unbound_nodes[]` 기록 |
| 1 | 자동 바인딩 |
| 2+ | match_score 최고 1개 자동 선택. 동점 시 사용자 확인 |

### 다중 바인딩

1 node에 여러 directive를 바인딩할 수 있다 (다중 렌즈).
예: PlannerAgent에 `framework: MECE` + `instruction: output-format-rules` 동시 바인딩.

다중 바인딩 시 `type`이 다른 directive 조합을 권장:
- framework + instruction: 사고 모델 + 실행 규칙
- framework + prompt: 분석 관점 + 생성 템플릿

---

## 출력: directive_binding.json

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
          "binding_rationale": "..."
        }
      ]
    }
  ],
  "unbound_nodes": ["T4"],
  "metadata": {
    "created_at": "...",
    "registry_path": "..."
  }
}
```

---

## CC-02 호환

`mso-execution-design`는 `directive_binding.json`의 `bindings[]`를 읽어
`execution_graph` 노드의 `directive_refs`에 매핑한다.
