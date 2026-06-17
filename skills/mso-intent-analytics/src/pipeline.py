"""
dispatch — Grounding Pipeline 뒷단 (intent → GroundedCommand).

slot_filler → resolver → validator → turn_writer → GroundedCommand 반환.

§11: utterance→intent 분류(앞단: normalize/router/serve)는 UUG(uug-grounding)로 흡수됐다.
이 모듈은 **뒷단만** — 이미 해석된 intent_id 를 받아 slot 채움·target 해소·검증·기록한다.
orchestration 이 `ug ground` 로 얻은 intent_id 를 넘긴다(디커플: UUG import 없음).
lookup 과 같은 스킬(mso-intent-analytics)에 co-located.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# ─── 경로 주입 (sibling 모듈: 같은 src/) ─────────────────────
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from normalize   import normalize                # type: ignore
from slot_filler import fill_slots               # type: ignore
from resolver    import resolve_target           # type: ignore
from validator   import validate                 # type: ignore
from turn_writer import append_turn, new_turn_id # type: ignore
from lookup      import lookup_intent            # type: ignore


def ground(
    utterance: str,
    intent_id: str,
    session_context: dict | None = None,
    prev_turn_id: str | None = None,
    write_turn: bool = True,
) -> dict:
    """
    (utterance, intent_id) → GroundedCommand dict.

    Parameters
    ----------
    utterance       : 오퍼레이터 발화 (slot 추출용 원문)
    intent_id       : UUG(uug-grounding)가 해석한 intent_id. **필수** — 앞단(분류)은
                      UUG 가 담당(§11). orchestration 이 `ug ground` 결과를 넘긴다.
    session_context : SessionContext dict (optional)
    prev_turn_id    : 직전 turn ID (optional)
    write_turn      : turns.jsonl append 여부 (테스트 시 False)

    Returns
    -------
    GroundedCommand dict (schemas/output.schema.json 준수). tier="UUG".
    """
    t_start = time.monotonic()
    ctx = session_context or {}
    session_id = ctx.get("session_id", "local:anonymous:0")
    turn_id    = new_turn_id()

    # ── 1. input_norm (slot 추출 전처리) ───────────────────
    norm = normalize(utterance)

    # ── 2. 뒷단: slot_filler + resolver + validator ────────
    intent = lookup_intent(intent_id) if intent_id else None

    if intent:
        slots_filled, reprompt_needed, reprompt_slots = fill_slots(intent, norm, ctx)
        target_id, target_concepts = resolve_target(intent, slots_filled, ctx)
        conforms, violations = validate(intent, slots_filled, reprompt_slots)
        if not conforms:
            # SHACL 실패도 reprompt로 처리
            reprompt_needed = True
            for v in violations:
                for spec in intent.get("slot_specs", []):
                    if spec["slot_name"] in v and spec["slot_name"] not in reprompt_slots:
                        reprompt_slots.append(spec["slot_name"])
    else:
        slots_filled    = {}
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
        "confidence":      1.0 if intent else 0.0,
        "tier":            "UUG",
        "reprompt_needed": reprompt_needed,
        "reprompt_slots":  reprompt_slots,
        "session_id":      session_id,
        "turn_id":         turn_id,
    }

    # ── 3. turns.jsonl append ──────────────────────────────
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
