# module.loop_risk

## Purpose
루프/재귀/반복에서 발생 가능한 위험을 식별하고 완화 전략을 기록한다.

## Risk Types
- 과도한 확장, 종료 조건 불명확성, 의존 순환

## Output
`loop_risk_assessment`는 노드별로 아래 객체를 유지한다.

```json
{
  "loop_type": "loop_infinite_risk",
  "severity": "medium",
  "where": "T3",
  "mitigation": ["stop_condition 추가", "최대 반복 횟수 제한"]
}
```
