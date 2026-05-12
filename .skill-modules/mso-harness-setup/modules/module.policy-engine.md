# Module: Policy Engine

## Goal

Policy Engine은 canonical event와 YAML runtime config를 입력으로 받아 allow/review/block/escalate 결정을 내린다.

---

## Policy Decision

| Decision | Meaning |
|------|------|
| `allow` | 실행 계속 |
| `review` | HITL 또는 governance review 필요 |
| `block` | 실행 차단 |
| `escalate` | 상위 route/model/provider/human으로 전환 |

---

## Policy Matching Keys

정책은 provider tool name이 아니라 다음 stable key로 매칭한다.

- `lifecycle.phase`
- `capability.category`
- `capability.risk_level`
- `execution.status`
- `semantic.entropy_delta`
- `semantic.topology_stability`
- `governance.requires_review`

---

## Policy Actions

| Action | Description |
|------|------|
| `inject_context` | 실행 전 security, repository, ontology, task constraints 주입 |
| `evaluate` | 실행 후 evaluator signal 계산 |
| `checkpoint` | 복구 가능한 state snapshot 생성 |
| `retry` | bounded retry 수행 |
| `route` | escalation router로 전달 |
| `audit` | canonical event 기록 |
| `terminate_branch` | low relevance/high loop risk branch 종료 후보 생성 |

---

## Guard Principles

- high risk capability는 pre-action policy를 먼저 통과해야 한다.
- destructive action은 provider-native tool name이 아니라 capability/risk 조합으로 판정한다.
- evaluation signal이 threshold를 넘으면 escalation은 자동 실행 가능하지만, topology 변경은 human approval을 요구한다.
- retry는 반드시 bounded여야 하며, retry 횟수는 audit event에 남긴다.

---

## YAML Policy Pattern

```yaml
policies:
  - match:
      capability: filesystem.execute
      risk_level: high
    pre_action:
      inject_context:
        - security_policy
        - repository_constraints
      decision: review
    post_action:
      evaluate:
        - topology_stability
        - semantic_entropy
      escalation:
        trigger:
          entropy_delta_gt: 0.3
        route_to:
          class: stronger_reasoning_model
```
