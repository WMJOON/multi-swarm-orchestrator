# module.agent-team

> mso-workflow-optimizer의 멀티 에이전트 아키텍처.
> Proactive Async + Jewels 패턴의 구현 명세.
>
> - **provider-free 구현**: `mso-agent-collaboration` 스킬의 티켓 dispatch 활용
> - **Claude Code 네이티브 구현**: Agent Teams 직접 사용

---

## mso-agent-collaboration 기반 구현 (provider-free)

`mso-agent-collaboration`의 `dispatch_mode`와 `handoff_payload`로 teammates를 표현한다.

### Teammate → 티켓 매핑

| Teammate | dispatch_mode | tags | 비고 |
|----------|--------------|------|------|
| jewel-producer | `swarm` | `worker`, `persistent` | WATCH 티켓. 완료하지 않고 루프 유지 |
| decision-agent | `run` | `worker` | DECIDE_LEVEL 티켓. on-demand |
| level-executor | `batch` | `worker` | EXECUTE_L{N} 티켓. decision 완료 후 unblock |
| hitl-coordinator | `run` | `review` | HITL 티켓. executor 완료 후 unblock |

### handoff_payload 확장 필드

```json
{
  "run_id": "<run_id>",
  "task_id": "DECIDE_LEVEL_{run_id}",
  "owner_agent": "decision-agent",
  "role": "worker",
  "objective": "3-Signal + Jewels → Automation Level 결정",
  "jewels": ["JWL-opt-..."],
  "workflow_name": "<name>",
  "current_metrics": {}
}
```

Jewels는 jewel-producer 티켓의 출력으로 저장(`{workspace}/.mso-context/jewels/opt/`)되며, decision-agent 티켓의 `handoff_payload.jewels`로 참조된다.

---

## 팀 아키텍처

```
optimizer-lead (delegate mode)
    ├── jewel-producer     [background, persistent] — 상시 모니터링 + Jewel 생성
    ├── decision-agent     [on-demand]              — Phase 2: Level 판단
    ├── level-executor     [on-demand]              — Phase 3: Level 실행
    └── hitl-coordinator   [on-demand]              — Phase 5: HITL + goal
```

**핵심 원칙**: `optimizer-lead`는 delegate mode로만 동작한다. 직접 분석·실행하지 않고 teammates에게 위임한다.

---

## Teammate 정의

### optimizer-lead

| 항목 | 값 |
|------|-----|
| 역할 | 팀 오케스트레이터. task 생성·할당·합성 전담 |
| mode | delegate (coordination-only) |
| 책임 | jewel 심각도 평가 → 풀 최적화 실행 여부 결정 → teammates 소환 |

**lead의 jewel 수신 처리 규칙:**

| jewel severity | 행동 |
|---------------|------|
| `high` | 즉시 decision-agent 소환 |
| `medium` | 동일 workflow jewel 2건 누적 시 decision-agent 소환 |
| `low` | 누적만, 다음 명시적 최적화 요청 시 Phase 1에 주입 |

---

### jewel-producer

| 항목 | 값 |
|------|-----|
| 역할 | `audit_global.db` 상시 모니터링 + Jewel 생성 |
| 실행 방식 | background (비동기) |
| model | haiku (비용 최소화) |
| tools | Read, Bash, Write |
| permissionMode | dontAsk |

**모니터링 대상:**
- `audit_logs` 테이블: 최근 N개 이벤트 기준 KPI 추이
- `user_feedback` 테이블: HITL 미응답 누적 여부
- 동일 `work_type` 반복 실패 패턴

**Jewel 생성 조건 (노이즈 방지):**

| 조건 | type | severity |
|------|------|----------|
| KPI 3회 연속 하락 또는 threshold -10% 이탈 | `kpi_drift` | high |
| 동일 workflow Level 30 실행 후 KPI 미개선 2회 | `level_escalation` | medium |
| 동일 에러 패턴 3회 이상 반복 | `pattern_alert` | medium |
| llm-as-a-judge samplingRatio < 0.05 누적 | `sampling_adjust` | low |

**조건 미달 시 Jewel 생성 금지** (노이즈 방지).

**Jewel 포맷:**
```json
{
  "jewel_id": "JWL-opt-{YYYYMMDD-HHmmss}",
  "workflow_name": "<name>",
  "type": "kpi_drift | level_escalation | pattern_alert | sampling_adjust",
  "severity": "high | medium | low",
  "content": "<감지 내용 1줄 요약>",
  "recommended_action": "<권고 행동>",
  "created_at": "<ISO8601>",
  "consumed": false
}
```

**저장 경로:** `{workspace}/.mso-context/jewels/opt/{jewel_id}.json`

**lead에게 메시지 (Jewel 생성 시):**
```
[jewel-producer → optimizer-lead]
JWL-opt-20260310-143022 생성
workflow: search-ai-seo | type: kpi_drift | severity: high
content: precision 87.2% → 81.4%, 3회 연속 하락
```

**지속 실행 메커니즘**: `WATCH_{workflow_name}` 태스크를 완료 처리하지 않고 루프로 계속 실행한다. `TeammateIdle` 훅이 `exit 2`로 재활성화하므로 idle 전환 시에도 모니터링이 유지된다. 태스크는 lead가 명시적으로 종료를 지시할 때만 완료 처리한다.

---

### decision-agent

| 항목 | 값 |
|------|-----|
| 역할 | Phase 2: 3-Signal + Jewels → Automation Level 결정 |
| 실행 방식 | foreground, on-demand |
| model | inherit |
| tools | Read, Bash |

**입력**: lead가 전달하는 `{ workflow_name, current_metrics, jewels[], audit_snapshot }`

**Jewel → Signal C 반영 규칙:**

| 수신 Jewel | Signal C 보정 |
|-----------|--------------|
| `kpi_drift` (high) | +10 추가 (Level 상향 압력) |
| `level_escalation` (medium) | +10 추가 |
| `pattern_alert` (medium) | escalation_needed=true 강제 |
| `sampling_adjust` (low) | Signal C 보정 없음, Phase 3 메타로만 전달 |

**lead에게 메시지 (결정 완료 시):**
```
[decision-agent → optimizer-lead]
Level 결정: 30
rationale: Signal A(L30) + Signal B(KPI미달) + Signal C(jewel kpi_drift +10)
escalation_needed: false
jewels_consumed: [JWL-opt-20260310-143022]
```

---

### level-executor

| 항목 | 값 |
|------|-----|
| 역할 | Phase 3: Level 10/20/30 실행 + report.md 생성 |
| 실행 방식 | foreground, on-demand |
| model | Level 10→haiku / Level 20→sonnet / Level 30→inherit |
| tools | Read, Bash, Write |

**입력**: lead가 전달하는 `{ automation_level, workflow_name, run_id, sampling_adjust_hint? }`

**audit logging 책임**: level-executor가 report.md 생성 후 `mso-agent-audit-log`를 통해 `audit_global.db`에 기록한다. delegate mode의 lead는 직접 기록하지 않는다.

**audit payload:**
```json
{
  "run_id": "<run_id>",
  "artifact_uri": ".mso-context/active/<run_id>/optimizer/levelXX_report.md",
  "status": "completed",
  "work_type": "workflow_optimization",
  "metadata": { "automation_level": 10|20|30, "workflow_name": "<name>", "jewels_consumed": [] }
}
```

**lead에게 메시지 (완료 시):**
```
[level-executor → optimizer-lead]
Level 30 실행 완료 + audit 기록 완료
report: .mso-context/active/{run_id}/optimizer/level30_report.md
jewels_consumed: [JWL-opt-20260310-143022]
```

---

### hitl-coordinator

| 항목 | 값 |
|------|-----|
| 역할 | Phase 5: 사용자에게 report 제시 → 피드백 수렴 → goal.json 생성 |
| 실행 방식 | foreground, on-demand |
| model | inherit |
| tools | Read, Write |

**lead에게 메시지 (완료 시):**
```
[hitl-coordinator → optimizer-lead]
goal 생성 완료
next_automation_level: 30
directives: ["samplingRatio 0.2로 상향", "evaluation.py 임계값 재조정"]
```

---

## 공유 Task List

| Task ID | 담당 | 상태 전이 |
|---------|------|----------|
| `WATCH_{workflow_name}` | jewel-producer | 완료 즉시 재클레임 (persistent) |
| `DECIDE_LEVEL_{run_id}` | decision-agent | pending → in_progress → completed |
| `EXECUTE_L{N}_{run_id}` | level-executor | `DECIDE_LEVEL` 완료 후 unblocked |
| `HITL_{run_id}` | hitl-coordinator | `EXECUTE_L{N}` 완료 후 unblocked |

**의존 관계:**
```
WATCH (상시)
    ↓ jewel 생성 시
DECIDE_LEVEL
    ↓ 완료 시 unblock
EXECUTE_L{N}
    ↓ 완료 시 unblock
HITL
```

---

## 팀 초기화 (lead 지시문)

```
Create an agent team for mso-workflow-optimizer.

Teammates:
- jewel-producer: background agent that monitors audit_global.db for
  the target workflow and generates jewels. Run proactively. Claim
  WATCH_{workflow_name} task and re-claim it after each completion.
- decision-agent: on-demand. Waits for lead assignment.
- level-executor: on-demand. Waits for lead assignment.
- hitl-coordinator: on-demand. Waits for lead assignment.

Lead stays in delegate mode. Do not implement tasks yourself.
```

---

## 전체 흐름 (명시적 최적화 요청 시)

```
1. 사용자: "search-ai 최적화해줘"
2. lead: jewel-producer에게 broadcast → 해당 workflow 미소비 jewels 수집 요청
3. lead: DECIDE_LEVEL 태스크 생성 (jewels 주입) → decision-agent 할당
4. decision-agent: 3-Signal + jewels → Level 결정 → lead에게 메시지
5. lead: EXECUTE_L{N} 태스크 생성 → level-executor 할당
6. level-executor: report.md 생성 → lead에게 메시지
7. level-executor: audit_global.db 기록 (Phase 4 포함, delegate lead 대신 직접 수행)
8. lead: HITL 태스크 생성 → hitl-coordinator 할당
9. hitl-coordinator: 사용자 피드백 → jewels consumed 마킹 → goal.json → lead에게 메시지
10. lead: 결과 합성 → 팀 대기 상태
```

## 전체 흐름 (jewel-producer 자율 감지 시)

```
1. jewel-producer: KPI drift 감지 → JWL 생성 → lead에게 메시지 (severity: high)
2. lead: severity 평가 → high이면 즉시 3~9번 실행
   (medium이면 동일 workflow jewel 2건 누적까지 대기)
3. 이후 동일
```

---

## Hook 설정 (TeammateIdle)

`TeammateIdle` 훅: jewel-producer가 idle 전환 직전에 실행. `exit 2`로 종료하면 피드백 메시지를 teammate에게 전달하며 계속 실행시킨다.

```json
{
  "hooks": {
    "TeammateIdle": [
      {
        "matcher": "jewel-producer",
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Continue monitoring audit_global.db. Run another monitoring cycle and check for new jewel conditions.' >&2 && exit 2"
          }
        ]
      }
    ]
  }
}
```

**`exit 2` 동작**: Claude Code Agent Teams 문서 기준, `TeammateIdle`에서 exit 2 반환 시 teammate에게 stderr 메시지를 피드백으로 전달하고 idle 전환을 차단하여 실행을 유지한다.
