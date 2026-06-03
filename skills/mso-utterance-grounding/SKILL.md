---
name: mso-utterance-grounding
version: "0.3.1"
description: >
  오퍼레이터 자연어 발화를 GroundedCommand로 변환하는 Smart Tool.
  Lv10 rule-based 라우터 + Lv30 LLM fallback으로 시작.
  analytics 누적 후 Lv20 경량 모델로 escalation-down.
role: runtime
triggers:
  - "utterance grounding"
  - "발화 grounding"
depends_on:
  - mso-intent-registry
---

# MSO Utterance Grounding (v0.3.1)

발화 → GroundedCommand 변환 Smart Tool.

## 4-Slot Pipeline

```
input_norm  → normalize.py       (unicode NFC, 공백 제거)
rules       → router.py          (Lv10 trigger_keywords 매칭)
inference   → serve.py           (Lv30 LLM fallback / Lv20 모델)
script      → pipeline.py        (slot_filler → resolver → validator → turn_writer)
```

## 사용법

```python
import sys
sys.path.insert(0, "slots/script")
sys.path.insert(0, "../mso-intent-registry/src")

from pipeline import ground

result = ground(
    utterance="ticket-217 재실행",
    session_context={"session_id": "run-abc:op-1:x", "run_ids": ["run-abc"]},
    write_turn=True,
)
# result["intent_id"] == "dispatch_ticket"
# result["slots"]["ticket_ref"] == "ticket-217"
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GROUNDING_SKIP_LLM` | 0 | 1이면 LLM inference 건너뜀 (테스트용) |
| `MSO_TURNS_PATH` | workspace/.mso-context/conversation/turns.jsonl | turns.jsonl 경로 |
| `ANTHROPIC_API_KEY` | — | Lv30 LLM 호출용 |

## 테스트 (M3 DoD)

```bash
pip install rdflib pytest
GROUNDING_SKIP_LLM=1 python -m pytest tests/ -v
```

**DoD 기준**: 50개 fixture ≥ 80% top-1 정확도 (Lv10 rule-based).
