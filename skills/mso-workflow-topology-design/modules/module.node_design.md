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
  "assigned_dqs": ["DQ1"],
  "execution_model": "single_instance",
  "optimizer_hint": {
    "suggested_split_after": null,
    "compression_rate": null,
    "last_optimized": null
  }
}
```

`execution_model`은 모든 노드에 필수(MUST). `optimizer_hint`는 설계 시 반드시 null로 초기화(MUST).
`bus` 선택 시 `bus.pattern`, `bus.merge_policy`, `bus.merge_agent` 추가 필요.
