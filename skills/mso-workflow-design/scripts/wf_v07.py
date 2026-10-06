#!/usr/bin/env python3
"""wf_v07 — v0.7.0-r2 Execution/hand_off/WorkflowGraph 온톨로지 공용 모듈.

SPEC: planning/mso-v0.7.0-SPEC-rail-stream-ontology.md (§6-B r2, D-13~D-16)

역할:
  1) v0.7 어휘 상수 (railType/streamType, layer·hand_off 파생 규칙, subject 어휘)
  2) v0.7 그래프 감지 (`is_v07_graph`) — 클래스명이 아니라 Rail/Stream/Execution
     존재로 판별한다 (wf:Task/Decision/Eval 은 v0.6과 이름을 공유, Q-4(a))
  3) v0.6 호환 projection (`project_v06_compat`) — deprecated, 외부 v0.6 소비자
     전환 지원용
  4) 제어 흐름 추출 (`control_graph`) — 실행 엔진·분석 도구가 읽는
     정본 추출기. 어떤 Rail 이 제어 흐름이고 무엇이 아닌지의 판단을 이 모듈이 소유한다.

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


# ── 제어 흐름 추출 (실행 엔진용 정본) ────────────────────────────────────────

CONTROL_RAILS = {"default", "escalates_to"}  # 흐름을 옮기는 Rail. reads/delegates_to/oracle 은 제어 흐름이 아니다.


def _node_id(node) -> str:
    """IRI 의 마지막 조각(# 우선, 없으면 /). 실행 엔진이 노드 키로 쓴다."""
    text = str(node)
    if "#" in text:
        text = text.rsplit("#", 1)[1]
    return text.rsplit("/", 1)[-1] if "/" in text else text


def _literal(g: Graph, node, pred) -> str | None:
    value = g.value(node, pred)
    return str(value) if isinstance(value, Literal) else None


def control_graph(g: Graph) -> dict:
    """v0.7 workflow 의 제어 흐름을 실행 엔진이 쓰기 좋은 구조로 추출한다 (원본 불변, 결정론).

    반환:
      nodes: [{id, uri, kind(task|decision|eval|event|end), label, subject, status, instruction, criteria, method, harness}]
      edges: [{source, target, type(default|escalates_to), on}]  — 제어 Rail 만
      entrypoints: Start 에서 default Rail 로 이어지는 노드 id
      ignored: [{rail, railType, reason}] — 제어 흐름이 아니어서 건너뛴 Rail (reads/delegates_to/oracle 등)
      errors: [str] — 실행 그래프로 만들 수 없는 결함(끝점이 Execution/Start/End 가 아님, from/to 없음, 출구 없는 Decision 등)
      warnings: [str] — 실행은 가능하나 의미가 손실되는 경우(subject 누락·미지, hasSubject=workflow 는 하위 workflow 로 펼치지 않음 등)
    errors 가 비어 있지 않으면 소비자는 컴파일을 중단해야 한다(조용히 일부만 쓰지 않는다).
    """
    nodes: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []
    ids: dict = {}

    def add(node, kind: str) -> None:
        subject = execution_subject(g, node) if kind not in {"end", "event"} else None
        declared = g.value(node, WF.hasSubject)
        if kind not in {"end", "event"}:
            if declared is None:
                warnings.append(f"{_node_id(node)}: wf:hasSubject missing, treated as self")
            elif str(declared) not in SUBJECTS:
                warnings.append(f"{_node_id(node)}: unknown wf:hasSubject {str(declared)!r}, treated as self")
            if subject == "workflow":
                warnings.append(f"{_node_id(node)}: hasSubject=workflow (sub-workflow) is not expanded; treated as a single node")
        ids[node] = _node_id(node)
        nodes.append({
            "id": _node_id(node), "uri": str(node), "kind": kind, "label": _label(g, node), "subject": subject,
            "status": _literal(g, node, WF.status), "instruction": _literal(g, node, WF.instruction),
            "criteria": [str(v) for v in g.objects(node, WF.criteria)],
            "method": _literal(g, node, WF.method), "harness": _literal(g, node, WF.harness),
        })

    for node in sorted(g.subjects(RDF.type, WF.Execution), key=str):
        kind = "decision" if _is_a(g, node, WF.Decision) else "eval" if _is_a(g, node, WF.Eval) else "task"
        add(node, kind)
    for node in sorted(g.subjects(RDF.type, WF.End), key=str):
        add(node, "end")
    # wf:Event 는 v0.6 에서 온 트리거 클래스다(스케줄러·웹훅 등). v0.7 TBox 에는 없지만 기존 workflow 가
    # Start 다음 진입 노드로 계속 쓰므로 거부하지 않고 트리거 노드(event)로 받는다.
    for node in sorted(g.subjects(RDF.type, WF.Event), key=str):
        if node in ids:
            continue
        warnings.append(f"{_node_id(node)}: wf:Event is a v0.6 trigger class not defined in the v0.7 TBox; treated as an entry trigger node")
        add(node, "event")
    starts = set(g.subjects(RDF.type, WF.Start))

    edges: list[dict] = []
    ignored: list[dict] = []
    entrypoints: set[str] = set()
    for rail in sorted(g.subjects(RDF.type, WF.Rail), key=str):
        rail_type = _rail_type(g, rail) or "default"
        if not _rail_type(g, rail):
            warnings.append(f"{_node_id(rail)}: wf:railType missing, treated as default")
        if rail_type not in CONTROL_RAILS:
            ignored.append({"rail": _node_id(rail), "railType": rail_type,
                            "reason": "data/oracle/tool rail, not control flow" if rail_type in RAIL_TYPES else "unknown railType"})
            continue
        source, target = g.value(rail, WF["from"]), g.value(rail, WF.to)
        if source is None or target is None:
            errors.append(f"{_node_id(rail)}: wf:from/wf:to missing")
            continue
        if target not in ids or (source not in ids and source not in starts):
            errors.append(f"{_node_id(rail)}: endpoint is not an Execution/Start/End: {_node_id(source)} -> {_node_id(target)}")
            continue
        if source in starts:
            entrypoints.add(ids[target])
            continue
        edges.append({"source": ids[source], "target": ids[target], "type": rail_type, "on": _literal(g, rail, WF.on)})

    for n in nodes:
        if n["kind"] != "decision":
            continue
        outs = [e for e in edges if e["source"] == n["id"]]
        if not outs:
            errors.append(f"{n['id']}: Decision has no outgoing control rail")
        for e in outs:
            if not e["on"]:
                warnings.append(f"{n['id']}: decision rail to {e['target']} has no wf:on")
    if not entrypoints:
        warnings.append("no Start rail found")
    return {"nodes": nodes, "edges": edges, "entrypoints": sorted(entrypoints),
            "ignored": ignored, "errors": errors, "warnings": warnings}
