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


# ─── CLI 진입점 (§11 배선: UUG→MSO subprocess 경계) ──────────────
# UUG(uug-grounding)가 앞단(utterance→intent)을 끝낸 뒤, 도메인 intent 의
# 뒷단(slot→target→validate→turn)을 이 CLI 로 위임한다. 프로세스 경계로
# 디커플 — MSO 는 UUG 를 import 하지 않고 stdout JSON 만 계약으로 노출한다.
def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(
        prog="mso-dispatch",
        description="MSO intent→action 뒷단 (intent_id → GroundedCommand JSON).",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("ground", help="intent_id + 발화 → GroundedCommand JSON (stdout)")
    g.add_argument("--intent-id", required=True, help="UUG 가 해석한 intent_id (필수)")
    g.add_argument("--utterance", required=True, help="slot 추출용 원문 발화")
    g.add_argument("--session-context", default=None, help="SessionContext JSON (선택)")
    g.add_argument("--no-write", action="store_true", help="turns.jsonl append 생략(테스트)")
    args = ap.parse_args(argv)

    if args.cmd == "ground":
        ctx = json.loads(args.session_context) if args.session_context else None
        grounded = ground(
            args.utterance,
            intent_id=args.intent_id,
            session_context=ctx,
            write_turn=not args.no_write,
        )
        print(json.dumps(grounded, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
