"""
script slot — SHACL Validator (+ 직접 required-slot 검증 fallback)
SHACL 파일 없으면 SlotSpec required 직접 확인으로 대체.
"""
from __future__ import annotations
from pathlib import Path

_SHACL_PATH = (
    Path(__file__).parent.parent / "generated" / "nlu_intent.shacl.ttl"
)


def validate(
    intent: dict,
    slots_filled: dict,
    reprompt_slots: list[str],
) -> tuple[bool, list[str]]:
    """
    Returns: (conforms, violation_messages)
    conforms=True  → SHACL OK
    conforms=False → violations 목록 반환
    """
    # 방법 1: SHACL 파일 있으면 pyshacl 사용
    if _SHACL_PATH.exists():
        return _shacl_validate(intent, slots_filled, reprompt_slots)

    # 방법 2: fallback — required 슬롯 직접 체크
    return _direct_validate(intent, slots_filled)


def _direct_validate(
    intent: dict,
    slots_filled: dict,
) -> tuple[bool, list[str]]:
    """SlotSpec.required 기반 직접 검증."""
    violations = []
    for spec in intent.get("slot_specs", []):
        if spec.get("required") and spec["slot_name"] not in slots_filled:
            violations.append(
                f"{intent['intent_id']} requires slot '{spec['slot_name']}'"
            )
    return (len(violations) == 0), violations


def _shacl_validate(
    intent: dict,
    slots_filled: dict,
    reprompt_slots: list[str],
) -> tuple[bool, list[str]]:
    """pyshacl 사용 검증. SHACL 파일이 존재할 때만 호출됨."""
    try:
        from pyshacl import validate as shacl_validate  # type: ignore
        from rdflib import Graph, Literal, Namespace, RDF, URIRef  # type: ignore

        MSO = Namespace("https://mso.dev/ontology/")
        data_g = Graph()
        intent_id = intent.get("intent_id", "unknown")
        subj = URIRef(f"https://mso.dev/command/{intent_id}")
        data_g.add((subj, RDF.type, MSO.GroundedCommand))
        data_g.add((subj, MSO.intent_id, Literal(intent_id)))
        for k, v in slots_filled.items():
            data_g.add((subj, MSO[k], Literal(str(v))))

        shapes_g = Graph()
        shapes_g.parse(str(_SHACL_PATH), format="turtle")

        conforms, _, report = shacl_validate(data_g, shacl_graph=shapes_g)
        if not conforms:
            violations = [str(report)]
            return False, violations
        return True, []
    except Exception as e:
        # SHACL 실패 시 fallback
        return _direct_validate(intent, slots_filled)
