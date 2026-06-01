"""
script slot — Grounding Pipeline 메인 진입점.
input_norm → rules → (inference) → slot_filler → resolver → validator → turn_writer
→ GroundedCommand 반환
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# ─── 경로 주입 ───────────────────────────────────────────────
_SKILL_DIR = Path(__file__).parent.parent.parent
_REGISTRY_SRC = _SKILL_DIR.parent / "mso-intent-registry" / "src"
for p in [str(_REGISTRY_SRC), str(_SKILL_DIR / "slots" / "input_norm"),
          str(_SKILL_DIR / "slots" / "rules"),
          str(_SKILL_DIR / "slots" / "inference"),
          str(_SKILL_DIR / "slots" / "script")]:
    if p not in sys.path:
        sys.path.insert(0, p)

from normalize   import normalize                # type: ignore
from router      import route, _load_keywords    # type: ignore
from serve       import classify                 # type: ignore
from slot_filler import fill_slots               # type: ignore
from resolver    import resolve_target           # type: ignore
from validator   import validate                 # type: ignore
from turn_writer import append_turn, new_turn_id # type: ignore
from lookup      import list_intents, lookup_intent  # type: ignore


def ground(
    utterance: str,
    session_context: dict | None = None,
    prev_turn_id: str | None = None,
    write_turn: bool = True,
    skip_llm: bool | None = None,
) -> dict:
    """
    utterance → GroundedCommand dict.

    Parameters
    ----------
    utterance       : 오퍼레이터 발화
    session_context : SessionContext dict (optional)
    prev_turn_id    : 직전 turn ID (optional)
    write_turn      : turns.jsonl append 여부 (테스트 시 False)
    skip_llm        : True면 inference slot LLM 호출 건너뜀

    Returns
    -------
    GroundedCommand dict (output.schema.json 준수)
    """
    t_start = time.monotonic()
    ctx = session_context or {}
    session_id = ctx.get("session_id", "local:anonymous:0")
    turn_id    = new_turn_id()

    # ── 1. input_norm ──────────────────────────────────────
    norm = normalize(utterance)

    # ── 2. rules (Lv10) ───────────────────────────────────
    keywords   = _load_keywords()
    intent_id, confidence = route(norm, keywords)
    tier = "Lv10"

    # ── 3. inference fallback (Lv30/Lv20) ─────────────────
    if intent_id is None:
        all_intents = list_intents()
        intent_id, confidence, tier = classify(norm, all_intents, skip_llm=skip_llm)

    # ── 4. script: slot_filler + resolver + validator ──────
    intent = lookup_intent(intent_id) if intent_id else None

    if intent:
        slots_filled, reprompt_needed, reprompt_slots = fill_slots(intent, norm, ctx)
        target_id, target_concepts = resolve_target(intent, slots_filled, ctx)
        conforms, violations = validate(intent, slots_filled, reprompt_slots)
        if not conforms:
            # SHACL 실패도 reprompt로 처리
            reprompt_needed = True
            for v in violations:
                # violation 메시지에서 슬롯 이름 파싱 (간단 방식)
                for spec in intent.get("slot_specs", []):
                    if spec["slot_name"] in v and spec["slot_name"] not in reprompt_slots:
                        reprompt_slots.append(spec["slot_name"])
    else:
        slots_filled   = {}
        reprompt_needed = False
        reprompt_slots  = []
        target_id       = None
        target_concepts = []

    duration_ms = int((time.monotonic() - t_start) * 1000)

    grounded: dict = {
        "intent_id":       intent_id,
        "target_id":       target_id,
        "target_concepts": target_concepts,
        "slots":           slots_filled,
        "confidence":      confidence,
        "tier":            tier,
        "reprompt_needed": reprompt_needed,
        "reprompt_slots":  reprompt_slots,
        "session_id":      session_id,
        "turn_id":         turn_id,
    }

    # ── 5. turns.jsonl append ──────────────────────────────
    if write_turn:
        append_turn(
            turn_id=turn_id,
            session_id=session_id,
            utterance=utterance,
            grounded=grounded,
            prev_turn_id=prev_turn_id,
            duration_ms=duration_ms,
        )

    return grounded
