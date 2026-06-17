"""
mso-intent-analytics dispatch(뒷단) 테스트.
§11: utterance→intent 분류(앞단)는 UUG 로 흡수 — 여기선 intent_id 입력 후
slot_filler→resolver→validator→turn_writer 만 검증.
실행: cd .../mso-intent-analytics && python -m pytest tests/ -v
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path

_TMP_TURNS = tempfile.mktemp(suffix=".jsonl")
os.environ["MSO_TURNS_PATH"] = _TMP_TURNS

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from normalize   import normalize, detect_language   # type: ignore
from slot_filler import fill_slots                   # type: ignore
from resolver    import resolve_target               # type: ignore
from validator   import validate as vld              # type: ignore
from turn_writer import append_turn, new_turn_id     # type: ignore
from pipeline    import ground                       # type: ignore
from lookup      import lookup_intent                # type: ignore


# ─── normalize (slot 전처리 — 뒷단에 잔류) ───────────────────

def test_normalize_strips_whitespace():
    assert normalize("  ticket-217 재실행  ") == "ticket-217 재실행"


def test_normalize_collapses_spaces():
    assert normalize("a  b   c") == "a b c"


def test_detect_language_ko():
    assert detect_language("어떻게 되고 있습니까?") == "ko"


# ─── slot_filler ─────────────────────────────────────────────

def test_slot_filler_dispatch_ticket_extracts_ref():
    intent = lookup_intent("dispatch_ticket")
    slots, reprompt, missing = fill_slots(intent, "ticket-217 재실행", {})
    assert slots.get("ticket_ref") == "ticket-217"
    assert not reprompt


def test_slot_filler_required_missing():
    intent = lookup_intent("dispatch_ticket")
    slots, reprompt, missing = fill_slots(intent, "재실행해줘", {})
    assert reprompt is True
    assert "ticket_ref" in missing


def test_slot_filler_session_context_fallback():
    intent = lookup_intent("query_run_status")
    ctx = {"session_id": "s1", "run_ids": ["run-abc"]}
    slots, reprompt, _ = fill_slots(intent, "내 run 어떻게 돼?", ctx)
    assert slots.get("run_ref") == "run-abc"
    assert not reprompt


def test_slot_filler_default_value():
    intent = lookup_intent("dispatch_ticket")
    slots, reprompt, _ = fill_slots(intent, "ticket-001 재실행", {})
    assert slots.get("reason") == "manual_retry"


# ─── resolver ────────────────────────────────────────────────

def test_resolver_ticket():
    intent = lookup_intent("dispatch_ticket")
    target_id, concepts = resolve_target(intent, {"ticket_ref": "ticket-217"}, {})
    assert target_id == "ticket-217"
    assert "TicketEvent" in concepts


def test_resolver_run():
    intent = lookup_intent("cancel_run")
    target_id, concepts = resolve_target(intent, {"run_ref": "run-abc"}, {})
    assert "RunContext" in concepts


def test_resolver_gate():
    intent = lookup_intent("override_hitl_gate")
    target_id, concepts = resolve_target(intent, {"gate_ref": "gate-h1"}, {})
    assert "HITLGateContext" in concepts


# ─── validator ───────────────────────────────────────────────

def test_validator_pass():
    intent = lookup_intent("dispatch_ticket")
    conforms, violations = vld(intent, {"ticket_ref": "ticket-217"}, [])
    assert conforms


def test_validator_fail_missing_required():
    intent = lookup_intent("dispatch_ticket")
    conforms, violations = vld(intent, {}, ["ticket_ref"])
    assert not conforms
    assert any("ticket_ref" in v for v in violations)


# ─── turn_writer ─────────────────────────────────────────────

def test_turn_writer_appends(tmp_path):
    os.environ["MSO_TURNS_PATH"] = str(tmp_path / "turns.jsonl")
    turn_id = new_turn_id()
    grounded = {
        "intent_id": "dispatch_ticket",
        "target_id": "ticket-217",
        "target_concepts": ["TicketEvent"],
        "slots": {"ticket_ref": "ticket-217"},
        "reprompt_needed": False,
        "reprompt_slots": [],
    }
    append_turn(turn_id, "s1", "ticket-217 재실행", grounded, None, 100)
    lines = Path(os.environ["MSO_TURNS_PATH"]).read_text().strip().splitlines()
    assert len(lines) == 2
    turn = json.loads(lines[1])
    assert turn["type"] == "turn"
    assert turn["resolved_intent_id"] == "dispatch_ticket"
    os.environ["MSO_TURNS_PATH"] = _TMP_TURNS


# ─── E2E 뒷단 (intent_id 입력 — 앞단은 UUG) ──────────────────

def test_e2e_with_intent_id_extracts_slots():
    r = ground("ticket-217 재실행", intent_id="dispatch_ticket", write_turn=False)
    assert r["intent_id"] == "dispatch_ticket"
    assert r["tier"] == "UUG"
    assert r["slots"].get("ticket_ref") == "ticket-217"
    assert r["target_id"] == "ticket-217"
    assert not r["reprompt_needed"]


def test_e2e_reprompt_when_ticket_missing():
    r = ground("재실행해줘", intent_id="dispatch_ticket", write_turn=False)
    assert r["intent_id"] == "dispatch_ticket"
    assert r["reprompt_needed"] is True
    assert "ticket_ref" in r["reprompt_slots"]


# ─── CLI 진입점 (§11 배선: UUG→MSO subprocess 계약) ──────────

def test_cli_ground_emits_grounded_command_json():
    """UUG 가 subprocess 로 부르는 계약: stdout 은 GroundedCommand JSON 한 줄."""
    import subprocess

    out = subprocess.run(
        [sys.executable, str(_SRC / "pipeline.py"), "ground",
         "--intent-id", "dispatch_ticket",
         "--utterance", "ticket-217 재실행", "--no-write"],
        capture_output=True, text=True, check=True,
    )
    grounded = json.loads(out.stdout)
    assert grounded["intent_id"] == "dispatch_ticket"
    assert grounded["tier"] == "UUG"
    assert grounded["slots"]["ticket_ref"] == "ticket-217"
    assert grounded["target_id"] == "ticket-217"
    assert grounded["reprompt_needed"] is False


def test_cli_ground_reprompt_path():
    import subprocess

    out = subprocess.run(
        [sys.executable, str(_SRC / "pipeline.py"), "ground",
         "--intent-id", "dispatch_ticket",
         "--utterance", "재실행해줘", "--no-write"],
        capture_output=True, text=True, check=True,
    )
    grounded = json.loads(out.stdout)
    assert grounded["reprompt_needed"] is True
    assert "ticket_ref" in grounded["reprompt_slots"]
