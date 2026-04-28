# APO Schema Reference

## 입력 JSONL 포맷

### llm_labels.jsonl
```json
{"id": "MSG-001", "class": "intent_A", "confidence": 0.85, "margin": 0.42}
```
- `margin`: top-1 confidence − top-2 confidence. 없으면 0으로 간주.

### human_labels.jsonl
```json
{"id": "MSG-001", "reviewed_class": "intent_B"}
```

---

## compute_apo_signals.py 출력 스키마

```json
{
  "total_matched": 320,
  "disagreement_rate": 0.22,
  "mean_confidence": 0.71,
  "worst_p10_confidence": 0.41,
  "deterioration_rate": 0.04,
  "safety_gate": {
    "delta_ok": true,
    "worst_p10_ok": false,
    "deterioration_ok": true,
    "disagreement_ok": false,
    "all_pass": false
  },
  "top_confused_classes": [
    {
      "class": "intent_A",
      "confusion_score": 0.38,
      "total": 45,
      "disagree": 12,
      "low_conf": 8,
      "low_margin": 6
    }
  ],
  "recommended_decision": "run_apo"
}
```

### recommended_decision 값

| 값 | 조건 |
|----|------|
| `skip` | safety_gate.all_pass = true |
| `run_apo` | disagreement_rate ≥ 0.15 |
| `monitor` | 0.10 ≤ disagreement_rate < 0.15 |

---

## Safety Gate 상세

| 조건 | 기준 | 비고 |
|------|------|------|
| `delta_ok` | mean_confidence ≥ baseline − 0.05 | baseline = 이전 라운드 mean_conf |
| `worst_p10_ok` | worst_p10_confidence ≥ baseline − 0.10 | |
| `deterioration_ok` | deterioration_rate ≤ 0.05 | confidence < 0.5 비율 |
| `disagreement_ok` | disagreement_rate ≤ baseline + 0.05 | |

baseline 없는 첫 라운드: `--baseline-disagreement 0.0` (모든 delta 조건 통과)

---

## apo_observability 기록 스키마

라운드 완료 후 아래 구조로 기록한다 (append-only).

```json
{
  "round_id": "round-20260428-001",
  "timestamp": "2026-04-28T17:00:00Z",
  "disagreement_before": 0.22,
  "disagreement_after": 0.13,
  "confusion_classes": ["intent_A", "intent_B"],
  "safety_gate_passed": false,
  "recommended_decision": "run_apo",
  "human_decision": "accept",
  "prompt_version_before": "v3",
  "prompt_version_after": "v4",
  "activated": true,
  "converged": false
}
```

### converged 판정

연속 2라운드에서 `disagreement_rate < 0.10` → `converged: true`.

---

## 수렴 임계값 기본값 (오버라이드 가능)

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `apo_trigger_threshold` | 0.15 | 이 값 이상이면 APO 실행 |
| `convergence_threshold` | 0.10 | 이 값 미만 2연속이면 수렴 |
| `top_n_confused` | 10 | 인터뷰 대상 혼동 클래스 수 |
| `safety_delta` | 0.05 | Safety Gate delta 허용 범위 |
