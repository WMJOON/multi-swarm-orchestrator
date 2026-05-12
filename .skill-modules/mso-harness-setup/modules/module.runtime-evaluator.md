# Module: Runtime Evaluator

## Goal

Runtime Evaluator는 event stream의 안정성 신호를 계산하여 policy engine과 escalation router에 전달한다.

---

## Signals

| Signal | Type | Meaning |
|------|------|------|
| `entropy_delta` | number | 직전 평가 대비 semantic drift proxy |
| `relevance_score` | number | intent/objective와 현재 event의 관련도 |
| `topology_stability` | enum | `stable`, `degraded`, `unstable` |
| `loop_risk` | number | 반복 실행 또는 recursive traversal 위험 |
| `boundary_status` | enum | `inside`, `near_boundary`, `violation` |

---

## Evaluation Rules

| Rule | Trigger | Suggested action |
|------|------|------|
| High entropy | `entropy_delta > threshold` | stronger model route or human review |
| Low relevance | `relevance_score < threshold` | branch termination candidate |
| Unstable topology | repeated transition failure | checkpoint + review |
| Loop risk | same capability/target repeats over limit | bounded traversal stop |
| Boundary violation | ontology or capability out of allowed scope | block or governance review |

---

## GraphRAG / Multi-hop Optimization

For GraphRAG and multi-hop traversal, evaluator must track:

- visited node/path signatures
- repeated relation expansion
- ontology boundary drift
- evidence relevance propagation
- branch fan-out depth
- checkpoint interval

---

## Evaluator Output Pattern

```yaml
semantic:
  entropy_delta: 0.14
  relevance_score: 0.88
  topology_stability: stable
  loop_risk: 0.08
  boundary_status: inside
governance:
  escalation_triggered: false
  requires_review: false
```

---

## when_unsure

If signal calculation is not implemented:

1. Set evaluator status to `not_evaluated`.
2. Preserve raw event and adapter output.
3. Do not fabricate metric values.
4. Prefer `review` over `allow` for high-risk capability events.
