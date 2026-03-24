# module.model-decision

> Phase 2 전용. model-decision이 3-Signal을 종합하여 Training Level을 결정하는 상세 규칙.

---

## Signal A — 데이터 가용성 + 라벨 전략

> Phase 1.5(Label Strategy)의 산출물을 반영한다. `label_strategy_output.json`이 존재하면 `effective_count`를 사용하고, 존재하지 않으면 `total_count`로 fallback한다.

### A-1: 라벨 유무 분류

| 필드 | 설명 |
|------|------|
| `labeled_count` | 인간 검증 라벨 수 |
| `unlabeled_count` | 비라벨 데이터 수 |
| `augmented_count` | Augmentation으로 생성된 라벨 수 |
| `weak_supervision_count` | Weak Supervision으로 생성된 라벨 수 |
| `synthetic_count` | LLM 합성 라벨 수 |
| `effective_count` | `labeled + 0.7 × (augmented + weak + synthetic)` |

### A-2: TL 판정 기준

| 상태 | 판정 TL | 학습 방식 권고 |
|------|---------|---------------|
| `effective_count` < 50 | TL-10 | Rule/Heuristic |
| `effective_count` 50~200, `labeled_count`(인간 검증만) ≥ 8/class | TL-20 | **SetFit** (Few-shot) |
| `effective_count` 200~2K | TL-20 | **LoRA/QLoRA** 또는 표준 fine-tuning |
| `effective_count` 2K~10K, llm-as-a-judge Pass | TL-20 | 표준 fine-tuning |
| `effective_count` > 10K, 품질 안정 + 다양한 분포 | TL-30 | 전체 학습 |

### A-3: 라벨 소스 품질 가중치

라벨 소스에 따라 신뢰도가 다르다. `effective_count` 산정 시 가중치를 적용한다.

| 소스 | 가중치 | 근거 |
|------|--------|------|
| 인간 검증 라벨 (HITL) | 1.0 | 최고 신뢰도 |
| Active Learning 선별 + 인간 라벨 | 1.0 | 인간 검증 동일 |
| Data Augmentation (EDA/Back-Translation) | 0.7 | 의미 보존 변형이나 노이즈 가능 |
| Weak Supervision (Snorkel) | 0.7 | 규칙 기반, 커버리지 제한 |
| LLM 합성 데이터 | 0.5 | 실제 분포 괴리 가능 |
| Zero-shot pseudo-label (미검증) | 0.3 | 정확도 편차 큼 |

> Cleanlab 감사를 거친 데이터는 가중치 +0.1 보정 (최대 1.0)

**체크 순서:**

1. `label_strategy_output.json` 존재 여부 확인
2. 존재 시: `effective_count` + `label_strategy` 레벨 확인
3. 미존재 시: `dataset_stats.json`의 `total_count`로 fallback (기존 로직)
4. `effective_count` 기반 TL 판정
5. `llm-as-a-judge` 품질 점수 확인 (cohen_kappa ≥ 0.6 → Pass)
6. 라벨 분포 불균형 검사 (소수 클래스 비율 < 5% → warning 플래그)
7. 합성/약성 라벨 비율 > 70%이면 warning + HITL 라벨 보강 권고

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
base_tl       = Signal_A      (effective_count 기반 초기 TL)
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
    "Signal A: effective_count=2,847 (labeled=400, augmented=1200×0.7, weak=2500×0.7, cohen_kappa=0.73) → TL-20 후보",
    "Signal B: multi-class classification (15 클래스) → TL-20",
    "Signal C: 이전 모델 없음 → 보정 없음",
    "Label Strategy: LS-2 (Active Learning + Augmentation 완료)",
    "종합: TL-20 확정, LoRA fine-tuning 권고"
  ],
  "escalation_needed": false
}
```

---

## base_model 선택 가이드

TL-20/30에서 `base_model`을 결정할 때:

| inference_pattern | effective_count | 권장 base_model / 방식 | 비고 |
|-------------------|----------------|----------------------|------|
| classification | < 200 (라벨 8+/class) | **SetFit** + sentence-transformers | Few-shot 최적 |
| classification | 200~2K | **LoRA/QLoRA** + distilbert/bert-base | PEFT 효율 |
| classification | 2K+ | distilbert, albert, tinybert | 표준 fine-tuning |
| NER | < 500 | **LoRA** + bert-base/roberta | 토큰 레벨 PEFT |
| NER | 500+ | distilbert, bert-base, roberta | 표준 fine-tuning |
| ranking | any | sentence-transformers/all-MiniLM | 임베딩 기반 |
| tagging | any | bert-base, roberta | 토큰 레벨 태깅 |

base_model 최종 선택은 `dataset_stats.json`의 언어 필드, `label_strategy_output.json`의 라벨 상황, 데이터 크기를 종합하여 결정한다. 사용자가 직접 지정할 수도 있다.
