# module.handoff

## Purpose
`outputs/workflow_topology_spec.json`을 다음 스킬들이 바로 소비할 수 있게 포맷 정합성 체크를 수행한다.

## Required keys
- `run_id`
- `nodes`
- `edges`
- `topology_type`
- `rsv_total`

## Handoff
- 출력은 항상 UTF-8 JSON.
- `edges`는 존재하면 `from`,`to` 모두 node id 유효성 검증.
