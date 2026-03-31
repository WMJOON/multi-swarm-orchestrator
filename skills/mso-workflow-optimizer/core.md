# mso-workflow-optimizer — Core Rules

## Terminology

| 용어 | 정의 |
|------|------|
| Automation Level | 최적화 실행 깊이 (10 / 20 / 30). 높을수록 자동화 비중이 크다 |
| agent-decision | 3-Signal을 종합하여 Automation Level을 결정하는 판단 노드 |
| operation-agent | agent-decision 지시를 수행하고 escalation을 처리하는 실행 노드 |
| decision-reporting-logging | 의사결정·실행 결과를 audit-log와 HITL로 라우팅하는 노드 |
| human-feedback-logging | HITL 피드백을 수렴·기록하고 goal을 생성하는 노드 |
| process-optimizing | 프로세스 실행·분석·평가를 반복하며 워크플로우를 점진적으로 개선하는 운영 모듈 |
| llm-as-a-judge | LLM을 Judge로 활용하여 데이터를 라벨링하고 품질을 정량 검증하는 평가 모듈 |
| labeling-rule | llm-as-a-judge에서 LLM에게 전달하는 라벨링 기준 문서 (버전 관리: vX.X) |
| samplingRatio | 데이터 샘플링 비율 파라미터. 초기 0.1, HITL 피드백으로 조정 |
| TF-PN | True/False Positive/Negative 혼동 행렬. llm-as-a-judge 라벨링 품질 정량 지표 |

---

## Input Interface

최소 입력:

- `workflow_name` (string, required) — 최적화할 워크플로우 식별자
- `trigger_type` (string) — `"direct"` | `"external"` (operation-agent 경유)
- 선택: `current_metrics`, `last_run_id`, `optimization_goal`

출력 경로 기본값:
- 리포트: `{workspace}/.mso-context/active/<run_id>/optimizer/levelXX_report.md`
- goal: `{workspace}/.mso-context/active/<run_id>/optimizer/goal.json`

LLM API ENV( `llm-as-a-judge` 실행 시):
- `LLM_API_PROVIDER` (optional, default: `openai`)
- `LLM_API_KEY` (preferred)
- provider fallback key: `OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | `GOOGLE_API_KEY`
- optional: `LLM_API_BASE_URL`, `LLM_MODEL`
- skill-local env template: `{mso-workflow-optimizer}/.env.example`
- runtime env file (recommended): `{mso-workflow-optimizer}/.env.local`
- model catalog: `{mso-workflow-optimizer}/configs/llm-model-catalog.yaml`
- model selector script: `{mso-workflow-optimizer}/scripts/select_llm_model.py`

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

## Harness Convention v0.1.2 (MUST)

### Compression Feed 분석

optimizer는 `audit_global.db`의 두 테이블을 기반으로 분할 제안을 생성한다.

```sql
-- compression_events: 압축 발생 이력
SELECT phase, vertex_sequence, compression_at_vertex, message_count
FROM compression_events
WHERE run_id = ?

-- guard_events: Guard 판정 이력
SELECT phase, guard_result, reason
FROM guard_events
WHERE run_id = ?
```

### optimization_proposal 출력 포맷 (MUST)

```yaml
optimization_proposal:
  target_node: <node_id>
  workflow: <workflow_yaml_path>
  current_vertex_sequence: [...]
  proposed_split:
    - group_1: [...]
    - group_2: [...]
  rationale: "<분할 근거 1~2줄>"
  compression_rate_before: <float>
  compression_rate_projected: <float>
  requires_human_approval: true       # 항상 true (MUST)
```

- optimizer 제안은 **자동으로 topology를 변경하지 않는다** (MUST NOT)
- 설계자의 HITL 승인 후 `workflow.yaml`의 `optimizer_hint`를 갱신한다
- `requires_human_approval`는 항상 `true` (MUST)

## Processing Rules

1. Phase 1에서 `docs/usage/{workflow_name}.md`와 audit_global.db를 반드시 조회한다.
2. Phase 1에서 `compression_events`, `guard_events` 테이블을 추가로 조회한다 (MUST).
3. Phase 2 agent-decision은 3-Signal(A: 데이터 가용성, B: KPI 지표, C: HITL 피드백 이력)로 레벨을 결정한다.
4. Signal 충돌 시 보수적 레벨(낮은 값) 선택 + `escalation_needed: true`.
5. Phase 3 실행 후 반드시 Phase 4 audit-log 기록을 완료해야 Phase 5로 진행한다.
6. Phase 5 HITL 타임아웃 시 현재 레벨 유지 + `carry_over_issues`에 "HITL 미응답" 기록.
7. compression_events 분석 결과 분할 필요 시 `optimization_proposal` 포맷으로 출력한다 (MUST).

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
- llm-as-a-judge의 `labeling-rule-vX.X.md`는 이전 버전을 삭제하지 않고 보존한다.
- `llm-as-a-judge` API 키 조회 순서는 `LLM_API_KEY` 우선, 미설정 시 provider별 키 fallback을 사용한다.
- 유효한 API 키가 없으면 fail-fast 하며, 키 원문은 로그/리포트/audit payload에 절대 기록하지 않는다.

---

## when_unsure

- Signal 간 충돌(2개 이상): 보수적 레벨 + escalation_needed=true.
- `workflow_name`이 모호하면: 최근 audit-log의 `workflow_name` Top 3를 제안하고 사용자 선택 요청.
- KPI 기준값 미확인: Signal B를 "중립(neutral)"으로 처리 후 Signal A·C만으로 결정.
