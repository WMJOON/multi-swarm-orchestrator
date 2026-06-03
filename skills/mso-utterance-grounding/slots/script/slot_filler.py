"""
script slot — Slot Filler
SessionContext + utterance token 추출로 SlotSpec 채움.
required 미충족 시 reprompt_needed=True.
"""
from __future__ import annotations
import re


def fill_slots(
    intent: dict,
    utterance: str,
    session_ctx: dict,
) -> tuple[dict, bool, list[str]]:
    """
    Returns:
        slots_filled    : {slot_name: value}
        reprompt_needed : required 슬롯이 채워지지 않으면 True
        reprompt_slots  : 미충족 required 슬롯 이름 목록
    """
    slots_filled: dict    = {}
    reprompt_slots: list[str] = []

    for spec in intent.get("slot_specs", []):
        name   = spec["slot_name"]
        policy = spec.get("fill_policy", "ask")
        req    = spec.get("required", False)

        value = (
            _extract_from_utterance(utterance, name, spec)
            or _from_session(session_ctx, name)
            or (spec.get("default_value") if policy == "default" else None)
        )

        if value is not None:
            slots_filled[name] = value
        elif req:
            reprompt_slots.append(name)

    return slots_filled, bool(reprompt_slots), reprompt_slots


# ─── 추출 헬퍼 ───────────────────────────────────────────────

_ENTITY_PATTERNS = {
    "ticket_ref":   re.compile(r"\bticket-\w+\b", re.I),
    "run_ref":      re.compile(r"\brun-\w+\b",    re.I),
    "workflow_ref": re.compile(r"\bwf-\w+\b",     re.I),
    "gate_ref":     re.compile(r"\b[Hh]\d+\s*gate\b|\bgate-\w+\b", re.I),
}

_PRIORITY_WORDS = {
    "높여": "high", "높게": "high", "올려": "high", "high": "high",
    "낮춰": "low",  "낮게": "low",  "내려": "low",  "low": "low",
    "보통": "normal", "normal": "normal",
    "긴급": "urgent", "urgent": "urgent",
}


def _extract_from_utterance(utterance: str, slot_name: str, spec: dict) -> str | None:
    slot_type = spec.get("slot_type", "free_text")

    if slot_type == "entity_ref":
        pat = _ENTITY_PATTERNS.get(slot_name)
        if pat:
            m = pat.search(utterance)
            return m.group(0).lower() if m else None

    if slot_name == "new_priority":
        utt_lower = utterance.lower()
        for word, val in _PRIORITY_WORDS.items():
            if word in utt_lower:
                return val
        return None

    if slot_type == "free_text":
        # task_description 등 — 전체 utterance를 fallback으로
        if slot_name == "task_description":
            return utterance.strip() or None

    return None


def _from_session(session_ctx: dict, slot_name: str) -> str | None:
    """SessionContext 필드에서 슬롯 값 추출."""
    mapping = {
        "run_ref":      lambda s: (s.get("run_ids") or [None])[0],
        "workflow_ref": lambda s: s.get("last_referenced_entity"),
        "gate_ref":     lambda s: s.get("last_referenced_entity"),
        "ticket_ref":   lambda s: s.get("last_referenced_entity"),
    }
    fn = mapping.get(slot_name)
    return fn(session_ctx) if fn and session_ctx else None
