# module.hitl-interaction

## 규칙

- `anomaly_detected` 또는 심각도 `critical` 신호 발생 시 `hitl_request` 이벤트를 생성한다.
- `scheduled` 모드에서는 요약(`periodic_report`)을 발행한다.
- event payload에는 `correlation`과 최소 `retry_policy`를 항상 포함한다.
