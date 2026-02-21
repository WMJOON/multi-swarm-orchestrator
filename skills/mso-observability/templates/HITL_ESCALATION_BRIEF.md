---
workspace-id: sandbox|id
run-id: id
escalation-id: id
gate-type: H1|H2
urgency: normal|high|critical
source-node: node-id
correlation: correlation-id
update-at:
update-by:
create-at:
create-by:
---

# {work name} HITL Escalation Brief

## Trigger
에스컬레이션이 발생한 원인을 서술한다.
error_type, severity, 관련 노드 정보를 포함해야 한다.

- Gate Type: H1|H2
- Error Type: schema_validation_error|hallucination|timeout|hitl_block
- Severity: low|medium|high|critical
- Source Node: {node-id}
- Trigger Condition:

---

## Current State
현재 실행 상태를 요약한다.
사람이 판단에 필요한 최소한의 맥락만 포함한다.

### Completed Nodes
| Node ID | Status | tree_hash_ref |
|---------|--------|---------------|
|         |        |               |

### Blocking Point
- 블로킹 노드: {node-id}
- 블로킹 원인:
- 마지막 성공 snapshot: {tree_hash_ref}

### Affected Downstream
이 블로킹으로 인해 대기 중인 하류 노드를 나열한다.

-

---

## Options
사람이 선택할 수 있는 행동을 나열한다.
각 옵션의 예상 결과와 리스크를 명시해야 한다.

### Option 1: Resume
- 행동: 현재 상태에서 실행을 재개한다.
- 조건: {어떤 조건이 해소되어야 하는가}
- 리스크:

### Option 2: Retry with Parameters
- 행동: 파라미터를 변경하여 재시도한다.
- 변경 대상: {model, temperature, timeout 등}
- 리스크:

### Option 3: Abort
- 행동: 현재 Run을 중단하고 마지막 안정 상태로 복귀한다.
- Fallback target: {tree_hash_ref}
- 리스크:

---

## Required Decision
사람에게 구체적으로 어떤 판단을 요청하는지 명시한다.
모호한 요청("확인해 주세요")이 아니라, 선택지와 판단 기준을 제공해야 한다.

-

---

## Deadline / Fallback
응답 기한과 미응답 시 기본 행동을 정의한다.

- 응답 기한: {ISO8601 timestamp 또는 상대 시간}
- 미응답 시 행동: {retry|abort|escalate to next level}
- 미응답 시 근거: retry_policy 또는 fallback_rules 참조
