---
name: mso-conversation-analytics
version: "0.3.1"
description: >
  turns.jsonl을 DuckDB in-memory로 분석해 운영 패턴을 측정.
  5개 분석 함수 + 환류 보고서 + Tier Escalation 신호 생성.
role: observability
triggers: []
depends_on:
  - mso-utterance-grounding
---

# MSO Conversation Analytics (v0.3.1)

`turns.jsonl` → DuckDB → 운영 정책 환류.

## CLI

```bash
# 전체 보고서
python src/analytics.py --query all --days 7 --output table

# 특정 함수
python src/analytics.py --query reprompt_rate --days 3 --output json

# 환류 보고서 생성
python src/analytics.py --feedback --days 7 > feedback.json
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `MSO_TURNS_PATH` | workspace/.mso-context/conversation/turns.jsonl | turns.jsonl 경로 |

## 테스트 (M4 DoD)

```bash
pip install duckdb pytest
python -m pytest tests/ -v
```
