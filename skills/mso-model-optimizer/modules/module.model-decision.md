# module.model-decision

> Phase 2 전용. model-decision이 3-Signal을 종합하여 Training Level을 결정하는 상세 규칙.

---

## Signal A — 데이터 가용성

| 상태 | 판정 TL |
|------|---------|
| 데이터 < 100건, 라벨 품질 불확실 | TL-10 |
| 데이터 100~10K건, llm-as-a-judge 품질 Pass | TL-20 |
| 데이터 > 10K건, 품질 안정 + 다양한 분포 확인 | TL-30 |

**체크 순서:**

1. `dataset_stats.json`의 `total_count` 확인
2. `total_count < 100` → TL-10 즉시 판정
3. `llm-as-a-judge` 품질 점수 확인 (cohen_kappa ≥ 0.6 → Pass)
4. 라벨 분포 불균형 검사 (소수 클래스 비율 < 5% → warning 플래그)

---

## Signal B — 태스크 특성

| 태스크 유형 | 복잡도 | 기본 판정 TL |
|-------------|--------|-------------|
| binary classification | 낮음 | TL-20 |
| multi-class classification (< 20 클래스) | 중간 | TL-20 |
| multi-class classification (≥ 20 클래스) | 높음 | TL-30 |
| NER (< 10 엔티티 유형) | 중간 | TL-20 |
| NER (≥ 10 엔티티 유형) | 높음 | TL-30 |
| ranking / similarity | 중간 | TL-20 |
| sequence tagging (복합) | 높음 | TL-30 |
| 결정론적 패턴 (regex/rule로 해결 가능) | 낮음 | TL-10 |

**판단 기준:**

1. `inference_pattern`으로 태스크 유형 식별
2. `dataset_stats.json`의 `label_count` 또는 `entity_type_count`로 복잡도 측정
3. 태스크가 결정론적인지 판별: 데이터 내 동일 입력 → 동일 출력 비율이 95% 이상이면 TL-10 권고

---

## Signal C — 기존 모델 이력

| 이력 상태 | TL 보정 |
|-----------|---------|
| 이전 모델 없음 (첫 학습) | 보정 없음 (0) |
| 이전 모델 존재 + f1 ≥ 0.90 | -10 (더 보수적으로: 미세 조정이면 충분) |
| 이전 모델 존재 + f1 < 0.85 | +10 (이전 모델 부족 → 더 깊은 학습 필요) |
| 이전 모델 존재 + rollback 이력 있음 | +10 + escalation_needed=true |

**데이터 출처**: `audit_global.db`의 `work_type='model_optimization'` 레코드에서 최근 3건 조회

---

## 3-Signal 종합 규칙

```
base_tl       = Signal_A      (데이터 기반 초기 TL)
task_delta    = Signal_B 기본 TL - base_tl   (태스크 복잡도 보정)
history_delta = Signal_C 보정값

# Signal B는 base_tl과 비교하여 delta 산출
# 예: Signal_A → TL-20, Signal_B → TL-30 → task_delta = +10

adjusted_tl   = base_tl + task_delta + history_delta
final_tl      = clip(adjusted_tl, TL-10, TL-30)

# rollback 이력이 있으면 강제 에스컬레이션
if Signal_C에 rollback 이력:
    escalation_needed = true

# Signal 간 충돌 (A와 B 방향 상이):
if |task_delta| >= 20:       # 2단계 이상 차이
    final_tl = min(Signal_A 기반, Signal_B 기반)   # 보수적 선택
    escalation_needed = true
```

---

## 충돌 해결 우선순위

1. **안전 우선**: Signal 충돌 시 항상 낮은 TL 선택
2. **rollback 이력은 강제 에스컬레이션**: 이전에 실패한 모델이 있으면 신중하게 접근
3. **Signal C는 보정값(delta)**: 단독으로 TL을 결정하지 않음
4. **데이터 부족은 최우선**: 100건 미만이면 Signal B·C와 무관하게 TL-10

---

## 출력 형식

```json
{
  "training_level": "TL-20",
  "model_type": "classifier",
  "base_model": "distilbert-base-uncased",
  "rationale": [
    "Signal A: 2,847건 (llm-as-a-judge cohen_kappa=0.73) → TL-20 후보",
    "Signal B: multi-class classification (15 클래스) → TL-20",
    "Signal C: 이전 모델 없음 → 보정 없음",
    "종합: TL-20 확정"
  ],
  "escalation_needed": false
}
```

---

## base_model 선택 가이드

TL-20/30에서 `base_model`을 결정할 때:

| inference_pattern | 권장 base_model 범위 | 비고 |
|-------------------|---------------------|------|
| classification | distilbert, albert, tinybert | 속도 우선 |
| NER | distilbert, bert-base, roberta | 정확도 우선 |
| ranking | sentence-transformers/all-MiniLM | 임베딩 기반 |
| tagging | bert-base, roberta | 토큰 레벨 태깅 |

base_model 최종 선택은 `dataset_stats.json`의 언어 필드와 데이터 크기를 고려하여 결정한다. 사용자가 직접 지정할 수도 있다.
