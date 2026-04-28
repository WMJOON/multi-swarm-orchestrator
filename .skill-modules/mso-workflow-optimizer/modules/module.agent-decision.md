# module.agent-decision

> Phase 2 전용. agent-decision이 3-Signal을 종합하여 Automation Level을 결정하는 상세 규칙.

---

## Level Decision Rubric

> 루브릭은 4개 차원에서 각 레벨의 적합 조건을 정의한다. Signal A·B·C는 이 루브릭을 기준으로 점수를 산정한다.
> **유효 조건**: `run_count ≥ 10` (audit_global.db 기준). 미달 시 Level 30 기본값 — Data Sufficiency Gate 참조.

| 차원 | Level 10 (리포팅) | Level 20 (스크립트 분석) | Level 30 (자동화 평가) |
|------|-----------------|----------------------|-------------------|
| **스크립트 가용성** | raw data만 존재 | analysis.script 존재 | evaluation.py 존재 |
| **KPI 달성률** | ≥ gate_threshold + 5% | gate_threshold ±5% | < gate_threshold − 5% |
| **pattern_stability** | ≥ 80 | 30 ≤ x < 80 | < 30 |
| **HITL 방향** | "유지" 또는 "하향" | 중립 / 이력 없음 | "상향" 요청 |

**gate_threshold 기본값**: `85` (precision 기준). `docs/usage/{workflow_name}.md`에 `kpi.gate_threshold` 명시 시 override.

---

## Data Sufficiency Gate

Phase 2 진입 전 아래 쿼리로 run_count를 확인한다.

```sql
SELECT COUNT(*) AS run_count
FROM audit_logs
WHERE workflow_name = '{workflow_name}' AND status = 'completed'
```

| run_count | 처리 |
|-----------|------|
| < 10 | **루브릭 평가 스킵.** Level 30 기본값 + `data_insufficient: true` 플래그. rationale에 "데이터 불충분" 명시. |
| 10 ~ 49 | 루브릭 평가 진행. pattern_stability 신뢰도 낮음 — rationale에 `"low_confidence: run_count={n}"` 명시. |
| ≥ 50 | 루브릭 평가 전결. pattern_stability 충분한 신뢰도. |

> **설계 의도**: `milestone` 트리거의 첫 발화 시점(run_count=10)과 루브릭 유효 시점이 일치한다.
> `observability_alert` 트리거도 동일한 audit_global.db에서 pattern_stability를 감지하므로, 모든 트리거는 audit-log 기반으로 수렴한다.

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

## Signal C — HITL 피드백 이력 + Jewels

| 피드백 패턴 | 레벨 보정 |
|-------------|-----------|
| 이전 HITL에서 "더 깊은 분석" 또는 "Level 상향" 요청 | +10 (max 30) |
| 이전 HITL에서 "빠른 리포트 충분" 또는 "Level 하향" 요청 | −10 (min 10) |
| 이전 HITL에서 "현행 유지" | 0 (보정 없음) |
| 피드백 이력 없음 | neutral (보정 없음) |

**데이터 출처**: `audit_global.db`의 `user_feedback` 테이블, `workflow_name` 기준 최근 3건 평균

### Signal C 추가 입력: Jewels (jewel-producer 생성분)

lead가 decision-agent 소환 시 미소비 jewels를 함께 전달한다.
jewels는 HITL 피드백 보정값 계산 **이후** 추가 반영된다.

| 수신 Jewel type | severity | Signal C 추가 보정 |
|----------------|----------|--------------------|
| `kpi_drift` | high | +10 |
| `level_escalation` | medium | +10 |
| `pattern_alert` | medium | escalation_needed=true 강제 |
| `sampling_adjust` | low | 보정 없음 (Phase 3 메타로만 전달) |

**적용 순서**: `base_level(Signal A)` → `HITL delta(Signal C)` → `jewel delta` → `KPI 검증(Signal B)` → `final_level`

---

## 3-Signal 종합 규칙

```
base_level    = Signal_A
hitl_delta    = Signal_C (HITL 피드백 보정)
jewel_delta   = jewels 보정 합산 (kpi_drift +10, level_escalation +10)

# Signal C 총 기여는 ±10으로 캡 (과잉 에스컬레이션 방지)
total_C_delta = clip(hitl_delta + jewel_delta, -10, +10)

adjusted_level = base_level + total_C_delta
final_level    = clip(adjusted_level, 10, 30)

if any(jewel.type == "pattern_alert" for jewel in jewels):
    escalation_needed = true

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
