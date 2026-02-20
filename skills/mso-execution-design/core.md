# mso-execution-design — Core Rules (v0.0.3)

## Purpose
`workflow_topology_spec` + `mental_model_bundle`을 버전화된 실행 그래프(`execution_graph`)로 매핑한다.
Git-metaphor 상태 전이 그래프(Versioned State Transition Graph) 기반의 실행 계획을 생성한다.

## Terms
- `execution_graph`: topology 노드를 commit/branch/merge 타입으로 분류한 DAG 구조
- `node_type`: commit(선형), branch(분기), merge(합류) — 엣지 수 기반 자동 분류
- `parent_refs`: 부모 노드 ID 배열. commit: 0-1개, branch: 정확히 1개, merge: 2+개
- `tree_hash_ref`: SHA-256 해시. 계획 시 null, 실행 시 채워짐. root 노드만 null 허용
- `merge_policy`: merge 노드 전용. strategy/scoring_weights(합=1.0)/quorum/manual_review_required
- `fallback_rules[]`: 에러 분류 체계 배열. error_type/severity/action/target_commit/max_retry/requires_human
- `lifecycle_policy`: 스토리지 정리 정책. branch_ttl_days/artifact_retention_days/archive_on_merge/cleanup_job_interval_days
- `mode`: 실행 모드 (`plan`/`default`/`dontAsk`/`bypassPermissions`/`experimental`)
- `handoff_contract`: 노드 간 output/input 전달 규약

## Input Interface
- `workflow_topology_spec`(필수): `nodes`, `edges`, `topology_type`
- `mental_model_bundle`(필수): `bundle_ref`, `node_chart_map`, `local_charts`

## Output Interface
필수 키:
- `run_id`
- `bundle_ref`
- `execution_graph` (노드별: type, bundle_ref, parent_refs, tree_hash_type, tree_hash_ref, model_selection, chart_ids, mode, handoff_contract)
- `fallback_rules[]` (에러 분류 체계 배열)

선택 키:
- `lifecycle_policy`
- `metadata`

## Error Handling
- 입력 파일 누락/포맷 오류: fail-fast
- execution_graph 노드 ID가 topology node id에 없음: fail-fast (CC-01 위반)
- parent_refs 카디널리티 위반: fail-fast
- scoring_weights 합계 ≠ 1.0: fail-fast
- 허용되지 않은 checkpoint: fail-fast
