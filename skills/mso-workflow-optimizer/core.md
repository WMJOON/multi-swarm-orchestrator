# mso-workflow-optimizer — Core Rules

## Terminology

| 용어 | 정의 |
|------|------|
| Automation Level | 최적화 실행 깊이 (10 / 20 / 30). 높을수록 자동화 비중이 크다 |
| agent-decision | 3-Signal을 종합하여 Automation Level을 결정하는 판단 노드 |
| operation-agent | agent-decision 지시를 수행하고 escalation을 처리하는 실행 노드 |
| decision-reporting-logging | 의사결정·실행 결과를 audit-log와 HITL로 라우팅하는 노드 |
| human-feedback-logging | HITL 피드백을 수렴·기록하고 goal을 생성하는 노드 |

---

## Input Interface

최소 입력:

- `workflow_name` (string, required) — 최적화할 워크플로우 식별자
- `trigger_type` (string) — `"direct"` | `"external"` (operation-agent 경유)
- 선택: `current_metrics`, `last_run_id`, `optimization_goal`

출력 경로 기본값:
- 리포트: `workspace/.mso-context/active/<run_id>/optimizer/levelXX_report.md`
- goal: `workspace/.mso-context/active/<run_id>/optimizer/goal.json`

---

## Output Interface

**decision_output** (Phase 2):
```json
{
  "automation_level": 10 | 20 | 30,
  "rationale": ["Signal A: ...", "Signal B: ...", "Signal C: ..."],
  "escalation_needed": true | false
}
```

**goal** (Phase 5):
```json
{
  "next_automation_level": 10 | 20 | 30,
  "optimization_directives": [],
  "carry_over_issues": [],
  "approved_by": "human_feedback" | "timeout_fallback"
}
```

전체 스키마: [schemas/optimizer_result.schema.json](schemas/optimizer_result.schema.json)

---

## Processing Rules

1. Phase 1에서 `docs/usage/{workflow_name}.md`와 audit_global.db를 반드시 조회한다.
2. Phase 2 agent-decision은 3-Signal(A: 데이터 가용성, B: KPI 지표, C: HITL 피드백 이력)로 레벨을 결정한다.
3. Signal 충돌 시 보수적 레벨(낮은 값) 선택 + `escalation_needed: true`.
4. Phase 3 실행 후 반드시 Phase 4 audit-log 기록을 완료해야 Phase 5로 진행한다.
5. Phase 5 HITL 타임아웃 시 현재 레벨 유지 + `carry_over_issues`에 "HITL 미응답" 기록.

---

## Error Handling

- `workflow_name` 미제공: fail-fast.
- `docs/usage/{}.md` 미존재: audit_snapshot만으로 진행, warning 기록.
- Level 30 실행 실패: Level 20으로 자동 강등 후 재시도, `carry_over_issues`에 기록.
- audit-log 기록 실패: 파이프라인 중단하지 않고 fallback 채널 안내.

---

## Security / Constraints

- `audit_global.db`는 읽기 전용으로 조회하며, 쓰기는 반드시 `mso-agent-audit-log` 스킬을 통한다.
- `docs/usage/{}.md`에 포함된 민감 설정(API key 등)은 로그에 기록하지 않는다.
- 외부 경로를 임포트하지 않는다. pack 내부 상대경로만 사용한다.

---

## when_unsure

- Signal 간 충돌(2개 이상): 보수적 레벨 + escalation_needed=true.
- `workflow_name`이 모호하면: 최근 audit-log의 `workflow_name` Top 3를 제안하고 사용자 선택 요청.
- KPI 기준값 미확인: Signal B를 "중립(neutral)"으로 처리 후 Signal A·C만으로 결정.
