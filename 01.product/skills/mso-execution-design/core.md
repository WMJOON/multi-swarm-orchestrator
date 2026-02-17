# mso-execution-design — Core Rules

## Purpose
`workflow_topology_spec` + `mental_model_bundle`을 실행 가능한 `execution_plan`으로 매핑한다.

## Terms
- `node_chart_map`: topology node를 chart 집합에 연결
- `mode`: 실행 모드 (`plan`/`default`/`dontAsk`/`bypassPermissions`)
- `handoff_contract`: 노드 간 output/input 전달 규약

## Input Interface
- `workflow_topology_spec`(필수): `nodes`
- `mental_model_bundle`(필수): `bundle_ref`, `node_chart_map`

## Output Interface
필수 키:
- `run_id`
- `bundle_ref`
- `node_chart_map`
- `task_to_chart_map`
- `node_mode_policy`
- `model_selection_policy`
- `handoff_contract`
- `fallback_rules`

## Error Handling
- 입력 파일 누락/포맷 오류: fail-fast
- `node_chart_map` 유효성 실패: fail-fast
- 허용되지 않은 checkpoint: fail-fast
