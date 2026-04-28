# module.model-monitoring

> 배포된 경량 모델의 성능을 모니터링하고, 성능 저하·승격 후보를 신호로 발생시킨다.

---

## 역할

`mso-model-optimizer`가 배포한 경량 모델(deploy_spec.json이 존재하는 Smart Tool)의 프로덕션 성능을 추적한다. `module.observation-policy`가 일반 실행 패턴을 관찰하는 반면, 이 모듈은 **모델 inference 품질**에 특화된 모니터링을 수행한다.

---

## 수집 지표

| 지표 | 정의 | 데이터 소스 | 수집 방식 |
|------|------|------------|-----------|
| `rolling_f1` | 최근 N건(기본 100) inference 결과의 F1 score | `audit_global.db` — `audit_logs` 테이블 | `work_type = 'model_inference'`인 로그에서 `result_label`과 `ground_truth`(사후 검증 시) 비교 |
| `latency_p95` | inference 실행 시간의 95th percentile | `audit_global.db` — `duration_sec` 컬럼 | 해당 tool의 최근 N건 중 95번째 백분위수 |
| `error_rate` | inference 실패율 | `audit_global.db` — `status` 컬럼 | 최근 N건 중 `status = 'fail'` 비율 |

### 수집 SQL 쿼리 (참고)

```sql
-- rolling_f1: ground_truth가 있는 경우에만 산출 가능
SELECT result_label, ground_truth, duration_sec, status
FROM audit_logs
WHERE work_type = 'model_inference'
  AND tool_name = :tool_name
ORDER BY timestamp DESC
LIMIT :window_size;

-- pattern_stability: 승격 후보 탐지용
SELECT tool_name,
       COUNT(*) as total_runs,
       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
       CAST(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as success_rate
FROM audit_logs
WHERE work_type = 'model_inference'
GROUP BY tool_name;
```

### 수집 파라미터

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `window_size` | 100 | rolling 지표 산출 시 참조할 최근 건수 |
| `evaluation_interval` | `on_observability_run` | 평가 실행 시점 (observability 실행 시마다) |

---

## 신호 발생 규칙

### 임계값 참조

임계값은 `deploy_spec.json`의 `rollback` 블록에서 가져온다.

```json
{
  "rollback": {
    "degradation_threshold_f1": 0.80,
    "fallback_strategy": "llm_passthrough"
  }
}
```

### 신호 매핑

| 조건 | event_type | severity | 후속 행동 |
|------|------------|----------|-----------|
| `rolling_f1 < degradation_threshold_f1` | `anomaly_detected` | warning | 사용자에게 경고 알림 |
| 연속 3회 `anomaly_detected` 또는 `rolling_f1 < degradation_threshold_f1 - 0.1` | `hitl_request` | critical | Fallback 선택지 제시 (Gate Output Schema 적용) |
| `error_rate > 0.3` | `hitl_request` | critical | 긴급 Fallback 발동 (`auto_fallback: true`) → 사후 HITL 확인 |
| `pattern_stability >= 0.4` (Symlinked 임계) | `promotion_suggestion` | info | CC-15 payload 생성 → mso-skill-governance 전달 |
| `pattern_stability >= 0.7` + `workspace_count >= 3` | `promotion_suggestion` | info | Global 승격 후보 제안 |

### 신호 출력 형식

```json
{
  "event_type": "model_monitoring",
  "checkpoint_id": "model-mon-{tool_name}-{timestamp}",
  "payload": {
    "target_skills": ["mso-model-optimizer"],
    "severity": "warning",
    "message": "rolling_f1이 임계값 미만입니다",
    "monitoring_metrics": {
      "tool_name": "intent-classifier",
      "rolling_f1": 0.78,
      "latency_p95": 15.2,
      "error_rate": 0.02,
      "window_size": 100,
      "threshold_state": "warning"
    }
  },
  "retry_policy": {
    "max_retries": 0,
    "on_retry": "drop"
  },
  "correlation": {
    "run_id": "{run_id}",
    "artifact_uri": ".mso-context/tool_registry.json"
  },
  "timestamp": "2026-03-28T..."
}
```

### 승격 제안 출력 형식 (CC-15 payload)

```json
{
  "event_type": "promotion_suggestion",
  "checkpoint_id": "promo-{tool_name}-{timestamp}",
  "payload": {
    "target_skills": ["mso-skill-governance"],
    "severity": "info",
    "message": "Tool 승격 후보가 감지되었습니다",
    "promotion_proposal": {
      "tool_name": "intent-classifier",
      "current_state": "local",
      "proposed_state": "symlinked",
      "metrics": {
        "pattern_stability": 0.52,
        "workspace_count": 2,
        "abstraction_score": null
      },
      "evidence_refs": [
        ".mso-context/tool_registry.json"
      ]
    }
  },
  "retry_policy": {
    "max_retries": 1,
    "backoff_seconds": 60,
    "on_retry": "queue"
  },
  "correlation": {
    "run_id": "{run_id}",
    "artifact_uri": ".mso-context/tool_registry.json"
  },
  "timestamp": "2026-03-28T..."
}
```

---

## tool_registry.json 연동

이 모듈은 `{workspace}/.mso-context/tool_registry.json`의 `metrics` 블록을 갱신한다.

| 필드 | 갱신 시점 | 값 |
|------|-----------|-----|
| `metrics.rolling_f1` | 매 평가 시 | 산출된 rolling_f1 값 |
| `metrics.pattern_stability` | 매 평가 시 | `frequency × success_rate` |
| `metrics.last_evaluated_at` | 매 평가 시 | ISO 8601 timestamp |
| `promotion.candidate` | 임계값 도달 시 | `true` |
| `promotion.target_state` | 임계값 도달 시 | `"symlinked"` 또는 `"global"` |

---

## 기존 모듈과의 관계

| 모듈 | 관계 |
|------|------|
| `module.observation-policy` | 일반 실행 패턴 관찰. 이 모듈은 모델 inference에 특화 |
| `module.hitl-interaction` | 이 모듈이 `hitl_request`를 발생시키면 hitl-interaction이 사용자 응답을 처리 |
| `module.improvement-proposal` | 승격 제안(`promotion_suggestion`)은 improvement-proposal의 한 유형 |
| `module.evolution-tracking` | 승격 제안의 상태(제안됨 → 승인됨 → 실행됨)를 추적 |

---

## when_unsure

- `ground_truth`가 없어 `rolling_f1`을 산출할 수 없는 경우: `latency_p95`와 `error_rate`만으로 모니터링하고, `rolling_f1: null`로 기록한다.
- `deploy_spec.json`이 존재하지 않는 tool: 모니터링 대상에서 제외한다.
- `tool_registry.json`이 존재하지 않는 workspace: 경고 이벤트(`severity: warning`)를 남기고 승격 탐지를 건너뛴다.
