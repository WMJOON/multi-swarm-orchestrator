#!/usr/bin/env python3
"""Compile MSO workflow TTL ABox into a LangGraph execution artifact.

The TTL ABox remains the source of truth. Generated graph.py is an adapter
artifact that can be regenerated from TTL + policy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
import sys
import textwrap
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from pprint import pformat
from typing import Any

try:
    from rdflib import Graph, Namespace, RDF, URIRef
except ImportError as exc:  # pragma: no cover - env dependent
    raise SystemExit("[ERROR] rdflib is required: pip install -r requirements.txt (see requirements.txt at the MSO repo root)") from exc

WF = Namespace("https://mso.dev/ontology/workflow#")

# ContextPack 스코어링/선택 정본은 mso-work-memory 의 wm_context.py.
# sibling 우선 — ~/.claude/skills 는 승격본(repository/) 심링크라 repository-test
# 개발 중 stale 코드를 읽게 되므로 co-located 소스를 먼저 찾는다.
_WM_CONTEXT_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent / "mso-work-memory" / "scripts" / "wm_context.py",
    Path.home() / ".claude" / "skills" / "mso-work-memory" / "scripts" / "wm_context.py",
]
_wm_context_module: Any = None


def _load_wm_context() -> Any:
    global _wm_context_module
    if _wm_context_module is None:
        for cand in _WM_CONTEXT_CANDIDATES:
            if cand.exists():
                spec = importlib.util.spec_from_file_location("wm_context", cand)
                assert spec and spec.loader
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                _wm_context_module = module
                break
        else:
            raise SystemExit(
                "[ERROR] wm_context.py not found — install the mso-work-memory skill "
                "(sibling skills/ dir or ~/.claude/skills/)."
            )
    return _wm_context_module


# v0.7 어휘·제어 흐름 추출의 정본은 mso-workflow-design 의 wf_v07.py (control_graph). sibling 우선, ~/.claude/skills fallback.
_WF_V07_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent / "mso-workflow-design" / "scripts" / "wf_v07.py",
    Path.home() / ".claude" / "skills" / "mso-workflow-design" / "scripts" / "wf_v07.py",
]
_wf_v07_module: Any = None


def _load_wf_v07() -> Any:
    global _wf_v07_module
    if _wf_v07_module is None:
        for cand in _WF_V07_CANDIDATES:
            if cand.exists():
                spec = importlib.util.spec_from_file_location("wf_v07", cand)
                assert spec and spec.loader
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if not hasattr(module, "control_graph"):
                    raise SystemExit(f"[ERROR] {cand} has no control_graph — update the mso-workflow-design skill (>=0.13.0).")
                _wf_v07_module = module
                break
        else:
            raise SystemExit(
                "[ERROR] wf_v07.py not found — install the mso-workflow-design skill "
                "(sibling skills/ dir or ~/.claude/skills/)."
            )
    return _wf_v07_module

# 로컬 AI 서빙 엔진 레지스트리. 모두 OpenAI 호환 API(/v1)를 노출한다. base_url 은 policy 의 engines 로 덮어쓴다.
DEFAULT_ENGINES: dict[str, dict[str, str]] = {
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "api": "openai-compatible"},
    "vllm": {"base_url": "http://127.0.0.1:8000/v1", "api": "openai-compatible"},
    "sglang": {"base_url": "http://127.0.0.1:30000/v1", "api": "openai-compatible"},
    "lmstudio": {"base_url": "http://127.0.0.1:1234/v1", "api": "openai-compatible"},
    "omlx": {"base_url": "http://127.0.0.1:8000/v1", "api": "openai-compatible"},
}

DEFAULT_POLICY: dict[str, Any] = {
    "mode": "cost",
    # 루프(되돌림 rail) 무한 반복 방지: 한 노드가 이 횟수보다 많이 실행되면 halt
    "loop_limit": 5,
    # 일반 'local' 슬롯(기본 provider local-ollama)이 가리킬 서빙 엔진: ollama|vllm|sglang|lmstudio|omlx
    "local_engine": "ollama",
    "engines": DEFAULT_ENGINES,
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
        # v0.6.0 oracle graph (SPEC §5): execution plane 은 evolves 를 *제안*만 하고
        # (AR 처럼), workflow 를 실제로 바꾸는 evolve 확정은 control plane oracle 권위다.
        # oracle graph 의 stratification(C∩W=∅)은 design-time SHACL 이 보장하고,
        # 여기서는 run-time 에 evolve 행위를 control plane 으로 gate 한다.
        "evolves": {
            "execution_plane": "propose-only",
            "control_plane": "confirm-after-human-or-metric-oracle",
        },
        "control_plane_events": {
            "enabled": True,
            "halt_on": ["request_user_decision", "propose_alternatives", "propose_evolution"],
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
    subject: str | None = None  # v0.7 wf:hasSubject (human|system|model|self)
    requires_human: bool = False  # True 면 사람 결정/결과 없이는 execution plane 이 halt


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
        policy.update({k: v for k, v in loaded.items() if k not in {"providers", "context", "writeback", "planes", "governance", "engines"}})
        engines = json.loads(json.dumps(DEFAULT_ENGINES))
        for name, cfg in (loaded.get("engines") or {}).items():
            engines.setdefault(name, {}).update(cfg or {})
        policy["engines"] = engines
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
    engine = str(policy.get("local_engine") or "ollama")
    if engine not in (policy.get("engines") or {}):
        raise SystemExit(f"unknown local_engine {engine!r}; choose one of {sorted(policy.get('engines') or {})}")
    if mode_override:
        policy["mode"] = mode_override
        policy["providers"] = json.loads(json.dumps(MODE_PROVIDER_DEFAULTS.get(mode_override, DEFAULT_POLICY["providers"])))
    return policy


def _localize(provider: str, policy: dict[str, Any]) -> str:
    """일반 local 슬롯(local-ollama)을 policy.local_engine 이 지정한 서빙 엔진으로 바꾼다."""
    engine = str(policy.get("local_engine") or "ollama")
    if provider == "local-ollama" and engine != "ollama":
        return f"local-{engine}"
    return provider


def _provider_for(node_type: str, judge: str | None, policy: dict[str, Any]) -> str:
    providers = policy.get("providers") or {}
    if node_type == "decision":
        decision = providers.get("decision") or {}
        return _localize(str(decision.get(judge or "", providers.get("default", "local-ollama"))), policy)
    return _localize(str(providers.get(node_type, providers.get("default", "local-ollama"))), policy)


def _subjects_by_type(g: Graph, cls: URIRef) -> list[URIRef]:
    return sorted((s for s in g.subjects(RDF.type, cls) if isinstance(s, URIRef)), key=str)


def load_work_memory(workmem_dir: Path | None) -> list[dict[str, Any]]:
    if not workmem_dir or not workmem_dir.exists():
        return []
    return _load_wm_context().load_entries(workmem_dir)


def _context_selector(node: Node, policy: dict[str, Any]) -> dict[str, Any]:
    context = policy.get("context") or {}
    return _load_wm_context().selector_from_node_fields(
        node.id,
        node_type=node.type,
        phase_id=node.phase_id,
        label=node.label,
        instruction=node.instruction,
        judge=node.judge,
        harness=node.harness,
        include_types=list(context.get("include_types") or []),
        top_k=int(context.get("top_k", 5)),
        relation_depth=int(context.get("relation_depth", 1)),
        max_entry_chars=int(context.get("max_entry_chars", 1200)),
    )


def _context_index_hash(entries: list[dict[str, Any]]) -> str:
    payload = [
        {
            "id": entry["id"],
            "type": entry["type"],
            "title": entry["title"],
            "text": entry["text"],
            "tags": entry["tags"],
            "created_at": entry["created_at"],
            "relations": entry["relations"],
            "metadata": entry["metadata"],
        }
        for entry in sorted(entries, key=lambda e: e["id"])
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


# hasSubject → judge. workflow(하위 workflow 위임)는 펼치지 않고 단일 노드로 두므로 HOTL 로 취급한다.
V07_JUDGE = {"human": "HITL", "model": "HOTL", "system": "HOOTL", "self": "HOTL", "workflow": "HOTL"}
V07_NODE_TYPE = {"task": "step", "decision": "decision", "eval": "validation", "event": "event", "end": "end"}


def _parse_v07(g: Graph, policy: dict[str, Any], warnings: list[str]) -> tuple[dict[str, Node], list[dict[str, str]], list[str]]:
    """mso-workflow-design 의 `wf_v07.control_graph` 결과를 IR 노드·엣지로 옮긴다.

    제어 Rail 판별·끝점 검증·subject 해석은 design 이 소유한다. 여기서는 실행 정책(judge→provider)만 입힌다.
    control_graph 가 errors 를 돌려주면 일부만 컴파일하지 않고 중단한다(사람 승인 지점이 누락된 채 통과하는 것을 막는다).
    """
    cg = _load_wf_v07().control_graph(g)
    if not cg["nodes"]:
        raise ValueError("v0.7 workflow cannot be compiled: no Execution/End nodes found")
    if cg["errors"]:
        raise ValueError("v0.7 workflow cannot be compiled: " + "; ".join(cg["errors"]))
    warnings.extend(cg["warnings"])
    nodes: dict[str, Node] = {}
    for item in cg["nodes"]:
        node_type = V07_NODE_TYPE[item["kind"]]
        subject = item["subject"]
        judge = V07_JUDGE[subject] if subject else None
        criteria = item["criteria"]
        node = Node(
            id=item["id"],
            uri=item["uri"],
            type=node_type,
            label=item["label"],
            status=item["status"],
            instruction=item["instruction"] or (criteria[0] if criteria and node_type != "validation" else None),
            judge=judge,
            harness=item["harness"] or item["method"],
            pass_criteria=criteria if node_type == "validation" else [],
            provider="python" if node_type in {"event", "end"} else _provider_for(node_type, judge, policy),
            subject=subject,
            requires_human=subject == "human",
        )
        if subject == "human" and node_type != "decision":
            node.provider = str(((policy.get("providers") or {}).get("decision") or {}).get("HITL", "human"))
        nodes[node.id] = node
    edges: list[dict[str, str]] = []
    for e in cg["edges"]:
        if nodes[e["source"]].type == "decision":
            on_value = e["on"] or "default"
            nodes[e["source"]].branches.append({"on": on_value, "goto": e["target"], "label": on_value})
            edges.append({"source": e["source"], "target": e["target"], "kind": "branch", "on": on_value, "label": on_value})
        else:
            edges.append({"source": e["source"], "target": e["target"], "kind": "rail"})
    for item in cg["ignored"]:
        warnings.append(f"{item['rail']}: {item['railType']} rail is not control flow ({item['reason']}), skipped")
    return nodes, edges, cg["entrypoints"]


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
    v07_edges: list[dict[str, str]] | None = None
    v07_entrypoints: list[str] = []

    if _load_wf_v07().is_v07_graph(g):
        nodes, v07_edges, v07_entrypoints = _parse_v07(g, policy, warnings)
        workflow_id = _safe_id(ttl_path.stem.replace(".abox", ""))

    for phase in ([] if v07_edges is not None else _subjects_by_type(g, WF.Phase)):
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
    for cls, node_type in ({} if v07_edges is not None else type_map).items():
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

    edges: list[dict[str, str]] = list(v07_edges or [])
    for subj, _, obj in ([] if v07_edges is not None else g.triples((None, WF.dependsOn, None))):
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

    for node in ([] if v07_edges is not None else list(nodes.values())):
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
    entrypoints = list(v07_entrypoints) or sorted(node_id for node_id, node in nodes.items() if node_id not in incoming and node.type == "phase")
    if not entrypoints:
        entrypoints = sorted(node_id for node_id in nodes if node_id not in incoming)

    memory_entries = load_work_memory(workmem_dir)
    context_enabled = bool((policy.get("context") or {}).get("enabled", True))
    context_packs = {
        node.id: _load_wm_context().build_context_pack(node.id, memory_entries, node.context_selector)
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


BINDING_KINDS = {"script", "agent", "interrupt"}
# 바인딩이 필요 없는 노드 타입: 시작/끝 표지.
UNBOUND_OK_TYPES = {"end", "start"}


def load_bindings(path: Path | None) -> dict[str, dict[str, Any]]:
    """노드 실행 바인딩(YAML/JSON)을 읽는다. 최상위 `bindings:` 키가 있으면 그 아래를, 없으면 전체를 노드 매핑으로 본다."""
    if path is None:
        return {}
    text = _read_text(path)
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - env dependent
            raise SystemExit("YAML bindings require PyYAML. Use JSON or install pyyaml.") from exc
        loaded = yaml.safe_load(text) or {}
    else:
        loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise SystemExit(f"bindings must be a mapping of node id -> binding: {path}")
    bindings = loaded.get("bindings", loaded)
    if not isinstance(bindings, dict):
        raise SystemExit(f"'bindings' must be a mapping of node id -> binding: {path}")
    return bindings


def validate_bindings(bindings: dict[str, dict[str, Any]], ir: dict[str, Any], strict: bool = False) -> tuple[list[str], list[str]]:
    """바인딩을 IR 과 대조한다. (errors, warnings) 를 돌려준다. 컴파일은 errors 가 있으면 중단한다.

    TTL(구조 정본)과 바인딩(수작업/에이전트 작성)이 어긋나는 것을 컴파일 시점에 잡는 게 목적이다.
    """
    errors: list[str] = []
    warnings: list[str] = []
    nodes = {node["id"]: node for node in ir["nodes"]}
    for node_id, binding in bindings.items():
        if node_id not in nodes:
            errors.append(f"binding for unknown node {node_id!r} (not in TTL)")
            continue
        if not isinstance(binding, dict) or binding.get("kind") not in BINDING_KINDS:
            errors.append(f"{node_id}: kind must be one of {sorted(BINDING_KINDS)}")
            continue
        node = nodes[node_id]
        kind = binding["kind"]
        if kind == "script":
            run = binding.get("run")
            if not (isinstance(run, str) and run.strip()) and not (isinstance(run, list) and run and all(isinstance(x, (str, int)) for x in run)):
                errors.append(f"{node_id}: script binding needs `run` (string or argv list)")
            rule = binding.get("decision")
            branches = {edge["on"] for edge in ir["edges"] if edge["kind"] == "branch" and edge["source"] == node_id}
            if node["type"] == "decision":
                if not isinstance(rule, dict):
                    errors.append(f"{node_id}: decision node script binding needs `decision` ({{source, map}}) to choose a branch")
                else:
                    if rule.get("source", "exit_code") not in {"exit_code", "stdout_json"}:
                        errors.append(f"{node_id}: decision.source must be exit_code or stdout_json")
                    targets = {v for k, v in (rule.get("map") or {}).items()}
                    unknown = targets - branches
                    if unknown:
                        errors.append(f"{node_id}: decision.map targets {sorted(unknown)} are not branches {sorted(branches)}")
            elif rule:
                errors.append(f"{node_id}: `decision` is only valid on decision nodes")
            if node.get("requires_human"):
                warnings.append(f"{node_id}: script binding on a human node bypasses the human gate; use kind=interrupt")
        if kind == "interrupt" and not node.get("requires_human") and node["type"] != "decision":
            warnings.append(f"{node_id}: interrupt on a non-human, non-decision node")
    for node_id, node in nodes.items():
        if node_id in bindings or node["type"] in UNBOUND_OK_TYPES:
            continue
        message = f"{node_id}: no binding (runs as planned only)"
        (errors if strict else warnings).append(message)
    return errors, warnings


def render_graph_py(ir: dict[str, Any], policy: dict[str, Any], bindings: dict[str, dict[str, Any]] | None = None) -> str:
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
        "engines": policy.get("engines", {}),
        "local_engine": policy.get("local_engine", "ollama"),
        "planes": policy.get("planes", {}),
        "policy": policy,
        "bindings": bindings or {},
    }
    payload_py = pformat(payload, width=100, sort_dicts=False).replace("\n", "\n    ")

    return textwrap.dedent(f'''\
    #!/usr/bin/env python3
    """Generated LangGraph adapter for MSO workflow {ir["workflow_id"]}.

    Generated from TTL ABox. Do not edit by hand; regenerate with
    mso-workflow-optimizer/scripts/compile_workflow.py.
    """

    from __future__ import annotations

    import json
    import os
    import shlex
    import subprocess
    from copy import deepcopy
    from typing import Annotated, Any

    PAYLOAD = {payload_py}

    try:
        from langgraph.graph import END, START, StateGraph
        LANGGRAPH_AVAILABLE = True
    except Exception:  # pragma: no cover - depends on optional runtime
        END = "__end__"
        START = "__start__"
        StateGraph = None
        LANGGRAPH_AVAILABLE = False
    try:
        from langgraph.types import Command, interrupt
    except Exception:  # pragma: no cover - depends on optional runtime
        Command = None
        interrupt = None

    # build_graph(checkpointer=...) 로 만든 그래프에서만 True. True 이면 사람/에이전트 대기를 halt 가 아니라
    # interrupt 로 멈추고 resume() 으로 같은 지점에서 이어간다.
    _CHECKPOINTED = False


    def node_specs() -> dict[str, dict[str, Any]]:
        return deepcopy(PAYLOAD["node_specs"])


    def _pause(state: dict[str, Any], node_id: str, reason: str, event: dict[str, Any]) -> Any:
        """체크포인터가 있으면 interrupt 로 멈추고 재개 값을 돌려준다. 없으면 halt 하고 None 을 돌려준다."""
        if _CHECKPOINTED and interrupt is not None:
            return interrupt(dict(event, node_id=node_id, reason=reason))
        state["halted"] = True
        state["halt_reason"] = reason
        events = list(state.get("control_plane_events", []))
        events.append(dict(event, node_id=node_id, status="pending-control-plane"))
        state["control_plane_events"] = events
        return None


    def _apply_resume(state: dict[str, Any], node_id: str, value: Any) -> None:
        """재개 값을 state 에 반영한다. 문자열은 분기 결정, dict 는 노드 결과(decision 키가 있으면 결정도)."""
        results = dict(state.get("node_results", {{}}))
        decisions = dict(state.get("decisions", {{}}))
        if isinstance(value, dict):
            results[node_id] = dict(results.get(node_id, {{}}), **value)
            if value.get("decision") is not None:
                decisions[node_id] = value["decision"]
        elif value is not None:
            results[node_id] = dict(results.get(node_id, {{}}), value=value)
            decisions[node_id] = value
        state["node_results"] = results
        state["decisions"] = decisions
        _mark_runtime(state, node_id)


    def _mark_runtime(state: dict[str, Any], node_id: str) -> None:
        """런타임(script/재개)에서 만들어진 결정·결과를 기록한다. 되돌림 루프 재진입 시 이것만 폐기한다(초기 입력은 유지)."""
        # 목록이 아니라 dict: 변경분(delta)은 바뀐 키만 담기 때문에 목록을 걸러내고 다시 채우면 항목이 누락될 수 있다.
        produced = dict(state.get("runtime_produced", {{}}))
        produced[node_id] = True
        state["runtime_produced"] = produced


    def _branch_ons(node_id: str) -> set[str]:
        return {{edge["on"] for edge in PAYLOAD["branch_edges"] if edge["source"] == node_id}}


    def _run_script(state: dict[str, Any], node_id: str, binding: dict[str, Any]) -> None:
        """script 바인딩 실행. state['execute'] 가 참일 때만 실제로 돌린다(기본은 dry-run)."""
        results = dict(state.get("node_results", {{}}))
        if not state.get("execute"):
            state["node_outputs"][node_id]["status"] = "bound-dry-run"
            return
        if (results.get(node_id) or {{}}).get("executed"):
            return
        command = binding["run"]
        argv = shlex.split(command) if isinstance(command, str) else [str(part) for part in command]
        env = dict(os.environ, MSO_WORKFLOW_ID=PAYLOAD["workflow_id"], MSO_NODE_ID=node_id)
        env.update({{str(k): str(v) for k, v in (binding.get("env") or {{}}).items()}})
        payload = json.dumps(
            {{"node_id": node_id, "node_results": state.get("node_results", {{}}), "decisions": state.get("decisions", {{}}),
              "inputs": state.get("inputs", {{}})}},
            ensure_ascii=False, default=str,
        )
        proc = subprocess.run(
            argv, input=payload, capture_output=True, text=True, env=env,
            cwd=binding.get("cwd") or state.get("cwd") or None, timeout=int(binding.get("timeout", 600)),
        )
        parsed = None
        try:
            parsed = json.loads(proc.stdout) if proc.stdout.strip() else None
        except ValueError:
            parsed = None
        result = {{"executed": True, "returncode": proc.returncode, "stdout": proc.stdout[-4000:],
                  "stderr": proc.stderr[-2000:], "output": parsed}}
        results[node_id] = dict(results.get(node_id, {{}}), **result)
        state["node_results"] = results
        _mark_runtime(state, node_id)
        state["node_outputs"][node_id]["status"] = "executed"
        rule = binding.get("decision")
        if rule:
            source = rule.get("source", "exit_code")
            if source == "exit_code":
                raw = str(proc.returncode)
            else:
                raw = parsed.get(rule.get("key", "decision")) if isinstance(parsed, dict) else None
            mapping = {{str(k): v for k, v in (rule.get("map") or {{}}).items()}}
            value = mapping.get(str(raw), mapping.get("default")) if mapping else raw
            if value in _branch_ons(node_id):
                decisions = dict(state.get("decisions", {{}}))
                decisions[node_id] = value
                state["decisions"] = decisions
                return
            state["halted"] = True
            state["halt_reason"] = "script_undecided:" + node_id
        elif proc.returncode != 0:
            state["halted"] = True
            state["halt_reason"] = "script_failed:" + node_id


    def _run_binding(state: dict[str, Any], node_id: str) -> None:
        binding = (PAYLOAD.get("bindings") or {{}}).get(node_id)
        if not binding or state.get("halted"):
            return
        kind = binding["kind"]
        results = state.get("node_results", {{}}) or {{}}
        if kind == "script":
            _run_script(state, node_id, binding)
        elif kind == "agent" and not results.get(node_id):
            event = {{"action": "delegate_to_agent", "instruction": PAYLOAD["node_specs"][node_id].get("instruction"),
                     "session": binding.get("session"), "expects": binding.get("expects")}}
            value = _pause(state, node_id, "awaiting_agent:" + node_id, event)
            if value is not None:
                _apply_resume(state, node_id, value)
        elif kind == "interrupt" and not results.get(node_id) and node_id not in (state.get("decisions", {{}}) or {{}}):
            event = {{"action": "request_user_decision", "instruction": PAYLOAD["node_specs"][node_id].get("instruction"),
                     "choices": sorted(_branch_ons(node_id))}}
            value = _pause(state, node_id, "awaiting_human:" + node_id, event)
            if value is not None:
                _apply_resume(state, node_id, value)


    def _run_node(state: dict[str, Any], node_id: str) -> dict[str, Any]:
        state = dict(state or {{}})
        if state.get("halted"):
            return state
        spec = PAYLOAD["node_specs"][node_id]
        visits = dict(state.get("visits", {{}}))
        visits[node_id] = visits.get(node_id, 0) + 1
        state["visits"] = visits
        if visits[node_id] > int(PAYLOAD.get("policy", {{}}).get("loop_limit", 5)):
            state["halted"] = True
            state["halt_reason"] = f"loop_limit:{{node_id}}"
            return state
        if visits[node_id] > 1 and (state.get("runtime_produced", {{}}) or {{}}).get(node_id):
            # 되돌림 루프로 다시 들어온 노드: 이전 라운드에서 런타임에 만든 결정·결과는 낡았으므로 버리고 다시 받는다.
            state["decisions"] = {{k: v for k, v in (state.get("decisions", {{}}) or {{}}).items() if k != node_id}}
            state["node_results"] = {{k: v for k, v in (state.get("node_results", {{}}) or {{}}).items() if k != node_id}}
            state["runtime_produced"] = dict(state["runtime_produced"], **{{node_id: False}})
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
        _run_binding(state, node_id)
        node_result = (state.get("node_results", {{}}) or {{}}).get(node_id) or {{}}
        branch_ons = _branch_ons(node_id)
        if spec.get("requires_human") and not state.get("halted") and not (node_result or (state.get("decisions", {{}}) or {{}}).get(node_id)):
            event = {{"action": "request_user_decision", "instruction": spec.get("instruction"), "choices": sorted(branch_ons)}}
            value = _pause(state, node_id, "awaiting_human:" + node_id, event)
            if value is not None:
                _apply_resume(state, node_id, value)
                node_result = (state.get("node_results", {{}}) or {{}}).get(node_id) or {{}}
        # fallback(선형) 모드는 분기를 무시하므로 decision 미결정 halt 는 LangGraph 모드에서만 적용한다.
        if LANGGRAPH_AVAILABLE and branch_ons and not state.get("halted") and (state.get("decisions", {{}}) or {{}}).get(node_id) not in branch_ons:
            event = {{"action": "request_decision", "instruction": spec.get("instruction"), "choices": sorted(branch_ons)}}
            value = _pause(state, node_id, "awaiting_decision:" + node_id, event)
            if value is not None:
                _apply_resume(state, node_id, value)
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


    def engine_for(node_id: str) -> dict[str, Any] | None:
        """노드 provider 가 local-<engine> 이면 그 서빙 엔진(base_url 등)을 돌려준다."""
        provider = PAYLOAD["node_specs"][node_id]["provider"]
        if not provider.startswith("local-"):
            return None
        name = provider[len("local-"):]
        cfg = PAYLOAD.get("engines", {{}}).get(name)
        return dict(cfg, name=name) if cfg else None


    def _route_decision(state: dict[str, Any], node_id: str) -> str:
        if (state or {{}}).get("halted"):
            return "__halt__"
        decisions = (state or {{}}).get("decisions", {{}})
        selected = decisions.get(node_id)
        branches = [edge for edge in PAYLOAD["branch_edges"] if edge["source"] == node_id]
        allowed = {{edge["on"] for edge in branches}}
        if selected in allowed:
            return selected
        return "__halt__" if branches else "__end__"


    def _merge_state(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
        """병렬 분기가 같은 step 에서 돌려주는 상태 변경분을 합친다(LangGraph reducer)."""
        merged = dict(left or {{}})
        for key, value in (right or {{}}).items():
            current = merged.get(key)
            if isinstance(value, list) and isinstance(current, list):
                merged[key] = current + value
            elif isinstance(value, dict) and isinstance(current, dict):
                combined = dict(current)
                combined.update(value)
                merged[key] = combined
            elif key == "halted":
                merged[key] = bool(current) or bool(value)
            else:
                merged[key] = value
        return merged


    def _state_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        """노드가 바꾼 부분만 돌려준다. 전체 상태를 돌려주면 병렬 노드끼리 덮어써 InvalidUpdateError 가 난다."""
        delta: dict[str, Any] = {{}}
        for key, value in after.items():
            old = before.get(key)
            if key not in before:
                delta[key] = value
            elif isinstance(value, list) and isinstance(old, list):
                if len(value) > len(old):
                    delta[key] = value[len(old):]
            elif isinstance(value, dict) and isinstance(old, dict):
                changed = {{k: v for k, v in value.items() if k not in old or old[k] != v}}
                if changed:
                    delta[key] = changed
            elif value != old:
                delta[key] = value
        return delta


    def _node_update(state: dict[str, Any], node_id: str) -> dict[str, Any]:
        before = deepcopy(state or {{}})
        return _state_delta(before, _run_node(state, node_id))


    class FallbackGraph:
        def invoke(self, initial_state: dict[str, Any] | None = None) -> dict[str, Any]:
            state = dict(initial_state or {{}})
            for node_id in PAYLOAD["node_order"]:
                state = _run_node(state, node_id)
                if state.get("halted"):
                    break
            state["langgraph_available"] = False
            return state


    def build_graph(checkpointer=None):
        global _CHECKPOINTED
        if not LANGGRAPH_AVAILABLE:
            return FallbackGraph()
        _CHECKPOINTED = checkpointer is not None

        graph = StateGraph(Annotated[dict, _merge_state])
        for node_id in PAYLOAD["node_order"]:
            graph.add_node(node_id, lambda state, node_id=node_id: _node_update(state, node_id))

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
            mapping["__halt__"] = END
            if mapping:
                graph.add_conditional_edges(
                    node_id,
                    lambda state, node_id=node_id: _route_decision(state, node_id),
                    mapping,
                )

        for node_id in PAYLOAD["terminal_nodes"]:
            graph.add_edge(node_id, END)

        return graph.compile(checkpointer=checkpointer) if checkpointer is not None else graph.compile()


    def invoke(initial_state: dict[str, Any] | None = None) -> dict[str, Any]:
        return build_graph().invoke(initial_state or {{}})


    def sqlite_checkpointer(path: str):
        """SQLite 체크포인터(pip install langgraph-checkpoint-sqlite). 프로세스가 끝나도 대기 지점이 남는다."""
        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver
        return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


    def _config(thread_id: str) -> dict[str, Any]:
        return {{"configurable": {{"thread_id": thread_id}}, "recursion_limit": 200}}


    def start(thread_id: str, initial_state: dict[str, Any] | None, checkpointer) -> dict[str, Any]:
        """thread_id 로 실행을 시작한다. interrupt 에서 멈추면 결과에 '__interrupt__' 가 담긴다."""
        return build_graph(checkpointer).invoke(initial_state or {{}}, config=_config(thread_id))


    def resume(thread_id: str, value: Any, checkpointer) -> dict[str, Any]:
        """멈춘 지점에서 이어간다. value 는 분기 이름(문자열) 또는 노드 결과 dict(decision 키 선택)."""
        return build_graph(checkpointer).invoke(Command(resume=value), config=_config(thread_id))
    ''')


def compile_workflow(
    ttl_path: Path,
    out_root: Path,
    policy_path: Path | None,
    mode: str | None,
    workmem_dir: Path | None = None,
    local_engine: str | None = None,
    bindings_path: Path | None = None,
    strict_bindings: bool = False,
) -> Path:
    policy = _load_policy(policy_path, mode)
    if local_engine:
        if local_engine not in policy["engines"]:
            raise SystemExit(f"unknown local engine {local_engine!r}; choose one of {sorted(policy['engines'])}")
        policy["local_engine"] = local_engine
    ir = parse_ttl(ttl_path, policy, workmem_dir=workmem_dir)
    bindings = load_bindings(bindings_path)
    if bindings_path is not None or strict_bindings:
        binding_errors, binding_warnings = validate_bindings(bindings, ir, strict=strict_bindings)
        ir["warnings"] = list(ir["warnings"]) + [f"bindings: {w}" for w in binding_warnings]
        if binding_errors:
            raise SystemExit("invalid bindings:\n  " + "\n  ".join(binding_errors))
    artifact_dir = out_root / _safe_id(ir["workflow_id"])
    artifact_dir.mkdir(parents=True, exist_ok=True)

    (artifact_dir / "workflow_ir.json").write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (artifact_dir / "optimizer_policy.json").write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (artifact_dir / "graph.py").write_text(render_graph_py(ir, policy, bindings), encoding="utf-8")
    manifest = {
        "name": ir["workflow_id"],
        "source_ttl": ir["source_ttl"],
        "source_sha256": ir["source_sha256"],
        "workmem_dir": ir.get("workmem_dir"),
        "workmem_sha256": ir.get("workmem_sha256"),
        "bindings": str(bindings_path) if bindings_path else None,
        "bindings_sha256": _sha256(bindings_path) if bindings_path else None,
        "bound_nodes": sorted(bindings),
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
    parser.add_argument("--local-engine", choices=sorted(DEFAULT_ENGINES), help="local AI serving engine for the generic local slot (default: policy local_engine, else ollama)")
    parser.add_argument("--workmem", type=Path, help="agent-context/work-memory directory for ContextPack snapshot")
    parser.add_argument("--bindings", type=Path, help="node execution bindings YAML/JSON (hand/agent-authored, validated against the TTL; see references/bindings.md)")
    parser.add_argument("--strict-bindings", action="store_true", help="fail if any non-end node has no binding")
    parser.add_argument("--print-ir", action="store_true", help="print workflow_ir.json after compiling")
    args = parser.parse_args(argv)

    artifact_dir = compile_workflow(args.ttl, args.out, args.policy, args.mode, workmem_dir=args.workmem, local_engine=args.local_engine,
                                    bindings_path=args.bindings, strict_bindings=args.strict_bindings)
    if importlib.util.find_spec("langgraph") is None:
        print(
            "[note] langgraph is not installed: generated graph.py will use the linear fallback invoke() "
            "(branches and loops are ignored). To execute it as a graph: pip install -r requirements-langgraph.txt",
            file=sys.stderr,
        )
    if args.print_ir:
        print((artifact_dir / "workflow_ir.json").read_text(encoding="utf-8"))
    else:
        print(artifact_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
