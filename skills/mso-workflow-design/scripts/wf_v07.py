#!/usr/bin/env python3
"""wf_v07 — v0.7.0-r2 Execution/hand_off/WorkflowGraph 온톨로지 공용 모듈.

SPEC: planning/mso-v0.7.0-SPEC-rail-stream-ontology.md (§6-B r2, D-13~D-16)

역할:
  1) v0.7 어휘 상수 (railType/streamType, layer·hand_off 파생 규칙, subject 어휘)
  2) v0.7 그래프 감지 (`is_v07_graph`) — 클래스명이 아니라 Rail/Stream/Execution
     존재로 판별한다 (wf:Task/Decision/Eval 은 v0.6과 이름을 공유, Q-4(a))
  3) v0.6 호환 projection (`project_v06_compat`) — deprecated, 외부 v0.6 소비자
     전환 지원용

호환 projection 대응표 (v0.7-r2 → v0.6):
  Task(Execution)              → wf:Step + wf:Task + wf:Node
  Decision (hasSubject)        → wf:Decision + wf:Node (human→user, 그외→agent)
  Eval (hasSubject)            → wf:Eval + wf:Node (human→user, system→metric, 그외→agent)
  Workflow wf:has              → wf:hasNode (Start/End/Artifact 제외)
  Rail default                 → wf:next / (on 있으면) Branch bnode 합성
  Rail reads                   → wf:consumes (Artifact→Execution)
  Rail delegates_to            → wf:usesTool "[[subjectDetail|label]]"
  Rail escalates_to            → wf:next (v0.6 등가물 없음 — 제어 흐름만 보존)
  Rail measured_by             → wf:measures (+ Eval wf:targetArtifact locator)
  Rail measures                → wf:target (Eval→Workflow)
  Rail evolves_to|tests_to     → wf:evolves (Workflow 대상만 — D-12 artifact 대상 제외)
  Stream consumed_by           → wf:consumes / produces_to → wf:produces
  Stream evidence_of           → (v0.6 등가물 없음 — 통과)
  Start/End                    → 파생 제외 (관측기가 boundary 합성)
"""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, Namespace, RDF, RDFS, URIRef

WF = Namespace("https://mso.dev/ontology/workflow#")

RAIL_TYPES = {
    "default", "reads", "delegates_to", "escalates_to",
    "measured_by", "measures", "evolves_to", "tests_to",
}
STREAM_TYPES = {"consumed_by", "produces_to", "evidence_of"}
BASE_RAILS = {"default", "reads", "delegates_to", "escalates_to"}
ORACLE_RAILS = {"measured_by", "measures", "evolves_to", "tests_to"}
HAND_OFF_RAILS = {"delegates_to", "escalates_to"}

SUBJECTS = {"self", "human", "model", "system", "workflow"}
# v0.6 subject 매핑 (Q-6 확정): user→human, agent→self, metric→system
V06_SUBJECT_MAP = {"user": "human", "agent": "self", "metric": "system"}

EXECUTION_CLASSES = (WF.Task, WF.Decision, WF.Eval)

METRIC_DIMENSIONS = {"trust", "quality", "cost", "speed", "safety", "robustness", "resource_usage"}


def rail_layer(rail_type: str) -> str:
    """Rail layer는 railType에서 파생한다 (D-5) — 저장하지 않는다."""
    if rail_type in ORACLE_RAILS:
        return "oracle"
    if rail_type in BASE_RAILS:
        return "base"
    return "unknown"


def is_hand_off(rail_type: str) -> bool:
    """hand_off = delegates_to | escalates_to 의 상위 개념 (D-15, 파생)."""
    return rail_type in HAND_OFF_RAILS


def execution_subject(g: Graph, node) -> str:
    """Execution의 실행 주체. 미선언은 self (D-14 기본값)."""
    value = g.value(node, WF.hasSubject)
    if isinstance(value, Literal) and str(value) in SUBJECTS:
        return str(value)
    return "self"


def is_v07_graph(g: Graph) -> bool:
    """Rail/Stream/Execution 존재로 판별 — 클래스명(wf:Task 등)은 v0.6과 공유되므로 쓰지 않는다."""
    for cls in (WF.Rail, WF.Stream, WF.Execution):
        if next(g.subjects(RDF.type, cls), None) is not None:
            return True
    return False


def _label(g: Graph, node: URIRef) -> str:
    value = g.value(node, RDFS.label) or g.value(node, WF.label)
    if isinstance(value, Literal):
        return str(value)
    text = str(node)
    return text.rsplit("/", 1)[-1] if "/" in text else text


def _rail_type(g: Graph, rail: URIRef) -> str:
    value = g.value(rail, WF.railType)
    return str(value) if isinstance(value, Literal) else ""


def _is_a(g: Graph, node, cls) -> bool:
    return (node, RDF.type, cls) in g


def _local_id(node: URIRef) -> str:
    text = str(node)
    return text.rsplit("/", 1)[-1] if "/" in text else text


def project_v06_compat(g: Graph) -> Graph:
    """v0.7 그래프에 v0.6 호환 술어를 파생해 합친 그래프를 반환한다.

    원본은 수정하지 않는다. 반환 그래프 = 원본 복사 + 파생 triple.

    .. deprecated:: A-phase (2026-07-02)
        관측 경로는 observe_v07(네이티브 렌더)로 전환됐다. 이 projection은
        아직 v0.6 술어를 읽는 외부 소비자의 전환 지원용으로만 남아 있으며,
        A-phase 완료(소비 프로젝트 마이그레이션) 후 제거 예정.
    """
    out = Graph()
    for triple in g:
        out.add(triple)

    def compat_subject(node, *, for_eval: bool) -> str:
        subject = execution_subject(g, node)
        if subject == "human":
            return "user"
        if for_eval and subject == "system":
            return "metric"
        return "agent"

    # ── Execution 유형 → v0.6 노드 클래스 ────────────────────────────────
    for node in g.subjects(RDF.type, WF.Execution):
        if _is_a(g, node, WF.Eval):
            out.add((node, WF.oracleType, Literal(compat_subject(node, for_eval=True))))
        elif _is_a(g, node, WF.Decision):
            out.add((node, WF.decisionSubject, Literal(compat_subject(node, for_eval=False))))
        else:
            out.add((node, RDF.type, WF.Step))
            out.add((node, RDF.type, WF.Task))
        out.add((node, RDF.type, WF.Node))

    # ── Workflow membership: wf:has → wf:hasNode ─────────────────────────
    for workflow, node in g.subject_objects(WF.has):
        if _is_a(g, node, WF.Start) or _is_a(g, node, WF.End) or _is_a(g, node, WF.Artifact):
            continue
        out.add((workflow, WF.hasNode, node))

    # ── Rail → v0.6 제어 술어 ────────────────────────────────────────────
    for rail in g.subjects(RDF.type, WF.Rail):
        rail_type = _rail_type(g, rail)
        source = g.value(rail, WF["from"])
        target = g.value(rail, WF.to)
        if source is None or target is None:
            continue

        if rail_type == "default":
            if _is_a(g, source, WF.Start):
                continue
            on_case = g.value(rail, WF.on)
            if isinstance(on_case, Literal):
                branch = BNode()
                out.add((source, WF.hasBranch, branch))
                out.add((branch, RDF.type, WF.Branch))
                out.add((branch, WF.on, on_case))
                criteria = g.value(rail, WF.criteria)
                if isinstance(criteria, Literal):
                    out.add((branch, WF.criteria, criteria))
                if not _is_a(g, target, WF.End):
                    out.add((branch, WF.gotoNode, target))
                    out.add((branch, WF.goto, Literal(_local_id(target))))
            else:
                if _is_a(g, target, WF.End):
                    continue
                out.add((source, WF.next, target))

        elif rail_type == "reads":
            out.add((source, WF.consumes, target))

        elif rail_type == "delegates_to":
            detail = g.value(target, WF.subjectDetail)
            name = str(detail) if isinstance(detail, Literal) else f"[[{_label(g, target)}]]"
            if not name.startswith("[["):
                name = f"[[{name}]]"
            out.add((source, WF.usesTool, Literal(name)))

        elif rail_type == "escalates_to":
            out.add((source, WF.next, target))  # v0.6 등가물 없음 — 제어 흐름만

        elif rail_type == "measured_by":
            out.add((source, WF.measures, target))
            locator = g.value(source, WF.locator)
            if isinstance(locator, Literal):
                out.add((target, WF.targetArtifact, locator))

        elif rail_type == "measures":
            out.add((source, WF.target, target))

        elif rail_type in {"evolves_to", "tests_to"}:
            if not _is_a(g, target, WF.Artifact):
                out.add((source, WF.evolves, target))

    # ── Stream → v0.6 공급망 술어 ────────────────────────────────────────
    for stream in g.subjects(RDF.type, WF.Stream):
        stream_type = g.value(stream, WF.streamType)
        stream_type = str(stream_type) if isinstance(stream_type, Literal) else ""
        source = g.value(stream, WF["from"])
        target = g.value(stream, WF.to)
        if source is None or target is None:
            continue
        if stream_type == "consumed_by":
            out.add((source, WF.consumes, target))
        elif stream_type == "produces_to":
            out.add((source, WF.produces, target))

    # ── Artifact 라벨 보정 ────────────────────────────────────────────────
    for artifact in g.subjects(RDF.type, WF.Artifact):
        if g.value(artifact, RDFS.label) is None and g.value(artifact, WF.label) is None:
            locator = g.value(artifact, WF.locator)
            if isinstance(locator, Literal):
                out.add((artifact, RDFS.label, locator))

    return out
