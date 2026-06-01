"""
Closed-loop 환류 보고서 생성.
분석 결과 → intent_matrix priority 재조정 / SlotSpec 튜닝 / 신규 intent 후보 제안.
"""
from __future__ import annotations
import re

from transitions import transition_matrix, factored, reprompt_rate, unresolved
from escalation  import check_escalation_candidates

# 환류 판정 임계값
_REPROMPT_THRESHOLD   = 1.5   # avg_reprompt > 이 값 → SlotSpec 튜닝 제안
_SUCCESSOR_MIN_PCT    = 40.0  # top_successor pct > 이 값 → matrix priority 올리기
_UNRESOLVED_MIN_COUNT = 3     # 동일 패턴 ≥ 이 건수 → 신규 intent 후보


def generate_feedback(con, days: int = 7) -> dict:
    """
    Returns: {
        "matrix_priority_suggestions": [...],
        "slotspec_tuning":             [...],
        "new_intent_candidates":       [...],
        "tier_escalation_candidates":  [...],
    }
    """
    return {
        "matrix_priority_suggestions": _matrix_suggestions(con, days),
        "slotspec_tuning":             _slotspec_tuning(con, days),
        "new_intent_candidates":       _new_intent_candidates(con, days),
        "tier_escalation_candidates":  check_escalation_candidates(con, days=days),
    }


# ─── 개별 환류 생성 ──────────────────────────────────────────

def _matrix_suggestions(con, days: int) -> list[dict]:
    """top_successor pct 높은 셀 → intent_matrix planned priority 올리기 제안."""
    tm = transition_matrix(con, days=days)
    seen: set[str] = set()
    suggestions = []
    for row in tm:
        key = f"{row['from_intent']}->{row['to_intent']}"
        if key in seen:
            continue
        seen.add(key)
        pct = row.get("pct") or 0
        if pct >= _SUCCESSOR_MIN_PCT:
            suggestions.append({
                "from_intent": row["from_intent"],
                "to_intent":   row["to_intent"],
                "pct":         pct,
                "suggestion": (
                    f"{row['from_intent']} 이후 {pct}% 확률로 {row['to_intent']} 발생 "
                    f"— intent_matrix에서 {row['to_intent']} 관련 planned 셀 priority 상향 고려"
                ),
            })
    return suggestions


def _slotspec_tuning(con, days: int) -> list[dict]:
    """avg_reprompt 높은 intent → SlotSpec 개선 제안."""
    rr = reprompt_rate(con, days=days)
    tuning = []
    for row in rr:
        avg = row.get("avg_reprompt") or 0
        if avg > _REPROMPT_THRESHOLD:
            tuning.append({
                "intent_id":   row["intent_id"],
                "avg_reprompt": avg,
                "suggestion": (
                    f"avg_reprompt={avg} > {_REPROMPT_THRESHOLD} "
                    f"— fill_policy를 'session_context'로 변경하거나 "
                    f"default_value 추가 검토"
                ),
            })
    return tuning


def _new_intent_candidates(con, days: int) -> list[dict]:
    """unresolved 발화에서 반복 키워드 클러스터 추출 → 신규 intent 후보."""
    rows = unresolved(con, days=days)
    if not rows:
        return []

    # 단순 키워드 빈도 집계 (v0.3.1 — embedding 클러스터링은 v0.4.x)
    word_count: dict[str, int] = {}
    word_utterances: dict[str, list[str]] = {}
    for row in rows:
        utt = (row.get("utterance") or "").lower()
        words = re.findall(r"[a-z가-힣]+", utt)
        for w in set(words):
            if len(w) < 2:
                continue
            word_count[w] = word_count.get(w, 0) + 1
            word_utterances.setdefault(w, []).append(row["utterance"])

    candidates = []
    for word, count in sorted(word_count.items(), key=lambda x: -x[1]):
        if count >= _UNRESOLVED_MIN_COUNT:
            candidates.append({
                "pattern":           word,
                "count":             count,
                "sample_utterances": word_utterances[word][:3],
                "suggestion": (
                    f"'{word}' 키워드가 {count}회 미분류 — "
                    f"새 intent trigger_keyword 또는 신규 intent 추가 검토"
                ),
            })
    return candidates
