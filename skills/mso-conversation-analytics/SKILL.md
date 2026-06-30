---
name: mso-conversation-analytics
version: "0.6.4"
description: >
  turns.jsonl을 DuckDB in-memory로 분석해 운영 패턴을 측정.
  5개 분석 함수 + 환류 보고서 + Tier Escalation 신호 생성.
  ⚠ §11.1/v0.5.0: 분석 메서드(전환행렬·funnel·reprompt율)는 UUG(uug-pattern-analytics)
  흡수 대상, MSO runtime tier-escalation 신호는 mso-intent-analytics 귀속.
  흡수 전까지 잔존(de-routed: orchestration 라우팅에서 제외, 직접 호출만).
role: observability
triggers: []
depends_on:
  - mso-intent-analytics   # turns.jsonl 생산자(뒷단 dispatch turn_writer)
---

# MSO Conversation Analytics (v0.5.0) — de-routed (§11.1)

`turns.jsonl` → DuckDB → 운영 정책 환류.

> **상태**: orchestration 라우팅에서 제외(de-route). 전환행렬·funnel·reprompt율 같은 사용자/turn 패턴 분석은 UUG `uug-pattern-analytics` 흡수 대상이다. MSO runtime tier-escalation 폐루프 신호는 `mso-intent-analytics` 귀속이다. 흡수 전까지 capability 보존 위해 잔존 — 직접 `python src/analytics.py` 호출만.

## Boundary

- **UUG로 이동**: 많이 사용하는 workflow 후보, 반복 발화, reprompt율, unresolved 발화 같은 user/turn 패턴 탐지.
- **MSO에 잔류**: MSO intent dispatch 이후의 runtime tier-escalation 신호와 GroundedCommand 기반 운영 신호.

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
