#!/usr/bin/env python3
"""observe_v07 — v0.7 Rail/Stream 네이티브 관측 렌더러 (A-phase).

SPEC: planning/mso-v0.7.0-SPEC-rail-stream-ontology.md

v0.6 렌더러(observe_graph.build_workflow_topology)와 달리 호환 projection 없이
wf:Rail / wf:Stream 인스턴스를 직접 순회한다. edge가 일급이므로 순회가 자명하다:

  Repository Graph = Execution Rail(Control/Execution, Rail)
                   + Data SupplyChain Graph(Artifact Stream, Stream)

렌더 원칙 (v0.6.7에서 확립된 경계 유지):
- TTL에 없는 의미를 창작하지 않는다. artifact_type은 명시 wf:artifactType만 사용
  (휴리스틱 추론 없음 — 미선언은 unspecified로 표기).
- Start/End는 정본 노드를 그대로 렌더한다 (boundary 합성 없음).
- Executor는 [[...]] subroutine, realizedBy는 sub-workflow 링크로 렌더한다.
"""

from __future__ import annotations

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef

WF = Namespace("https://mso.dev/ontology/workflow#")

MACHINE_NATIVE = {"knowledge_store", "event_store", "local_database", "table"}
MERMAID_LINE_BREAK = "<br/>"

RAIL_EDGE_STYLE = {
    # railType → (arrow, label)  — on 이 있으면 항상 -.->|on: x|
    # hand_off(delegates_to/escalates_to)는 주체 전환 — 점선 (D-15)
    "default": ("-->", None),
    "reads": ("-.->", "reads"),
    "delegates_to": ("-.->", "delegates_to"),
    "escalates_to": ("-.->", "escalates_to"),
    "measured_by": ("-.->", "measured_by"),
    "measures": ("--o", "measures"),
    "evolves_to": ("-->", "evolves_to"),
    "tests_to": ("-->", "tests_to"),
}

STREAM_EDGE_STYLE = {
    "consumed_by": ("-->", "consumed_by"),
    "produces_to": ("-->", "produces_to"),
    "evidence_of": ("-.->", "evidence_of"),
}

CLASS_DEFS = [
    "  classDef start fill:#dcfce7,stroke:#16a34a,color:#111827",
    "  classDef end_ fill:#fee2e2,stroke:#991b1b,color:#111827",
    "  classDef task fill:#dbeafe,stroke:#2563eb,color:#111827",
    "  classDef decision fill:#ffedd5,stroke:#ea580c,color:#111827",
    "  classDef eval fill:#fee2e2,stroke:#dc2626,color:#111827",
    "  classDef executor fill:#f5f3ff,stroke:#7c3aed,color:#111827",
    "  classDef artifact fill:#f0fdf4,stroke:#15803d,color:#111827",
    "  classDef workflow fill:#eef2ff,stroke:#4f46e5,color:#111827",
]


# ─── 그래프 질의 ────────────────────────────────────────────────────────────


def _text(value) -> str:
    return str(value) if isinstance(value, Literal) else ""


def _local(term) -> str:
    text = str(term)
    return text.rsplit("/", 1)[-1] if "/" in text else text


def _label(g: Graph, node) -> str:
    for predicate in (RDFS.label, WF.label):
        value = g.value(node, predicate)
        if isinstance(value, Literal):
            return str(value)
    return _local(node)


def v07_workflows(g: Graph) -> dict[URIRef, str]:
    """workflowType이 선언된 workflow → scope 문자열.

    v0.6 관측 경로와 출력 디렉토리를 공유하기 위해 URI 마지막 세그먼트를 쓴다
    (v0.6 scope는 `node/<scope>/<id>`의 첫 세그먼트 = workflow URI 마지막 세그먼트).
    """
    out: dict[URIRef, str] = {}
    for workflow in sorted(g.subjects(WF.workflowType, None), key=str):
        if isinstance(workflow, URIRef):
            out[workflow] = _local(workflow)
    return out


def is_v07_graph(g: Graph) -> bool:
    for cls in (WF.Rail, WF.Stream):
        if next(g.subjects(RDF.type, cls), None) is not None:
            return True
    return False


def _members(g: Graph, workflow: URIRef) -> set[URIRef]:
    return {n for n in g.objects(workflow, WF.has) if isinstance(n, URIRef)}


def _edges(g: Graph, edge_class: URIRef, type_pred: URIRef) -> list[dict]:
    edges = []
    for edge in sorted(g.subjects(RDF.type, edge_class), key=str):
        source = g.value(edge, WF["from"])
        target = g.value(edge, WF.to)
        if not isinstance(source, URIRef) or not isinstance(target, URIRef):
            continue
        edges.append({
            "uri": edge,
            "from": source,
            "to": target,
            "type": _text(g.value(edge, type_pred)),
            "on": _text(g.value(edge, WF.on)),
            "criteria": _text(g.value(edge, WF.criteria)),
            "derived": _text(g.value(edge, WF.derived)) == "true",
        })
    return edges


def rails(g: Graph) -> list[dict]:
    return _edges(g, WF.Rail, WF.railType)


def streams(g: Graph) -> list[dict]:
    return _edges(g, WF.Stream, WF.streamType)


# ─── Mermaid 노드 렌더 ──────────────────────────────────────────────────────


def _mermaid_id(term: URIRef) -> str:
    import re
    return "n_" + re.sub(r"[^0-9A-Za-z_]", "_", str(term).split("#", 1)[-1])


def _esc(text: str, max_len: int = 72) -> str:
    text = text.replace('"', "'")
    return text[: max_len - 1] + "…" if len(text) > max_len else text


def _node_decl(g: Graph, node: URIRef) -> tuple[str, str]:
    """(mermaid 선언 라인, css class) — 노드 클래스별 shape."""
    node_id = _mermaid_id(node)
    label = _esc(_label(g, node))
    local = _esc(_local(node), 40)

    def has(cls) -> bool:
        return (node, RDF.type, cls) in g

    if has(WF.Start):
        return f'  {node_id}(("start")):::start', "start"
    if has(WF.End):
        return f'  {node_id}(("end")):::end_', "end_"
    def subject_of(n) -> str:
        value = g.value(n, WF.hasSubject)
        text = _text(value)
        return text if text else "self"

    if has(WF.Eval):
        suffix = f"{MERMAID_LINE_BREAK}subject: {subject_of(node)}"
        return f'  {node_id}[/"{label}{MERMAID_LINE_BREAK}id: {local}{MERMAID_LINE_BREAK}Eval{suffix}"\\]:::eval', "eval"
    if has(WF.Decision):
        suffix = f"{MERMAID_LINE_BREAK}subject: {subject_of(node)}"
        return f'  {node_id}{{{{"{label}{MERMAID_LINE_BREAK}id: {local}{MERMAID_LINE_BREAK}Decision{suffix}"}}}}:::decision', "decision"
    if has(WF.Task):
        return f'  {node_id}["{label}{MERMAID_LINE_BREAK}id: {local}{MERMAID_LINE_BREAK}Task"]:::task', "task"
    if has(WF.Execution):
        # 유형 미지정 Execution — hand_off 대상(주체≠self)은 [[...]] subroutine (D-15)
        subject = subject_of(node)
        if subject != "self":
            detail = _text(g.value(node, WF.subjectDetail))
            extra = f"{MERMAID_LINE_BREAK}{_esc(detail, 40)}" if detail else ""
            return f'  {node_id}[["{label}{MERMAID_LINE_BREAK}subject: {subject}{extra}"]]:::executor', "executor"
        return f'  {node_id}["{label}{MERMAID_LINE_BREAK}id: {local}{MERMAID_LINE_BREAK}Execution"]:::task', "task"
    if has(WF.Artifact):
        artifact_type = _text(g.value(node, WF.artifactType)) or "unspecified"
        locator = _text(g.value(node, WF.locator))
        body = f"{_esc(locator) or label}{MERMAID_LINE_BREAK}{artifact_type.upper()}"
        if artifact_type in MACHINE_NATIVE:
            return f'  {node_id}[("{body}")]:::artifact', "artifact"
        return f'  {node_id}@{{ shape: doc, label: "{body}" }}', "artifact"
    if has(WF.Workflow):
        return f'  {node_id}(["Workflow: {label}"]):::workflow', "workflow"
    return f'  {node_id}["{label}"]', ""


def _edge_line(edge: dict, style_map: dict) -> str:
    arrow, label = style_map.get(edge["type"], ("-->", edge["type"]))
    if edge.get("derived") and label:
        label = f"{label}*"  # D-21: 추론 파생 edge — 저장 관계와 구분
    source_id = _mermaid_id(edge["from"])
    target_id = _mermaid_id(edge["to"])
    if edge["on"]:
        text = f"on: {edge['on']}"
        if edge["criteria"]:
            text += f"{MERMAID_LINE_BREAK}{_esc(edge['criteria'], 48)}"
        return f'  {source_id} -.->|"{_esc(text, 64)}"| {target_id}'
    if label:
        return f"  {source_id} {arrow}|{label}| {target_id}"
    return f"  {source_id} {arrow} {target_id}"


# ─── 뷰 빌더 ────────────────────────────────────────────────────────────────


def _scope_edges(edges: list[dict], members: set[URIRef]) -> list[dict]:
    return [e for e in edges if e["from"] in members or e["to"] in members]


def _collect_nodes(edges: list[dict], members: set[URIRef]) -> list[URIRef]:
    nodes: set[URIRef] = set(members)
    for edge in edges:
        nodes.add(edge["from"])
        nodes.add(edge["to"])
    return sorted(nodes, key=str)


def _is_artifact(g: Graph, node: URIRef) -> bool:
    return (node, RDF.type, WF.Artifact) in g


def _exclude_artifacts(g: Graph, nodes: list[URIRef]) -> list[URIRef]:
    return [node for node in nodes if not _is_artifact(g, node)]


def _exclude_artifact_edges(g: Graph, edges: list[dict]) -> list[dict]:
    return [edge for edge in edges if not _is_artifact(g, edge["from"]) and not _is_artifact(g, edge["to"])]


def _artifact_index(g: Graph, nodes: list[URIRef]) -> str:
    rows = []
    for node in nodes:
        if (node, RDF.type, WF.Artifact) not in g:
            continue
        artifact_type = _text(g.value(node, WF.artifactType)) or "unspecified"
        locator = _text(g.value(node, WF.locator)) or "-"
        prov_bits = []
        for prop, key in ((WF.author, "author"), (WF.version, "v"), (WF.confidence, "conf"),
                          (WF.validation, "validated"), (WF.coverage, "cov")):
            value = _text(g.value(node, prop))
            if value:
                prov_bits.append(f"{key}: {_esc(value, 24)}")
        provenance = " · ".join(prov_bits) if prov_bits else "—"
        rows.append(f"| `{_local(node)}` | {artifact_type} | `{locator}` | {provenance} |")
    if not rows:
        return ""
    return "\n".join([
        "",
        "## Artifact Node Index",
        "",
        "| id | artifact_type (명시 선언) | locator | provenance (§6) |",
        "|---|---|---|---|",
        *rows,
        "",
        "> `artifact_type`은 TTL `wf:artifactType` 명시값만 표시한다 (v0.7 native — 추론 없음).",
        "> provenance는 선언값만 표시 — `—` 는 §6 미기록 (validate_abox 커버리지 경고 대상).",
    ])


def _executor_links(g: Graph, nodes: list[URIRef]) -> list[str]:
    """hasSubject=workflow 인 위임 Execution의 realizedBy(Skill=sub-workflow) 링크."""
    lines = []
    for node in nodes:
        if (node, RDF.type, WF.Execution) not in g:
            continue
        for workflow in g.objects(node, WF.realizedBy):
            if isinstance(workflow, URIRef):
                lines.append(f"  {_mermaid_id(node)} -.->|realizedBy| {_mermaid_id(workflow)}")
    return lines


def build_view(g: Graph, workflow: URIRef, scope: str, view: str) -> str:
    """view ∈ {execution-rail, artifact-stream, repository}."""
    if view == "workflow":
        view = "execution-rail"
    members = _members(g, workflow)
    rail_edges = _scope_edges(rails(g), members) if view != "artifact-stream" else []
    if view == "execution-rail":
        rail_edges = _exclude_artifact_edges(g, rail_edges)
    stream_edges: list[dict] = []
    if view in {"artifact-stream", "repository"}:
        # WorkflowGraph closure (D-16): member Execution이 소비/생산하는 Artifact도
        # scope에 포함한다 — artifact↔artifact edge(evidence_of, 파생 * 포함)가
        # 그 closure 안에서 렌더된다.
        all_streams = streams(g)
        closure = set(members)
        for edge in all_streams:
            if edge["from"] in members or edge["to"] in members:
                closure.add(edge["from"])
                closure.add(edge["to"])
        stream_edges = _scope_edges(all_streams, closure)
    edges = rail_edges + stream_edges
    nodes = _collect_nodes(edges, members if view != "artifact-stream" else set())
    if view == "artifact-stream":
        # 공급망 관점: stream 연결 노드만
        nodes = _collect_nodes(stream_edges, set())
    elif view == "execution-rail":
        # control plane 관점: wf:Rail에 등장하는 실행 노드만.
        # wf:has 멤버로 선언된 artifact는 repository/artifact-stream 뷰에서만 보인다.
        nodes = _exclude_artifacts(g, _collect_nodes(rail_edges, set()))

    label = _label(g, workflow)
    workflow_type = _text(g.value(workflow, WF.workflowType))
    header = {
        "execution-rail": "Execution Rail (Control Plane — wf:Rail)",
        "artifact-stream": "Artifact Stream Graph (Data Plane — wf:Stream)",
        "repository": "Repository Graph = Execution Rail + Artifact Stream Graph",
    }[view]

    lines = [
        f"> {header} · scope `{scope}` · workflowType `{workflow_type or '-'}` · **v0.7 native** (Rail/Stream 직접 순회)",
        "",
        "```mermaid",
        "flowchart LR",
        *CLASS_DEFS,
    ]
    seen_ids: set[str] = set()
    body: list[str] = []
    for node in nodes:
        node_id = _mermaid_id(node)
        if node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        decl, _cls = _node_decl(g, node)
        body.append(decl)
    for edge in rail_edges:
        body.append(_edge_line(edge, RAIL_EDGE_STYLE))
    for edge in stream_edges:
        body.append(_edge_line(edge, STREAM_EDGE_STYLE))
    body.extend(_executor_links(g, nodes))
    if not body:
        body.append('  empty["(no nodes)"]')
    lines.extend(body)
    lines.append("```")
    if view != "execution-rail":
        lines.append(_artifact_index(g, nodes))
    lines.append("")
    lines.append(f"- workflow: `{label}` (`{_local(workflow)}`)")
    lines.append(f"- rail edges: {len(rail_edges)} · stream edges: {len(stream_edges)}")
    return "\n".join(line for line in lines if line is not None)
