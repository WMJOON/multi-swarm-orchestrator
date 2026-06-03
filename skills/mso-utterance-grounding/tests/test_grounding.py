"""
mso-utterance-grounding M3 DoD 테스트
실행: cd repository-test/skills/mso-utterance-grounding && python -m pytest tests/ -v
환경:
  GROUNDING_SKIP_LLM=1   (자동 설정됨 — LLM 호출 없이 Lv10 rule-based만)
  MSO_TURNS_PATH=/tmp/test_turns.jsonl (자동 설정됨)
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path

# ─── 환경 설정 ───────────────────────────────────────────────
os.environ["GROUNDING_SKIP_LLM"] = "1"
_TMP_TURNS = tempfile.mktemp(suffix=".jsonl")
os.environ["MSO_TURNS_PATH"] = _TMP_TURNS

# ─── 경로 주입 ───────────────────────────────────────────────
_SKILL = Path(__file__).parent.parent
_REGISTRY_SRC = _SKILL.parent / "mso-intent-registry" / "src"
for p in [str(_REGISTRY_SRC),
          str(_SKILL / "slots" / "input_norm"),
          str(_SKILL / "slots" / "rules"),
          str(_SKILL / "slots" / "inference"),
          str(_SKILL / "slots" / "script")]:
    if p not in sys.path:
        sys.path.insert(0, p)

from normalize   import normalize, detect_language   # type: ignore
from router      import route                        # type: ignore
from slot_filler import fill_slots                   # type: ignore
from resolver    import resolve_target               # type: ignore
from validator   import validate as vld              # type: ignore
from turn_writer import append_turn, new_turn_id     # type: ignore
from pipeline    import ground                       # type: ignore
from lookup      import lookup_intent                # type: ignore


# ════════════════════════════════════════════════════════════
# Case 1 — normalize (input_norm)
# ════════════════════════════════════════════════════════════

def test_normalize_strips_whitespace():
    assert normalize("  ticket-217 재실행  ") == "ticket-217 재실행"


def test_normalize_nfc():
    # NFC 변환 후에도 동일 텍스트여야 함
    text = "가나다"
    assert normalize(text) == text


def test_normalize_collapses_spaces():
    assert normalize("a  b   c") == "a b c"


def test_detect_language_ko():
    # 순수 한국어 텍스트
    assert detect_language("어떻게 되고 있습니까?") == "ko"

def test_detect_language_mixed():
    # 한국어+영어 혼용 — "run"이 영어라 mixed
    assert detect_language("내 run 어떻게 돼?") == "mixed"


def test_detect_language_en():
    assert detect_language("dispatch ticket retry") == "en"


# ════════════════════════════════════════════════════════════
# Case 2 — router (rules slot)
# ════════════════════════════════════════════════════════════

def test_router_dispatch_ticket():
    intent_id, conf = route("ticket-217 재실행")
    assert intent_id == "dispatch_ticket"
    assert conf == 1.0


def test_router_cancel_run():
    intent_id, conf = route("이 run 취소해줘")
    assert intent_id == "cancel_run"


def test_router_no_match():
    intent_id, conf = route("오늘 날씨 어때?")
    assert intent_id is None
    assert conf == 0.0


def test_router_override_hitl():
    intent_id, _ = route("H1 gate 해제해줘")
    assert intent_id == "override_hitl_gate"


# ════════════════════════════════════════════════════════════
# Case 3 — slot_filler
# ════════════════════════════════════════════════════════════

def test_slot_filler_dispatch_ticket_extracts_ref():
    intent = lookup_intent("dispatch_ticket")
    slots, reprompt, missing = fill_slots(intent, "ticket-217 재실행", {})
    assert slots.get("ticket_ref") == "ticket-217"
    assert not reprompt


def test_slot_filler_required_missing():
    intent = lookup_intent("dispatch_ticket")
    # ticket_ref 없는 발화
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


# ════════════════════════════════════════════════════════════
# Case 4 — resolver
# ════════════════════════════════════════════════════════════

def test_resolver_ticket():
    intent = lookup_intent("dispatch_ticket")
    target_id, concepts = resolve_target(
        intent, {"ticket_ref": "ticket-217"}, {}
    )
    assert target_id == "ticket-217"
    assert "TicketEvent" in concepts


def test_resolver_run():
    intent = lookup_intent("cancel_run")
    target_id, concepts = resolve_target(
        intent, {"run_ref": "run-abc"}, {}
    )
    assert "RunContext" in concepts


def test_resolver_gate():
    intent = lookup_intent("override_hitl_gate")
    target_id, concepts = resolve_target(
        intent, {"gate_ref": "gate-h1"}, {}
    )
    assert "HITLGateContext" in concepts


# ════════════════════════════════════════════════════════════
# Case 5 — validator
# ════════════════════════════════════════════════════════════

def test_validator_pass():
    intent = lookup_intent("dispatch_ticket")
    conforms, violations = vld(intent, {"ticket_ref": "ticket-217"}, [])
    assert conforms


def test_validator_fail_missing_required():
    intent = lookup_intent("dispatch_ticket")
    conforms, violations = vld(intent, {}, ["ticket_ref"])
    assert not conforms
    assert any("ticket_ref" in v for v in violations)


# ════════════════════════════════════════════════════════════
# Case 6 — turn_writer
# ════════════════════════════════════════════════════════════

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
    # 첫 줄: schema 헤더, 두 번째 줄: turn
    assert len(lines) == 2
    turn = json.loads(lines[1])
    assert turn["type"] == "turn"
    assert turn["turn_id"] == turn_id
    assert turn["resolved_intent_id"] == "dispatch_ticket"
    os.environ["MSO_TURNS_PATH"] = _TMP_TURNS   # 복원


# ════════════════════════════════════════════════════════════
# Case 7 — E2E fixture 정확도 (M3 DoD ≥80%)
# ════════════════════════════════════════════════════════════

def test_fixture_accuracy():
    fixture_path = Path(__file__).parent / "fixtures" / "utterances_50.jsonl"
    rows = [json.loads(l) for l in fixture_path.read_text().splitlines() if l.strip()]
    total   = len(rows)
    correct = 0
    errors  = []

    for row in rows:
        result = ground(row["utterance"], write_turn=False, skip_llm=True)
        if result["intent_id"] == row["expected_intent"]:
            correct += 1
        else:
            errors.append(
                f"  utterance='{row['utterance']}' "
                f"expected={row['expected_intent']} "
                f"got={result['intent_id']}"
            )

    accuracy = correct / total
    print(f"\nAccuracy: {correct}/{total} = {accuracy:.1%}")
    if errors:
        print("Mismatches:\n" + "\n".join(errors))

    assert accuracy >= 0.80, (
        f"M3 DoD: accuracy {accuracy:.1%} < 80%. Mismatches:\n" + "\n".join(errors)
    )


# ════════════════════════════════════════════════════════════
# Case 8 — reprompt 케이스 E2E
# ════════════════════════════════════════════════════════════

def test_e2e_reprompt_when_ticket_missing():
    result = ground("재실행해줘", write_turn=False, skip_llm=True)
    assert result["intent_id"] == "dispatch_ticket"
    assert result["reprompt_needed"] is True
    assert "ticket_ref" in result["reprompt_slots"]


def test_e2e_unresolved_returns_none():
    result = ground("오늘 점심 뭐 먹지?", write_turn=False, skip_llm=True)
    assert result["intent_id"] is None
    assert result["reprompt_needed"] is False
