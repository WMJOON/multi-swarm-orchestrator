"""
mso-intent-analytics — Lookup API
UUG(uug-grounding) 멀티-레지스트리 브리지 + 뒷단 dispatch(pipeline.py) + conversation-analytics 에서 호출.
RDFLib 기반, 별도 서버 없음.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, SKOS

# ─── 경로 설정 ───────────────────────────────────────────────
_SKILL_DIR = Path(__file__).parent.parent
_INSTANCES  = _SKILL_DIR / "instances"  / "intents.ttl"
_TAXONOMY_T = _SKILL_DIR / "taxonomy"   / "target_taxonomy.ttl"
_TAXONOMY_I = _SKILL_DIR / "taxonomy"   / "intent_taxonomy.ttl"
_MATRIX     = _SKILL_DIR / "matrix"     / "intent_matrix.ttl"

MSO = Namespace("https://mso.dev/ontology/")

# ─── entity_ref 패턴 → target concepts ──────────────────────
_ENTITY_PATTERNS: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"^ticket-\d+$",  re.I), ["TicketEvent"]),
    (re.compile(r"^run-\w+$",     re.I), ["RunContext"]),
    (re.compile(r"^wf-\w+$",      re.I), ["WorkflowEntity"]),
    (re.compile(r"^gate-\w+$",    re.I), ["RunContext", "HITLGateContext"]),
    (re.compile(r"^manifest-\w+$",re.I), ["RunManifest"]),
]


# ─── Graph 로드 (mtime 캐시) ─────────────────────────────────
_graph_cache: dict[str, tuple[float, Graph]] = {}

def _load_graph(path: Path) -> Graph:
    """파일 mtime 변경 시 자동 재로드."""
    key = str(path)
    mtime = path.stat().st_mtime
    if key not in _graph_cache or _graph_cache[key][0] != mtime:
        g = Graph()
        g.parse(str(path), format="turtle")
        _graph_cache[key] = (mtime, g)
    return _graph_cache[key][1]

def _intents_graph() -> Graph:
    return _load_graph(_INSTANCES)

def _target_graph() -> Graph:
    g = Graph()
    g.parse(str(_TAXONOMY_T), format="turtle")
    g.parse(str(_TAXONOMY_I), format="turtle")
    return g

def _matrix_graph() -> Graph:
    return _load_graph(_MATRIX)


# ─── Public API ──────────────────────────────────────────────

def list_intents() -> list[dict]:
    """
    모든 canonical intent 반환.
    Returns: [{"intent_id", "verb_concept", "target_concept",
               "trigger_keywords", "example_utterances", "slot_specs"}, ...]
    """
    g = _intents_graph()
    results = []
    for subj in g.subjects(RDF.type, MSO.Intent):
        results.append(_intent_to_dict(g, subj))
    return sorted(results, key=lambda x: x["intent_id"])


def lookup_intent(intent_id: str) -> dict | None:
    """
    intent_id로 Intent 레코드 조회.
    Returns: intent dict | None
    """
    g = _intents_graph()
    subj = MSO[intent_id]
    if (subj, RDF.type, MSO.Intent) not in g:
        return None
    return _intent_to_dict(g, subj)


def lookup_target(entity_ref: str) -> dict:
    """
    entity_ref(예: "ticket-217")로 target 개념 목록 반환.
    rule-based 패턴 매칭 우선, 미매칭 시 빈 목록.
    Returns: {"entity_ref": str, "target_concepts": list[str]}
    """
    concepts: list[str] = []
    for pattern, concept_list in _ENTITY_PATTERNS:
        if pattern.match(entity_ref):
            concepts = concept_list[:]
            break
    # FailedTicket / ActiveTicket 추론은 향후 context 주입으로 확장
    return {"entity_ref": entity_ref, "target_concepts": concepts}


def get_trigger_keywords(intent_id: str) -> list[str]:
    """intent의 trigger_keywords 목록만 빠르게 반환."""
    record = lookup_intent(intent_id)
    if record is None:
        return []
    return record.get("trigger_keywords", [])


def list_matrix_cells(status: str = "filled") -> list[dict]:
    """
    status 필터로 matrix cell 목록 반환.
    status: "filled" | "planned" | "rejected" | "*"
    """
    g = _matrix_graph()
    results = []
    for subj in g.subjects(RDF.type, MSO.IntentMatrixCell):
        cell_status = str(g.value(subj, MSO.status) or "")
        if status != "*" and cell_status != status:
            continue
        results.append({
            "cell_id":           str(g.value(subj, MSO.cell_id) or ""),
            "verb_concept":      _short(g.value(subj, MSO.verb_concept)),
            "target_concept":    _short(g.value(subj, MSO.target_concept)),
            "status":            cell_status,
            "intent_id":         str(g.value(subj, MSO.intent_id) or ""),
            "priority":          _int_or_none(g.value(subj, MSO.priority)),
            "rejected_rationale":str(g.value(subj, MSO.rejected_rationale) or ""),
        })
    return sorted(results, key=lambda x: x["cell_id"])


# ─── Internal helpers ────────────────────────────────────────

def _intent_to_dict(g: Graph, subj: URIRef) -> dict:
    def _list(pred):
        raw = g.value(subj, pred)
        if raw is None:
            return []
        # RDF list
        items = []
        node = raw
        while node and node != RDF.nil:
            first = g.value(node, RDF.first)
            if first is not None:
                items.append(str(first))
            node = g.value(node, RDF.rest)
        return items

    slot_specs = []
    for slot_node in _rdf_list_items(g, subj, MSO.slot_specs):
        slot_specs.append({
            "slot_name":     str(g.value(slot_node, MSO.slot_name) or ""),
            "slot_type":     str(g.value(slot_node, MSO.slot_type) or ""),
            "required":      str(g.value(slot_node, MSO.required) or "false").lower() == "true",
            "fill_policy":   str(g.value(slot_node, MSO.fill_policy) or "ask"),
            "default_value": str(g.value(slot_node, MSO.default_value) or "") or None,
        })

    return {
        "intent_id":          str(g.value(subj, MSO.intent_id) or ""),
        "verb_concept":       _short(g.value(subj, MSO.verb_concept)),
        "target_concept":     _short(g.value(subj, MSO.target_concept)),
        "trigger_keywords":   _list(MSO.trigger_keywords),
        "example_utterances": _list(MSO.example_utterances),
        "slot_specs":         slot_specs,
    }


def _rdf_list_items(g: Graph, subj: URIRef, pred) -> list:
    """RDF list (rdf:first/rdf:rest) 순회."""
    raw = g.value(subj, pred)
    if raw is None:
        return []
    items = []
    node = raw
    while node and node != RDF.nil:
        first = g.value(node, RDF.first)
        if first is not None:
            items.append(first)
        node = g.value(node, RDF.rest)
        if node is None:
            break
    return items


def _short(uri) -> str:
    """URIRef → 로컬명 (예: mso:QueryVerb → 'QueryVerb')."""
    if uri is None:
        return ""
    s = str(uri)
    if "#" in s:
        return s.split("#")[-1]
    if "/" in s:
        return s.split("/")[-1]
    return s


def _int_or_none(val) -> int | None:
    if val is None:
        return None
    try:
        return int(str(val))
    except ValueError:
        return None
