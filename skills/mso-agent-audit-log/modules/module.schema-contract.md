# module.schema-contract

## 질문 축

- 로그 스키마의 소유권과 변경 경로는 어디까지인가?

## 규칙

- SoT 스키마는 `schema/init.sql`, `schema/migrate_v1_to_v1_1.sql`로 단일 관리.
- 다른 스킬은 스키마를 재정의할 수 없다.
- `task_name`, `status`, `action`, `id` 필드는 비워둘 수 없다.
- 결정/증거 엔티티(`decisions`, `evidence`, `impacts`)는 `id` 기반의 연결 관계를 보존한다.
- 스키마 버전은 `metadata.schema_version`으로 기록한다.

---

## Harness Convention v0.1.2 (MUST)

### 4개 기본 테이블

| 테이블 | 기록 주체 | 내용 |
|--------|---------|------|
| `execution_events` | mso-agent-collaboration | 에이전트 소환/완료 |
| `compression_events` | adapter (각 provider) | compression 감지 |
| `guard_events` | Guard | REJECT / ESCALATE 판정 |
| `handoff_events` | Spawner | handoff_context 수신 |

### compression_event 스키마 (MUST)

```yaml
compression_event:
  event_id: "cmp-<timestamp>"
  run_id: <run_id>
  timestamp: <ISO8601>

  agent_id: <agent_id>
  phase: <phase_name>
  vertex_sequence: [...]              # 현재 에이전트가 처리한 vertex 순서
  compression_at_vertex: <vertex>     # 압축 감지 시점의 vertex

  step: <int>
  message_count: <int>
  estimated_context_ratio: <float>    # 제공 가능한 경우

  # optimizer가 사후 채움 — 기록 시점에는 null
  quality_degraded: null
  reasoning_broken: null
```

- compression 감지 시 실행을 멈추지 않고 기록만 한다 (MUST NOT 실행 중단)
- `message_count`만으로 기록해도 충분 (감지 어려운 경우)

### audit_ref 포인터 패턴 (MUST)

에이전트 context에는 audit 원문이 아닌 `audit_ref` 포인터만 유지한다.

```
포맷: {run_id}#{step}
예:   run-20260331-001#step12
```

```
에이전트 context  →  audit_ref: "run-20260331-001#step7"
audit_global.db  →  전체 실행 기록 (compression_events, guard_events, ...)
```
