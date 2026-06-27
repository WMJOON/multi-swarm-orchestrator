#!/usr/bin/env python3
"""Compile MSO workflow TTL ABox into a LangGraph execution artifact.

The TTL ABox remains the source of truth. Generated graph.py is an adapter
artifact that can be regenerated from TTL + policy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import textwrap
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from pprint import pformat
from typing import Any

from rdflib import Graph, Namespace, RDF, URIRef

WF = Namespace("https://mso.dev/ontology/workflow#")

DEFAULT_POLICY: dict[str, Any] = {
    "mode": "cost",
    "providers": {
        "default": "local-ollama",
        "phase": "python",
        "step": "local-ollama",
        "validation": "python",
        "decision": {
            "HITL": "human",
            "HITLFE": "codex-chatgpt",
            "HOTL": "local-ollama",
            "HOOTL": "local-ollama",
        },
    },
    "context": {
        "enabled": True,
        "mode": "snapshot",
        "top_k": 5,
        "relation_depth": 1,
        "max_entry_chars": 1200,
        "include_types": [
            "principle",
            "pattern",
            "episode",
            "user-decision",
            "agent-decision",
            "alternatives-record",
            "issue-note",
            "trouble-shooting",
        ],
    },
    "writeback": {
        "enabled": True,
        "mode": "queue-only",
        "allowed_types": [
            "issue-note",
            "agent-decision",
            "alternatives-record",
            "trouble-shooting",
        ],
        "requires_review": True,
    },
    "planes": {
        "control_plane_agents": ["claude-code", "codex"],
        "execution_plane": "langgraph",
    },
    "governance": {
        "user_decision": {
            "execution_plane": "forbidden",
            "control_plane": "record-after-human-or-metric-oracle",
        },
        "alternatives_record": {
            "execution_plane": "queue-or-interrupt",
            "control_plane": "present-to-user-or-metric-oracle",
        },
        "control_plane_events": {
            "enabled": True,
            "halt_on": ["request_user_decision", "propose_alternatives"],
        },
    },
}

MODE_PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "cost": DEFAULT_POLICY["providers"],
    "privacy": {
        "default": "local-ollama",
        "phase": "python",
        "step": "local-ollama",
        "validation": "python",
        "decision": {
            "HITL": "human",
            "HITLFE": "local-ollama",
            "HOTL": "local-ollama",
            "HOOTL": "local-ollama",
        },
    },
    "speed": {
        "default": "openai-api",
        "phase": "python",
        "step": "openai-api",
        "validation": "python",
        "decision": {
            "HITL": "human",
            "HITLFE": "codex-chatgpt",
            "HOTL": "openai-api",
            "HOOTL": "openai-api",
        },
    },
    "quality": {
        "default": "openai-api",
        "phase": "python",
        "step": "openai-api",
        "validation": "python",
        "decision": {
            "HITL": "human",
            "HITLFE": "codex-chatgpt",
            "HOTL": "openai-api",
            "HOOTL": "openai-api",
        },
    },
}


@dataclass
class Node:
    id: str
    uri: str
    type: str
    label: str
    status: str | None = None
    instruction: str | None = None
    judge: str | None = None
    harness: str | None = None
    pass_criteria: list[str] = field(default_factory=list)
    provider: str = "local-ollama"
    phase_id: str | None = None
    branches: list[dict[str, str]] = field(default_factory=list)
    context_selector: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryEntry:
    id: str
    type: str
    title: str
    text: str
    tags: list[str]
    created_at: str | None
    source_path: str
    relations: list[dict[str, str]]
    metadata: dict[str, Any]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("_") or "workflow"


def _local_id(uri: URIRef | str) -> str:
    text = str(uri)
    if "#" in text:
        text = text.rsplit("#", 1)[1]
    if "/" in text:
        text = text.rsplit("/", 1)[1]
    return _safe_id(text)


def _literal(g: Graph, subj: URIRef, pred: URIRef) -> str | None:
    value = next(g.objects(subj, pred), None)
    return str(value) if value is not None else None


def _literals(g: Graph, subj: URIRef, pred: URIRef) -> list[str]:
    return [str(v) for v in g.objects(subj, pred)]


def _load_policy(path: Path | None, mode_override: str | None) -> dict[str, Any]:
    policy = json.loads(json.dumps(DEFAULT_POLICY))
    if path:
        text = _read_text(path)
        if path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except ImportError as exc:  # pragma: no cover - env dependent
                raise SystemExit("YAML policy requires PyYAML. Use JSON or install pyyaml.") from exc
            loaded = yaml.safe_load(text) or {}
        else:
            loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise SystemExit("policy must be a mapping")
        policy.update({k: v for k, v in loaded.items() if k not in {"providers", "context", "writeback", "planes", "governance"}})
        providers = json.loads(json.dumps(MODE_PROVIDER_DEFAULTS.get(policy.get("mode", "cost"), DEFAULT_POLICY["providers"])))
        providers.update(loaded.get("providers") or {})
        if isinstance(providers.get("decision"), dict) and isinstance((loaded.get("providers") or {}).get("decision"), dict):
            merged_decision = json.loads(json.dumps(MODE_PROVIDER_DEFAULTS.get(policy.get("mode", "cost"), DEFAULT_POLICY["providers"]).get("decision", {})))
            merged_decision.update((loaded.get("providers") or {}).get("decision") or {})
            providers["decision"] = merged_decision
        policy["providers"] = providers
        for section in ("context", "writeback", "planes"):
            merged = json.loads(json.dumps(DEFAULT_POLICY.get(section, {})))
            merged.update(loaded.get(section) or {})
            policy[section] = merged
        governance = json.loads(json.dumps(DEFAULT_POLICY["governance"]))
        for key, value in (loaded.get("governance") or {}).items():
            if isinstance(value, dict) and isinstance(governance.get(key), dict):
                governance[key].update(value)
            else:
                governance[key] = value
        policy["governance"] = governance
    if mode_override:
        policy["mode"] = mode_override
        policy["providers"] = json.loads(json.dumps(MODE_PROVIDER_DEFAULTS.get(mode_override, DEFAULT_POLICY["providers"])))
    return policy


def _provider_for(node_type: str, judge: str | None, policy: dict[str, Any]) -> str:
    providers = policy.get("providers") or {}
    if node_type == "decision":
        decision = providers.get("decision") or {}
        return str(decision.get(judge or "", providers.get("default", "local-ollama")))
    return str(providers.get(node_type, providers.get("default", "local-ollama")))


def _subjects_by_type(g: Graph, cls: URIRef) -> list[URIRef]:
    return sorted((s for s in g.subjects(RDF.type, cls) if isinstance(s, URIRef)), key=str)


def _entry_from_obj(obj: dict[str, Any], source_path: Path) -> MemoryEntry | None:
    if not isinstance(obj, dict) or not obj.get("id") or not obj.get("type"):
        return None
    return MemoryEntry(
        id=str(obj.get("id")),
        type=str(obj.get("type")),
        title=str(obj.get("title") or ""),
        text=str(obj.get("text") or ""),
        tags=[str(t) for t in (obj.get("tags") or [])],
        created_at=str(obj.get("created_at")) if obj.get("created_at") else None,
        source_path=str(obj.get("source_path") or source_path),
        relations=[
            {"type": str(rel.get("type")), "target": str(rel.get("target"))}
            for rel in (obj.get("relations") or [])
            if isinstance(rel, dict) and rel.get("type") and rel.get("target")
        ],
        metadata=obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {},
    )


def load_work_memory(workmem_dir: Path | None) -> list[MemoryEntry]:
    if not workmem_dir or not workmem_dir.exists():
        return []
    entries: list[MemoryEntry] = []
    for path in sorted(workmem_dir.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry = _entry_from_obj(obj, path)
            if entry:
                entries.append(entry)
    return entries


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[A-Za-z0-9_.-]{3,}", text or "")}


def _context_selector(node: Node, policy: dict[str, Any]) -> dict[str, Any]:
    context = policy.get("context") or {}
    query = " ".join(
        part for part in [
            node.id,
            node.type,
            node.phase_id or "",
            node.label,
            node.instruction or "",
            node.judge or "",
            node.harness or "",
        ]
        if part
    )
    tags = [node.id, node.type]
    if node.phase_id:
        tags.append(node.phase_id)
    if node.judge:
        tags.append(node.judge)
    if node.harness:
        tags.append(node.harness)
    return {
        "query": query,
        "tags": sorted(set(tags)),
        "include_types": list(context.get("include_types") or []),
        "top_k": int(context.get("top_k", 5)),
        "relation_depth": int(context.get("relation_depth", 1)),
        "max_entry_chars": int(context.get("max_entry_chars", 1200)),
    }


_TYPE_PRIORITIES = {
    "principle": 30,
    "pattern": 26,
    "user-decision": 24,
    "episode": 20,
    "trouble-shooting": 16,
    "issue-note": 14,
    "agent-decision": 12,
    "alternatives-record": 12,
}


def _entry_score(entry: MemoryEntry, selector: dict[str, Any]) -> int:
    allowed = set(selector.get("include_types") or [])
    if allowed and entry.type not in allowed:
        return -1
    score = _TYPE_PRIORITIES.get(entry.type, 0)
    selector_tags = {str(t).lower() for t in selector.get("tags") or []}
    entry_tags = {str(t).lower() for t in entry.tags}
    score += 18 * len(selector_tags & entry_tags)
    haystack = _tokenize(" ".join([entry.id, entry.type, entry.title, entry.text, " ".join(entry.tags)]))
    score += len(_tokenize(selector.get("query", "")) & haystack)
    if entry.metadata.get("module") and str(entry.metadata["module"]).lower() in selector_tags:
        score += 12
    return score


def _expand_related(selected: list[MemoryEntry], all_entries: list[MemoryEntry], depth: int) -> list[MemoryEntry]:
    if depth <= 0:
        return selected
    by_id = {entry.id: entry for entry in all_entries}
    incoming: dict[str, list[MemoryEntry]] = defaultdict(list)
    for entry in all_entries:
        for rel in entry.relations:
            incoming[rel["target"]].append(entry)
    result: dict[str, MemoryEntry] = {entry.id: entry for entry in selected}
    frontier = list(selected)
    for _ in range(depth):
        next_frontier: list[MemoryEntry] = []
        for entry in frontier:
            neighbors = [by_id[rel["target"]] for rel in entry.relations if rel["target"] in by_id]
            neighbors.extend(incoming.get(entry.id, []))
            for neighbor in neighbors:
                if neighbor.id not in result:
                    result[neighbor.id] = neighbor
                    next_frontier.append(neighbor)
        frontier = next_frontier
        if not frontier:
            break
    return list(result.values())


def build_context_pack(node: Node, entries: list[MemoryEntry], selector: dict[str, Any]) -> dict[str, Any]:
    scored = [
        (score, entry)
        for entry in entries
        if (score := _entry_score(entry, selector)) >= 0
    ]
    scored.sort(key=lambda item: (-item[0], item[1].created_at or "", item[1].id))
    top = [entry for _, entry in scored[: int(selector.get("top_k", 5))]]
    selected = _expand_related(top, entries, int(selector.get("relation_depth", 1)))
    scores = {entry.id: score for score, entry in scored}
    max_chars = int(selector.get("max_entry_chars", 1200))
    return {
        "node_id": node.id,
        "selector": selector,
        "entries": [
            {
                "id": entry.id,
                "type": entry.type,
                "title": entry.title,
                "text": entry.text[:max_chars],
                "tags": entry.tags,
                "metadata": entry.metadata,
                "relations": entry.relations,
                "source_path": entry.source_path,
                "score": scores.get(entry.id, 0),
            }
            for entry in selected
        ],
    }


def _context_index_hash(entries: list[MemoryEntry]) -> str:
    payload = [
        {
            "id": entry.id,
            "type": entry.type,
            "title": entry.title,
            "text": entry.text,
            "tags": entry.tags,
            "created_at": entry.created_at,
            "relations": entry.relations,
            "metadata": entry.metadata,
        }
        for entry in sorted(entries, key=lambda e: e.id)
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def parse_ttl(ttl_path: Path, policy: dict[str, Any], workmem_dir: Path | None = None) -> dict[str, Any]:
    g = Graph()
    g.parse(ttl_path, format="turtle")

    project = next(g.subjects(RDF.type, WF.Project), None)
    workflow_id = _safe_id(_literal(g, project, WF.label) if isinstance(project, URIRef) else ttl_path.stem)
    if workflow_id == "workflow":
        workflow_id = _safe_id(ttl_path.stem.replace(".abox", ""))

    nodes: dict[str, Node] = {}
    phase_nodes: dict[str, list[str]] = defaultdict(list)
    warnings: list[str] = []

    for phase in _subjects_by_type(g, WF.Phase):
        node_id = _local_id(phase)
        nodes[node_id] = Node(
            id=node_id,
            uri=str(phase),
            type="phase",
            label=_literal(g, phase, WF.label) or node_id,
            status=_literal(g, phase, WF.status),
            provider=_provider_for("phase", None, policy),
        )
        for node in g.objects(phase, WF.hasNode):
            if isinstance(node, URIRef):
                phase_nodes[node_id].append(_local_id(node))

    type_map = {
        WF.Step: "step",
        WF.Decision: "decision",
        WF.Validation: "validation",
        WF.Group: "group",
    }
    for cls, node_type in type_map.items():
        for subj in _subjects_by_type(g, cls):
            node_id = _local_id(subj)
            judge = _literal(g, subj, WF.judge)
            nodes[node_id] = Node(
                id=node_id,
                uri=str(subj),
                type=node_type,
                label=_literal(g, subj, WF.label) or node_id,
                status=_literal(g, subj, WF.status),
                instruction=_literal(g, subj, WF.instruction),
                judge=judge,
                harness=_literal(g, subj, WF.harness),
                pass_criteria=_literals(g, subj, WF.passCriteria),
                provider=_provider_for(node_type, judge, policy),
            )
            for branch in g.objects(subj, WF.hasBranch):
                if not isinstance(branch, URIRef):
                    continue
                on_value = _literal(g, branch, WF.on)
                goto = _literal(g, branch, WF.goto)
                label = _literal(g, branch, WF.label)
                if on_value:
                    nodes[node_id].branches.append({
                        "on": on_value,
                        "goto": _safe_id(goto or ""),
                        "label": label or on_value,
                    })

    for phase_id, child_ids in phase_nodes.items():
        for child_id in child_ids:
            if child_id in nodes:
                nodes[child_id].phase_id = phase_id

    for node in nodes.values():
        node.context_selector = _context_selector(node, policy)

    edges: list[dict[str, str]] = []
    for subj, _, obj in g.triples((None, WF.dependsOn, None)):
        if isinstance(subj, URIRef) and isinstance(obj, URIRef):
            source = _local_id(obj)
            target = _local_id(subj)
            if source in nodes and target in nodes:
                edges.append({"source": source, "target": target, "kind": "depends_on"})

    for phase_id, child_ids in phase_nodes.items():
        children = [cid for cid in sorted(child_ids) if cid in nodes]
        if not children:
            continue
        edges.append({"source": phase_id, "target": children[0], "kind": "phase_entry"})
        warnings.append(f"{phase_id}: node order is lexical because RDF has no sequence container")
        for source, target in zip(children, children[1:]):
            if nodes[source].branches:
                continue
            edges.append({"source": source, "target": target, "kind": "lexical_next"})

    for node in nodes.values():
        for branch in node.branches:
            target = branch.get("goto")
            if target and target in nodes:
                edges.append({
                    "source": node.id,
                    "target": target,
                    "kind": "branch",
                    "on": branch["on"],
                    "label": branch["label"],
                })
            elif target:
                warnings.append(f"{node.id}: branch target not found: {target}")

    incoming = {edge["target"] for edge in edges}
    entrypoints = sorted(node_id for node_id, node in nodes.items() if node_id not in incoming and node.type == "phase")
    if not entrypoints:
        entrypoints = sorted(node_id for node_id in nodes if node_id not in incoming)

    memory_entries = load_work_memory(workmem_dir)
    context_enabled = bool((policy.get("context") or {}).get("enabled", True))
    context_packs = {
        node.id: build_context_pack(node, memory_entries, node.context_selector)
        for node in nodes.values()
        if context_enabled and memory_entries
    }

    return {
        "workflow_id": workflow_id,
        "source_ttl": str(ttl_path),
        "source_sha256": _sha256(ttl_path),
        "workmem_dir": str(workmem_dir) if workmem_dir else None,
        "workmem_entry_count": len(memory_entries),
        "workmem_sha256": _context_index_hash(memory_entries) if memory_entries else None,
        "mode": policy.get("mode", "cost"),
        "nodes": [node.__dict__ for node in sorted(nodes.values(), key=lambda n: n.id)],
        "edges": sorted(edges, key=lambda e: (e["source"], e["target"], e["kind"], e.get("on", ""))),
        "entrypoints": entrypoints,
        "context_packs": context_packs,
        "writeback_policy": policy.get("writeback") or {},
        "warnings": warnings,
    }


def _topological_order(ir: dict[str, Any]) -> list[str]:
    nodes = [n["id"] for n in ir["nodes"]]
    graph: dict[str, set[str]] = {n: set() for n in nodes}
    indeg: dict[str, int] = {n: 0 for n in nodes}
    for edge in ir["edges"]:
        source, target = edge["source"], edge["target"]
        if source not in graph or target not in graph or target in graph[source]:
            continue
        graph[source].add(target)
        indeg[target] += 1
    queue = deque(sorted(n for n, degree in indeg.items() if degree == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for target in sorted(graph[node]):
            indeg[target] -= 1
            if indeg[target] == 0:
                queue.append(target)
    return order if len(order) == len(nodes) else sorted(nodes)


def render_graph_py(ir: dict[str, Any], policy: dict[str, Any]) -> str:
    node_order = _topological_order(ir)
    node_specs = {node["id"]: node for node in ir["nodes"]}
    fixed_edges = [
        edge for edge in ir["edges"]
        if edge["kind"] != "branch" and edge["source"] in node_specs and edge["target"] in node_specs
    ]
    branch_edges = [edge for edge in ir["edges"] if edge["kind"] == "branch"]
    outgoing = defaultdict(list)
    for edge in ir["edges"]:
        outgoing[edge["source"]].append(edge)
    terminal_nodes = sorted(node_id for node_id in node_specs if not outgoing[node_id])

    payload = {
        "workflow_id": ir["workflow_id"],
        "mode": ir["mode"],
        "node_order": node_order,
        "node_specs": node_specs,
        "context_packs": ir.get("context_packs", {}),
        "entrypoints": ir["entrypoints"],
        "fixed_edges": fixed_edges,
        "branch_edges": branch_edges,
        "terminal_nodes": terminal_nodes,
        "writeback_policy": ir.get("writeback_policy", {}),
        "governance": policy.get("governance", {}),
        "planes": policy.get("planes", {}),
        "policy": policy,
    }
    payload_py = pformat(payload, width=100, sort_dicts=False).replace("\n", "\n    ")

    return textwrap.dedent(f'''\
    #!/usr/bin/env python3
    """Generated LangGraph adapter for MSO workflow {ir["workflow_id"]}.

    Generated from TTL ABox. Do not edit by hand; regenerate with
    mso-workflow-optimizer/scripts/compile_workflow.py.
    """

    from __future__ import annotations

    from copy import deepcopy
    from typing import Any

    PAYLOAD = {payload_py}

    try:
        from langgraph.graph import END, START, StateGraph
        LANGGRAPH_AVAILABLE = True
    except Exception:  # pragma: no cover - depends on optional runtime
        END = "__end__"
        START = "__start__"
        StateGraph = None
        LANGGRAPH_AVAILABLE = False


    def node_specs() -> dict[str, dict[str, Any]]:
        return deepcopy(PAYLOAD["node_specs"])


    def _run_node(state: dict[str, Any], node_id: str) -> dict[str, Any]:
        state = dict(state or {{}})
        if state.get("halted"):
            return state
        spec = PAYLOAD["node_specs"][node_id]
        context_pack = (
            (state.get("context_overrides", {{}}) or {{}}).get(node_id)
            or PAYLOAD.get("context_packs", {{}}).get(node_id)
            or {{"node_id": node_id, "entries": [], "selector": spec.get("context_selector", {{}})}}
        )
        state.setdefault("active_context", {{}})[node_id] = context_pack
        trace = list(state.get("trace", []))
        trace.append({{
            "node_id": node_id,
            "type": spec["type"],
            "label": spec["label"],
            "provider": spec["provider"],
            "judge": spec.get("judge"),
            "harness": spec.get("harness"),
            "context_entry_ids": [entry.get("id") for entry in context_pack.get("entries", [])],
        }})
        state["trace"] = trace
        state["last_node"] = node_id
        state.setdefault("node_outputs", {{}})[node_id] = {{
            "status": "planned",
            "provider": spec["provider"],
            "instruction": spec.get("instruction"),
            "context_entry_ids": [entry.get("id") for entry in context_pack.get("entries", [])],
        }}
        node_result = (state.get("node_results", {{}}) or {{}}).get(node_id) or {{}}
        control_event = node_result.get("control_plane_event")
        if control_event:
            event = dict(control_event)
            event.update({{
                "node_id": node_id,
                "status": "pending-control-plane",
                "execution_plane": PAYLOAD.get("planes", {{}}).get("execution_plane", "langgraph"),
                "control_plane_agents": PAYLOAD.get("planes", {{}}).get("control_plane_agents", []),
            }})
            state.setdefault("control_plane_events", []).append(event)
            governance = PAYLOAD.get("governance", {{}}).get("control_plane_events", {{}})
            halt_on = set(governance.get("halt_on", []))
            action = event.get("action") or event.get("type")
            if action in halt_on:
                state["halted"] = True
                state["halt_reason"] = action
        writeback = node_result.get("memory_writeback")
        if writeback:
            policy = PAYLOAD.get("writeback_policy", {{}})
            allowed = set(policy.get("allowed_types", []))
            item_type = writeback.get("type")
            queue_item = dict(writeback)
            queue_item.update({{
                "node_id": node_id,
                "status": "proposed",
                "requires_review": bool(policy.get("requires_review", True)),
            }})
            if allowed and item_type not in allowed:
                queue_item["status"] = "rejected"
                queue_item["reason"] = "type not allowed by writeback policy"
            if item_type == "user-decision":
                queue_item["status"] = "rejected"
                queue_item["reason"] = "execution plane cannot record user-decision directly"
            state.setdefault("memory_writeback_queue", []).append(queue_item)
        return state


    def _route_decision(state: dict[str, Any], node_id: str) -> str:
        decisions = (state or {{}}).get("decisions", {{}})
        selected = decisions.get(node_id)
        branches = [edge for edge in PAYLOAD["branch_edges"] if edge["source"] == node_id]
        allowed = {{edge["on"] for edge in branches}}
        if selected in allowed:
            return selected
        return branches[0]["on"] if branches else "__end__"


    class FallbackGraph:
        def invoke(self, initial_state: dict[str, Any] | None = None) -> dict[str, Any]:
            state = dict(initial_state or {{}})
            for node_id in PAYLOAD["node_order"]:
                state = _run_node(state, node_id)
                if state.get("halted"):
                    break
            state["langgraph_available"] = False
            return state


    def build_graph():
        if not LANGGRAPH_AVAILABLE:
            return FallbackGraph()

        graph = StateGraph(dict)
        for node_id in PAYLOAD["node_order"]:
            graph.add_node(node_id, lambda state, node_id=node_id: _run_node(state, node_id))

        for entry in PAYLOAD["entrypoints"]:
            graph.add_edge(START, entry)

        branch_sources = {{edge["source"] for edge in PAYLOAD["branch_edges"]}}
        for edge in PAYLOAD["fixed_edges"]:
            if edge["source"] in branch_sources:
                continue
            graph.add_edge(edge["source"], edge["target"])

        for node_id in sorted(branch_sources):
            mapping = {{
                edge["on"]: edge["target"]
                for edge in PAYLOAD["branch_edges"]
                if edge["source"] == node_id
            }}
            if mapping:
                graph.add_conditional_edges(
                    node_id,
                    lambda state, node_id=node_id: _route_decision(state, node_id),
                    mapping,
                )

        for node_id in PAYLOAD["terminal_nodes"]:
            graph.add_edge(node_id, END)

        return graph.compile()


    def invoke(initial_state: dict[str, Any] | None = None) -> dict[str, Any]:
        return build_graph().invoke(initial_state or {{}})
    ''')


def compile_workflow(
    ttl_path: Path,
    out_root: Path,
    policy_path: Path | None,
    mode: str | None,
    workmem_dir: Path | None = None,
) -> Path:
    policy = _load_policy(policy_path, mode)
    ir = parse_ttl(ttl_path, policy, workmem_dir=workmem_dir)
    artifact_dir = out_root / _safe_id(ir["workflow_id"])
    artifact_dir.mkdir(parents=True, exist_ok=True)

    (artifact_dir / "workflow_ir.json").write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (artifact_dir / "optimizer_policy.json").write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (artifact_dir / "graph.py").write_text(render_graph_py(ir, policy), encoding="utf-8")
    manifest = {
        "name": ir["workflow_id"],
        "source_ttl": ir["source_ttl"],
        "source_sha256": ir["source_sha256"],
        "workmem_dir": ir.get("workmem_dir"),
        "workmem_sha256": ir.get("workmem_sha256"),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "artifacts": ["graph.py", "workflow_ir.json", "optimizer_policy.json"],
        "warnings": ir["warnings"],
    }
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile MSO workflow TTL ABox to LangGraph artifacts.")
    parser.add_argument("ttl", type=Path, help="workflow *.abox.ttl file")
    parser.add_argument("--out", type=Path, default=Path("generated/langgraph"), help="output root directory")
    parser.add_argument("--policy", type=Path, help="optimizer policy YAML/JSON")
    parser.add_argument("--mode", choices=sorted(MODE_PROVIDER_DEFAULTS), help="override policy mode")
    parser.add_argument("--workmem", type=Path, help="agent-context/work-memory directory for ContextPack snapshot")
    parser.add_argument("--print-ir", action="store_true", help="print workflow_ir.json after compiling")
    args = parser.parse_args(argv)

    artifact_dir = compile_workflow(args.ttl, args.out, args.policy, args.mode, workmem_dir=args.workmem)
    if args.print_ir:
        print((artifact_dir / "workflow_ir.json").read_text(encoding="utf-8"))
    else:
        print(artifact_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
