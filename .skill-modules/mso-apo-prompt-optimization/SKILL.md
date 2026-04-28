---
name: mso-apo-prompt-optimization
description: |
  LLM-as-a-judge 라벨과 인간(HITL) 라벨의 불일치를 분석해 라벨링 프롬프트를 자동 개선하는 수렴 루프 스킬.
  다음 상황에 사용한다:
  (1) 라벨링 라운드 완료 후 APO 실행 요청 ("APO 실행", "프롬프트 최적화", "라벨링 품질 개선")
  (2) 특정 클래스에서 LLM 분류 오류가 반복될 때
  (3) disagreement_rate ≥ 0.15 신호가 감지될 때
  mso-model-optimizer Phase 1.6 또는 독립 루틴으로 실행된다.
---

# mso-apo-prompt-optimization

LLM 라벨 vs 인간 라벨 차이 분석 → 혼동 패턴 추출 → 프롬프트 개선 → 재검증의 수렴 루프.

---

## 입력 요구사항

| 항목 | 필수 | 설명 |
|------|------|------|
| `llm_labels` | ✓ | LLM-as-a-judge 분류 결과 (class, confidence) |
| `human_labels` | ✓ | HITL 검수 결과 (reviewed_class) |
| `current_prompt` | ✓ | 현재 활성 라벨링 프롬프트 |
| `class_definitions` | - | 클래스별 정의 (있으면 인터뷰 품질 향상) |
| `human_decision_records` | - | 확정된 운영 정책 (있으면 프롬프트 제약으로 고정) |

---

## 실행 흐름

### Step 1 — 신호 계산

`scripts/compute_apo_signals.py`를 실행한다.

```bash
python3 scripts/compute_apo_signals.py \
  --llm-labels llm_labels.jsonl \
  --human-labels human_labels.jsonl \
  --output apo_signals.json
```

산출 신호: `disagreement_rate`, `confusion_score[]`, `safety_gate`, `recommended_decision`
스키마 상세: [references/apo-schema.md](references/apo-schema.md)

**조기 종료**: `safety_gate.all_pass = true` → APO 불필요, 현재 프롬프트 유지.

---

### Step 2 — 혼동 패턴 추출 + Agent Discussion

`confusion_score` 상위 N개 클래스(기본 10개)를 대상으로 구조화 인터뷰를 진행한다.

```
for each confused_class_pair (A vs B):
  1. 현재 프롬프트의 A, B 정의 제시
  2. 질문: "A와 B의 경계 조건이 명확한가? 반례가 있는가?"
  3. 사용자 응답 → 개선 힌트 수집
  4. human_decision_records 정책은 제약으로 고정

조기 종료:
  - 동일 클래스 쌍 2라운드 연속 반복 → 루프 탈출
  - 사용자 "충분하다" → 즉시 종료
```

---

### Step 3 — 프롬프트 초안 생성

수집된 개선 힌트 + 운영 정책 제약을 LLM에 전달하여 초안을 생성한다.

**원칙**:
- 원본 변수 구조 (`{class_list}`, `{text}`, `{context}` 등) 반드시 유지
- 혼동 클래스에 정의·경계 조건·반례 추가
- 잘 동작하는 부분은 수정하지 않음
- 초안은 `is_active: false` — 사람 승인 전 미적용

---

### Step 4 — HITL 검토 + 활성화

초안과 변경 요약을 제시한다. 사용자 결정:

| 결정 | 처리 |
|------|------|
| `accept` | 프롬프트 활성화 + apo_observability 기록 |
| `reject` | 현재 프롬프트 유지 + 거절 사유 기록 |
| `needs_revision` | Step 3 재실행 |

---

### Step 5 — 수렴 판정

| 조건 | 처리 |
|------|------|
| 연속 2라운드 `disagreement_rate < 0.10` | APO 루프 종료, 프롬프트 고정 |
| `disagreement_rate ≥ 0.10` 유지 | 다음 라운드 후 Step 1부터 재실행 |

---

## 산출물

```json
{
  "round_id": "<round_id>",
  "disagreement_before": 0.22,
  "disagreement_after": 0.13,
  "confusion_classes": ["class_A", "class_B"],
  "recommended_decision": "accept",
  "activated": true,
  "converged": false
}
```

스키마 상세: [references/apo-schema.md](references/apo-schema.md)
