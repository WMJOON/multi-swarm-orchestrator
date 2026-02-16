# module.node-design

## Purpose
각 노드의 `label`, `theta_gt_band`, `rsv_target`, `assigned_dqs`를 산출한다.

## Node Rules
- `nodes[].id`는 `T1`, `T2` ... 형식.
- `theta_gt_band`는 `wide`/`moderate`/`narrow` 중 하나.
- `assigned_dqs`는 해당 노드가 닫아야 할 DQ 리스트.
- `rsv_target`은 0.0~1.0 범위 추정치.

## Output Pattern
```json
{
  "id": "T1",
  "label": "Goal decomposition",
  "theta_gt_band": "moderate",
  "rsv_target": 0.42,
  "assigned_dqs": ["DQ1"]
}
```
