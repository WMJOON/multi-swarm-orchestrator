"""
script slot — Target Resolver
entity_ref 후보를 slots_filled에서 찾아 mso-intent-registry.lookup_target() 호출.
"""
from __future__ import annotations
import sys
from pathlib import Path

_REGISTRY_SRC = Path(__file__).parent.parent.parent.parent / \
    "mso-intent-registry" / "src"
if str(_REGISTRY_SRC) not in sys.path:
    sys.path.insert(0, str(_REGISTRY_SRC))

# entity_ref로 쓸 수 있는 슬롯 이름 (우선순위 순)
_ENTITY_REF_SLOTS = ["ticket_ref", "run_ref", "workflow_ref", "gate_ref"]


def resolve_target(
    intent: dict,
    slots_filled: dict,
    session_ctx: dict,
) -> tuple[str | None, list[str]]:
    """
    Returns: (target_id, target_concepts)
    """
    from lookup import lookup_target  # type: ignore

    # 1) slots_filled에서 entity_ref 슬롯 탐색
    entity_ref = _find_entity_ref(intent, slots_filled)

    # 2) 없으면 session_ctx.last_referenced_entity fallback
    if entity_ref is None and session_ctx:
        entity_ref = session_ctx.get("last_referenced_entity")

    if entity_ref is None:
        return None, []

    result = lookup_target(entity_ref)
    return result["entity_ref"], result["target_concepts"]


def _find_entity_ref(intent: dict, slots_filled: dict) -> str | None:
    # 우선순위 슬롯 목록에서 먼저 시도
    for name in _ENTITY_REF_SLOTS:
        if name in slots_filled:
            return slots_filled[name]
    # slot_specs에서 entity_ref 타입 슬롯 순서대로 시도
    for spec in intent.get("slot_specs", []):
        if spec.get("slot_type") == "entity_ref":
            name = spec["slot_name"]
            if name in slots_filled:
                return slots_filled[name]
    return None
