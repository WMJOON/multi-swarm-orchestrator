# module.hitl-feedback

> Phase 5 전용. human-in-the-loop 피드백 수렴 및 goal 산출 상세.

---

## HITL 제시 형식

사용자에게 다음 항목을 포함하여 제시한다:

```
[워크플로우 최적화 결과]
- 워크플로우: {workflow_name}
- 적용된 Automation Level: {automation_level}
- 리포트 경로: {report_path}

[검토 요청]
1. Automation Level이 적절했습니까? (적절 / 상향 권장 / 하향 권장)
2. 개선 제안 중 다음 주기에 반영할 항목을 선택해주세요:
   - [ ] 제안 1
   - [ ] 제안 2
   ...
3. 추가 의견 (선택):
```

---

## 피드백 수렴 규칙

| 피드백 항목 | 처리 방식 |
|-------------|-----------|
| Level 상향 권장 | `next_automation_level = min(current + 10, 30)` |
| Level 하향 권장 | `next_automation_level = max(current - 10, 10)` |
| 적절 | `next_automation_level = current` |
| 개선 제안 선택 | `optimization_directives[]`에 추가 |
| 추가 의견 | `carry_over_issues[]`에 자유 텍스트로 추가 |

---

## human-feedback-logging audit payload

`mso-agent-audit-log`의 `user_feedback` 테이블(v1.3.0 스키마)에 기록한다.
optimizer 전용 필드는 `feedback_text`에 JSON 직렬화하여 저장한다.

**user_feedback 테이블 매핑:**

| user_feedback 컬럼 | optimizer 값 |
|---------------------|-------------|
| `id` | `FB-xxxx` (자동 생성) |
| `date` | 현재 날짜 |
| `user_id` | HITL 응답자 식별자 (없으면 null) |
| `feedback_text` | 아래 JSON 직렬화 |
| `source_ref_path` | `workspace/.mso-context/active/<run_id>/optimizer/levelXX_report.md` |
| `impact_domain` | `"workflow_optimization"` |
| `impact_summary` | `"Level {before} → {after}, {n}건 제안 수렴"` (사람 읽기용 요약) |
| `reversibility` | `"High"` (다음 주기에 재조정 가능) |
| `related_audit_id` | Phase 4에서 기록한 `audit_logs.id` |

**feedback_text JSON 구조:**

```json
{
  "feedback_type": "level_adjustment | suggestion_acceptance | free_text",
  "workflow_name": "<name>",
  "level_before": 10 | 20 | 30,
  "level_after": 10 | 20 | 30,
  "accepted_suggestions": ["제안 1", "제안 2"],
  "rejected_suggestions": ["제안 3"],
  "free_text": "..."
}
```

---

## goal 산출 규칙

피드백 수렴 완료 후 `goal.json`을 생성한다:

```json
{
  "next_automation_level": 10 | 20 | 30,
  "optimization_directives": ["수렴된 제안들"],
  "carry_over_issues": ["미해결 이슈들"],
  "approved_by": "human_feedback"
}
```

---

## 타임아웃 처리

HITL 응답 대기 시간 초과 시:

```json
{
  "next_automation_level": "{현재 automation_level 유지}",
  "optimization_directives": [],
  "carry_over_issues": ["HITL 미응답 — 다음 주기에 재검토 필요"],
  "approved_by": "timeout_fallback"
}
```

---

## 재진입 (Re-entry) 조건

`carry_over_issues`에 항목이 1개 이상 존재하면 다음 워크플로우 실행 완료 시 자동으로 Phase 1이 재트리거된다.
operation-agent가 이 신호를 감지하고 외부 트리거로 Phase 1에 진입한다.
