"""
Tier Escalation 신호 판정.
funnel 결과에서 Lv30→Lv20 전환 후보 감지.
"""
from __future__ import annotations

from transitions import funnel


def check_escalation_candidates(
    con,
    days: int = 7,
    min_turns: int = 200,
    min_accuracy: float = 0.85,
) -> list[dict]:
    """
    Lv30→Lv20 전환 후보 반환.
    조건: turn_count >= min_turns AND success_rate >= min_accuracy*100

    Returns: [{"intent_id","turn_count","lv30_accuracy_7d","signal"}, ...]
    """
    rows = funnel(con, days=days)
    candidates = []
    for row in rows:
        if (row["total"] >= min_turns
                and (row["success_rate"] or 0) / 100 >= min_accuracy):
            candidates.append({
                "intent_id":        row["intent_id"],
                "turn_count":       row["total"],
                "lv30_accuracy_7d": round((row["success_rate"] or 0) / 100, 3),
                "signal": (
                    "Lv30→Lv20 전환 가능. "
                    "mso-model-optimizer TL-20 트리거 조건 충족"
                ),
            })
    return candidates
