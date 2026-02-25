# module.agent-decision

> Phase 2 전용. agent-decision이 3-Signal을 종합하여 Automation Level을 결정하는 상세 규칙.

---

## Signal A — 데이터·스크립트 가용성

| 상태 | 판정 레벨 |
|------|-----------|
| raw data만 존재, 분석 스크립트 없음 | Level 10 |
| 분석 스크립트 존재, 평가 기준 미확정 | Level 20 |
| 평가 기준 확정 + evaluation.py 존재 | Level 30 |

**체크 순서:**
1. `evaluation.py` (또는 동등한 평가 스크립트) 존재 여부 확인
2. 없으면 `analysis.script` (SQL/Python 분석 스크립트) 존재 여부 확인
3. 없으면 Level 10

---

## Signal B — 최근 KPI 지표

| 지표 상태 | 판정 레벨 |
|-----------|-----------|
| KPI 임계값 미달 (precision < gate_threshold) | Level 30 우선 검토 |
| KPI 보통 (임계값 ±5% 내외), 구조 개선 필요 | Level 20 |
| KPI 충족 (임계값 초과), 가시화만 필요 | Level 10 |
| KPI 기준값 미확인 | neutral (Signal A·C로만 결정) |

**데이터 출처**: `audit_global.db`의 최근 `audit_logs.metadata` 또는 직접 전달된 `current_metrics`

---

## Signal C — HITL 피드백 이력

| 피드백 패턴 | 레벨 보정 |
|-------------|-----------|
| 이전 HITL에서 "더 깊은 분석" 또는 "Level 상향" 요청 | +10 (max 30) |
| 이전 HITL에서 "빠른 리포트 충분" 또는 "Level 하향" 요청 | −10 (min 10) |
| 이전 HITL에서 "현행 유지" | 0 (보정 없음) |
| 피드백 이력 없음 | neutral (보정 없음) |

**데이터 출처**: `audit_global.db`의 `user_feedback` 테이블, `workflow_name` 기준 최근 3건 평균

---

## 3-Signal 종합 규칙

```
base_level = Signal_A
adjusted_level = base_level + Signal_C_delta
final_level = clip(adjusted_level, 10, 30)

if Signal_B == "KPI 미달" and final_level < 30:
    escalation_needed = true
    final_level = 30 (권고), 사용자 확인 후 확정

if Signal_간_충돌 (A와 B 방향 상이):
    final_level = min(A, B 기반 레벨)   # 보수적 선택
    escalation_needed = true
```

---

## 충돌 해결 우선순위

1. 안전 우선: Signal 충돌 시 항상 낮은 레벨 선택
2. KPI 미달은 escalation_needed=true로 명시적 에스컬레이션
3. Signal C는 보정값(delta)이므로 단독으로 레벨을 결정하지 않는다

---

## 출력 형식

```json
{
  "automation_level": 10 | 20 | 30,
  "rationale": [
    "Signal A: evaluation.py 존재 → Level 30 후보",
    "Signal B: KPI=90.3% > threshold → Level 10 충분",
    "Signal C: HITL 이력 없음 → 보정 없음",
    "충돌 감지 → 보수적 선택 Level 20"
  ],
  "escalation_needed": false
}
```
