# module.execution-graph

> v0.0.3: execution_graph DAG 구성 규칙

## 노드 타입 분류 로직

topology의 edges를 분석하여 각 노드의 타입을 자동 분류한다.

| 조건 | 타입 | 설명 |
|------|------|------|
| incoming edges ≥ 2 | `merge` | Fan-in 합류 노드 |
| outgoing edges ≥ 2 | `branch` | Fan-out 분기 노드 |
| 그 외 | `commit` | 선형 실행 노드 |

## parent_refs 카디널리티 검증

| 타입 | parent_refs 길이 | 검증 규칙 |
|------|------------------|-----------|
| `commit` | 0 또는 1 | root 노드는 0, 그 외 1 |
| `branch` | 정확히 1 | 분기 원점 노드 1개 |
| `merge` | 2 이상 | 합류 대상 브랜치 최소 2개 |

## tree_hash_ref 초기화 규칙

- 계획 생성 시: 모든 노드의 `tree_hash_ref`를 `null`로 설정
- 실행 시: Execution Agent가 산출물을 SHA-256 해싱하여 채움
- root 노드만 실행 후에도 `null` 허용 (부모 상태 없음)
- `tree_hash_type`은 항상 `"sha256"`

## 그래프 무결성 규칙

1. execution_graph의 모든 node_id는 topology의 node id에 존재해야 함 (CC-01)
2. parent_refs의 모든 참조는 execution_graph 내 유효한 node_id여야 함
3. 순환 참조(Cycle) 금지 — DAG 속성 유지
4. 고아 노드(연결 없는 노드) 허용하되, 경고(warning) 기록
