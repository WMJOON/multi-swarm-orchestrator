---
name: mso-conversation-analytics
version: "0.3.1"
description: >
  turns.jsonl을 DuckDB in-memory로 분석해 운영 패턴을 측정.
  5개 분석 함수 + 환류 보고서 + Tier Escalation 신호 생성.
  ⚠ §11.1: 분석 메서드(전환행렬·funnel·reprompt율)는 UUG(uug-pattern-analytics)로
  흡수 예정, tier-escalation 신호는 mso-intent-analytics 귀속 예정. 흡수 전까지
  잔존(de-routed: orchestration 라우팅에서 제외, 직접 호출만).
role: observability
triggers: []
depends_on:
  - mso-intent-analytics   # turns.jsonl 생산자(뒷단 dispatch turn_writer)
---

# MSO Conversation Analytics (v0.3.1) — de-routed (§11.1)

`turns.jsonl` → DuckDB → 운영 정책 환류.

> **상태**: orchestration 라우팅에서 제외(de-route). 분석 메서드의 UUG 흡수가 완료되면 이 스킬은 제거되고, tier-escalation 폐루프는 `mso-intent-analytics` 로 이전된다(§11.1). 흡수 전까지 capability 보존 위해 잔존 — 직접 `python src/analytics.py` 호출만.

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
