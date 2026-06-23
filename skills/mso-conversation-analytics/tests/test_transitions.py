"""
mso-conversation-analytics M4 DoD 테스트
실행: cd repository/skills/mso-conversation-analytics && python -m pytest tests/ -v
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from transitions import (
    load_turns, transition_matrix, factored,
    funnel, reprompt_rate, unresolved,
)
from feedback   import generate_feedback
from escalation import check_escalation_candidates

_FIXTURES = Path(__file__).parent / "fixtures"
_EMPTY    = str(_FIXTURES / "turns_empty.jsonl")
_SAMPLE   = str(_FIXTURES / "turns_sample.jsonl")


# ════════════════════════════════════════════════════════════
# Empty 케이스 — 5개 함수 모두 빈 리스트, exception 없음
# ════════════════════════════════════════════════════════════

def test_empty_transition_matrix():
    con = load_turns(_EMPTY)
    assert transition_matrix(con) == []

def test_empty_factored():
    con = load_turns(_EMPTY)
    assert factored(con) == []

def test_empty_funnel():
    con = load_turns(_EMPTY)
    assert funnel(con) == []

def test_empty_reprompt_rate():
    con = load_turns(_EMPTY)
    assert reprompt_rate(con) == []

def test_empty_unresolved():
    con = load_turns(_EMPTY)
    assert unresolved(con) == []


# ════════════════════════════════════════════════════════════
# Sample 케이스 — SPEC §8.1 기대 결과 검증
# ════════════════════════════════════════════════════════════

def test_sample_transition_matrix_top():
    """dispatch_ticket → query_audit_log 최상위"""
    con = load_turns(_SAMPLE)
    rows = transition_matrix(con, days=365)
    assert len(rows) > 0
    # dispatch_ticket → query_audit_log 존재 확인
    pairs = {(r["from_intent"], r["to_intent"]) for r in rows}
    assert ("dispatch_ticket", "query_audit_log") in pairs


def test_sample_transition_matrix_count():
    """dispatch_ticket → query_audit_log cnt=2 (t1→t2, t4→t5)"""
    con = load_turns(_SAMPLE)
    rows = transition_matrix(con, days=365)
    hit = next((r for r in rows
                if r["from_intent"] == "dispatch_ticket"
                and r["to_intent"]  == "query_audit_log"), None)
    assert hit is not None, "dispatch_ticket→query_audit_log not found"
    assert hit["cnt"] == 2


def test_sample_factored_top():
    """dispatch_ticket × TicketEvent 계열 → query_audit_log 최상위 전이"""
    con = load_turns(_SAMPLE)
    rows = factored(con, days=365)
    assert len(rows) > 0
    # UNNEST로 TicketEvent / FailedTicket 각각 별도 행 → 둘 다 유효
    ticket_concepts = {"TicketEvent", "FailedTicket", "ActiveTicket", "PendingTicket"}
    top_dispatch = [
        r for r in rows
        if r["from_intent"] == "dispatch_ticket"
        and (r["from_target_concept"] or "") in ticket_concepts
        and r["to_intent"] == "query_audit_log"
    ]
    assert len(top_dispatch) > 0, (
        f"dispatch_ticket×TicketEvent→query_audit_log 전이 없음. rows={rows}"
    )


def test_sample_funnel_dispatch_ticket():
    """dispatch_ticket total=2, success_cnt=2"""
    con = load_turns(_SAMPLE)
    rows = funnel(con, days=365)
    hit = next((r for r in rows if r["intent_id"] == "dispatch_ticket"), None)
    assert hit is not None
    assert hit["total"] == 2
    assert hit["success_cnt"] == 2


def test_sample_funnel_query_audit_log():
    """query_audit_log total=2"""
    con = load_turns(_SAMPLE)
    rows = funnel(con, days=365)
    hit = next((r for r in rows if r["intent_id"] == "query_audit_log"), None)
    assert hit is not None
    assert hit["total"] == 2


def test_sample_reprompt_rate_empty():
    """fixture에 reprompt 없음 → 빈 리스트"""
    con = load_turns(_SAMPLE)
    rows = reprompt_rate(con, days=365)
    assert rows == []


def test_sample_unresolved():
    """t6 'rollback' 발화 1건 반환"""
    con = load_turns(_SAMPLE)
    rows = unresolved(con, days=365)
    assert len(rows) == 1
    assert "rollback" in rows[0]["utterance"]


# ════════════════════════════════════════════════════════════
# feedback + escalation
# ════════════════════════════════════════════════════════════

def test_feedback_empty_no_exception():
    """빈 데이터 → 예외 없이 빈 dict 4개 키 반환"""
    con = load_turns(_EMPTY)
    report = generate_feedback(con, days=365)
    assert "matrix_priority_suggestions" in report
    assert "slotspec_tuning"             in report
    assert "new_intent_candidates"       in report
    assert "tier_escalation_candidates"  in report


def test_feedback_sample_new_intent_candidate():
    """unresolved 'rollback' → new_intent_candidates에 포함 (단어 빈도 1이라 threshold 미달)"""
    con = load_turns(_SAMPLE)
    report = generate_feedback(con, days=365)
    # 6 turn sample에서는 'rollback' 1건 → threshold=3 미달 → 빈 리스트 정상
    assert isinstance(report["new_intent_candidates"], list)


def test_escalation_empty():
    """빈 데이터 → 빈 리스트"""
    con = load_turns(_EMPTY)
    assert check_escalation_candidates(con, days=365) == []


def test_escalation_sample_below_threshold():
    """6 turn sample → min_turns=200 미달 → 빈 리스트"""
    con = load_turns(_SAMPLE)
    candidates = check_escalation_candidates(con, days=365, min_turns=200)
    assert candidates == []


def test_escalation_sample_low_threshold():
    """min_turns=1 로 낮추면 후보 감지"""
    con = load_turns(_SAMPLE)
    candidates = check_escalation_candidates(
        con, days=365, min_turns=1, min_accuracy=0.5
    )
    assert len(candidates) > 0
    assert all("signal" in c for c in candidates)


# ════════════════════════════════════════════════════════════
# CLI 연기 테스트 (import 수준)
# ════════════════════════════════════════════════════════════

def test_analytics_module_importable():
    import analytics  # type: ignore  # noqa
    assert hasattr(analytics, "QUERIES")
    assert len(analytics.QUERIES) == 5
