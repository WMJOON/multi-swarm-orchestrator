"""
mso-intent-registry Lookup API smoke tests (M2 DoD)
실행: cd repository-test/skills/mso-intent-registry && python -m pytest tests/ -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from lookup import list_intents, lookup_intent, lookup_target, get_trigger_keywords, list_matrix_cells


# ── Case 1: list_intents ──────────────────────────────────────
def test_list_intents_count():
    intents = list_intents()
    assert len(intents) == 10, f"Expected 10 intents, got {len(intents)}"


def test_list_intents_required_fields():
    for intent in list_intents():
        assert intent["intent_id"], "intent_id must not be empty"
        assert intent["verb_concept"], "verb_concept must not be empty"
        assert intent["target_concept"], "target_concept must not be empty"
        assert isinstance(intent["trigger_keywords"], list), "trigger_keywords must be list"
        assert len(intent["trigger_keywords"]) > 0, f"{intent['intent_id']} has no trigger_keywords"


# ── Case 2: lookup_intent ─────────────────────────────────────
def test_lookup_intent_dispatch_ticket():
    r = lookup_intent("dispatch_ticket")
    assert r is not None, "dispatch_ticket must exist"
    assert r["verb_concept"] == "CreateVerb"
    assert r["target_concept"] == "TicketEvent"
    assert "재실행" in r["trigger_keywords"]
    # required slot: ticket_ref
    ticket_ref = next((s for s in r["slot_specs"] if s["slot_name"] == "ticket_ref"), None)
    assert ticket_ref is not None, "dispatch_ticket must have ticket_ref slot"
    assert ticket_ref["required"] is True


def test_lookup_intent_not_found():
    assert lookup_intent("nonexistent_intent") is None


# ── Case 3: lookup_target ─────────────────────────────────────
def test_lookup_target_ticket():
    r = lookup_target("ticket-217")
    assert r["entity_ref"] == "ticket-217"
    assert "TicketEvent" in r["target_concepts"]


def test_lookup_target_run():
    r = lookup_target("run-abc")
    assert "RunContext" in r["target_concepts"]


def test_lookup_target_gate():
    r = lookup_target("gate-h1")
    assert "HITLGateContext" in r["target_concepts"]
    assert "RunContext" in r["target_concepts"]


def test_lookup_target_unknown():
    r = lookup_target("unknown-ref-xyz")
    assert r["entity_ref"] == "unknown-ref-xyz"
    assert r["target_concepts"] == []


# ── Case 4: get_trigger_keywords ─────────────────────────────
def test_get_trigger_keywords():
    kws = get_trigger_keywords("cancel_run")
    assert isinstance(kws, list)
    assert len(kws) > 0
    assert "취소" in kws or "abort" in kws


# ── Case 5: list_matrix_cells ─────────────────────────────────
def test_matrix_filled_cells():
    cells = list_matrix_cells(status="filled")
    assert len(cells) == 10, f"Expected 10 filled cells, got {len(cells)}"


def test_matrix_sparql_equivalent():
    """PRD M2 DoD: SPARQL SELECT ?cell WHERE { ?cell status 'filled' } → 10 row 재현."""
    cells = list_matrix_cells(status="filled")
    intent_ids = [c["intent_id"] for c in cells]
    expected = {
        "query_run_status", "query_ticket_list", "query_audit_log",
        "dispatch_ticket", "create_ticket",
        "pause_workflow", "resume_workflow", "override_hitl_gate",
        "update_ticket_priority", "cancel_run",
    }
    assert set(intent_ids) == expected, f"Missing: {expected - set(intent_ids)}"
