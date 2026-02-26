---
name: mso-observability
version: 0.0.2
run_input: "audit log db, behavior feed"
run_output: "observability callback events"
status_model: "pass | warn | fail"
---

# Core

## 목적
실행 SoT(`mso-agent-audit-log`)를 소비해 신호를 분류하고, HITL 체크포인트 이벤트를 정형화해 다음 스텝(`mso-skill-governance`)에 전달한다.

## 입력
- `run_id` / `artifact_uri`
- SoT DB 경로 (기본: `{workspace}/.mso-context/active/<run_id>/50_audit/agent_log.db`)
- 증거 이벤트 경로(옵션: `{workspace}/.mso-context/active/<run_id>/60_observability/*.jsonl`)

## 출력
- 최소 형식의 callback 이벤트:

```json
{
  "event_type": "improvement_proposal | anomaly_detected | periodic_report | hitl_request",
  "checkpoint_id": "HC-YYYYMMDD-NNN",
  "payload": {
    "target_skills": ["mso-workflow-topology-design", "mso-mental-model-design", "mso-execution-design", "mso-skill-governance"],
    "severity": "info | warning | critical",
    "message": "..."
  },
  "retry_policy": { "max_retries": 2, "backoff_seconds": 10, "on_retry": "queue" },
  "correlation": {
    "run_id": "20260217-msoobs-observability",
    "artifact_uri": "{workspace}/.mso-context/active/20260217-msoobs-observability/30_execution/execution_plan.json"
  },
  "timestamp": "2026-...Z"
}
```

## 인바운드-아웃바운드 정책

- 입력: SQLite SoT 읽기 전용.
- 출력: `{workspace}/.mso-context/active/<run_id>/60_observability/` 아래 `callback-*` 파일.
- 자동 반영(실제 토폴로지 수정)은 수행하지 않고 제안만 남긴다.

## 실패/휴리스틱

- DB 미존재: `status=warn` 이벤트를 남기고 종료.
- 신호 미탐지: `event_type=periodic_report`로 빈 요약 남김.
- Critical 이벤트는 48h 미응답 시 `requires_manual_confirmation`로 게이트 상향.
