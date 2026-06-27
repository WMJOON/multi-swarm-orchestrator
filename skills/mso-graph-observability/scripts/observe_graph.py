#!/usr/bin/env python3
"""Generate graph observability views for MSO repositories.

The first implemented scope is the workflow graph: Mermaid views from workflow
TTL/ABox plus the bundled workflow TBox. Memory/audit/worklog graph analytics
belong in this skill as later scopes.

YAML workflow files are intentionally not topology inputs. They are accepted
only as legacy migration inputs; sibling *.abox.ttl files are the observable
SSOT.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - optional index registry support
    yaml = None

try:
    from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
    from rdflib.namespace import OWL, XSD
except ImportError as exc:  # pragma: no cover - user environment guard
    raise SystemExit(
        "rdflib is required. Install project dependencies with `pip install -r requirements.txt`."
    ) from exc


WF = Namespace("https://mso.dev/ontology/workflow#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

CLASS_TYPES = {OWL.Class, RDFS.Class}
PROPERTY_TYPES = {OWL.ObjectProperty, OWL.DatatypeProperty, RDF.Property}
LITERAL_RANGES = {
    XSD.string,
    XSD.boolean,
    XSD.integer,
    XSD.decimal,
    XSD.date,
    XSD.dateTime,
    RDFS.Literal,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate graph observability views for MSO repositories."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--workflow-dir",
        type=Path,
        help="Directory containing workflow TTL files. Defaults to <root>/agent-context/workflow if it exists, otherwise <root>.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory. Defaults to <root>/agent-context/observability/graph when available, otherwise <workflow-dir>/observability.",
    )
    parser.add_argument(
        "--ontology",
        type=Path,
        action="append",
        default=[],
        help="Additional TTL file to parse. Can be repeated.",
    )
    parser.add_argument(
        "--no-default-tbox",
        action="store_true",
        help="Do not include MSO's bundled workflow TBox.",
    )
    parser.add_argument(
        "--strict-ssot",
        action="store_true",
        help="Exit non-zero when workflow YAML files do not have sibling *.abox.ttl files.",
    )
    return parser.parse_args()


def default_tbox_path() -> Path:
    skill_dir = Path(__file__).resolve().parents[1]
    skills_dir = skill_dir.parent
    return skills_dir / "mso-workflow-design" / "references" / "tbox" / "workflow-tbox.ttl"


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, list[Path]]:
    root = args.root.resolve()
    workflow_dir = (
        args.workflow_dir.resolve()
        if args.workflow_dir
        else (root / "agent-context" / "workflow")
    )
    if not workflow_dir.exists():
        workflow_dir = root

    output_dir = args.output_dir.resolve() if args.output_dir else default_output_dir(root, workflow_dir)

    ttl_paths: list[Path] = []
    if workflow_dir.exists():
        ttl_paths.extend(sorted(p for p in workflow_dir.rglob("*.ttl") if p.is_file()))

    if not args.no_default_tbox:
        tbox = default_tbox_path()
        if tbox.exists():
            ttl_paths.append(tbox)

    ttl_paths.extend(p.resolve() for p in args.ontology if p.exists())

    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for path in ttl_paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_paths.append(resolved)

    return workflow_dir, output_dir, unique_paths


def parse_graph(ttl_paths: Iterable[Path]) -> Graph:
    graph = Graph()
    for path in ttl_paths:
        graph.parse(path, format="turtle")
    return graph


def is_workflow_abox(path: Path) -> bool:
    return path.name.endswith(".abox.ttl")


def default_output_dir(root: Path, workflow_dir: Path) -> Path:
    agent_context = root / "agent-context"
    if agent_context.exists():
        return agent_context / "observability" / "graph"
    return workflow_dir / "observability"


def workflow_ssot_state(workflow_dir: Path) -> dict[str, list[Path]]:
    yaml_paths = sorted(
        p
        for p in workflow_dir.rglob("*.yaml")
        if p.is_file() and "observability" not in p.parts
    )
    abox_paths = sorted(p for p in workflow_dir.rglob("*.abox.ttl") if p.is_file())
    abox_by_stem = {p.name.removesuffix(".abox.ttl"): p for p in abox_paths}

    yaml_with_abox: list[Path] = []
    yaml_without_abox: list[Path] = []
    for path in yaml_paths:
        if path.stem in abox_by_stem:
            yaml_with_abox.append(path)
        else:
            yaml_without_abox.append(path)

    yaml_stems = {p.stem for p in yaml_paths}
    abox_without_yaml = [
        path for path in abox_paths if path.name.removesuffix(".abox.ttl") not in yaml_stems
    ]

    return {
        "yaml": yaml_paths,
        "abox": abox_paths,
        "yaml_with_abox": yaml_with_abox,
        "yaml_without_abox": yaml_without_abox,
        "abox_without_yaml": abox_without_yaml,
    }


def local_name(term: URIRef | Literal | str) -> str:
    text = str(term)
    if "#" in text:
        return text.rsplit("#", 1)[1]
    return text.rstrip("/").rsplit("/", 1)[-1]


def scoped_local_parts(term: URIRef | Literal | str, prefix: str) -> list[str]:
    local = local_name(term)
    if not local.startswith(prefix):
        return []
    return [part for part in local.removeprefix(prefix).split("/") if part]


def workflow_scope(term: URIRef | Literal | str) -> str | None:
    """Return workflow/module scope from scoped workflow URIs.

    Current scoped URIs look like `phase/<workflow-id>/<phase-id>` and
    `node/<workflow-id>/<node-id>`. Legacy flat URIs return None.
    """
    for prefix in ("phase/", "node/"):
        parts = scoped_local_parts(term, prefix)
        if len(parts) >= 2:
            return parts[0]
    return None


def display_id(term: URIRef | Literal | str) -> str:
    for prefix in ("phase/", "node/"):
        parts = scoped_local_parts(term, prefix)
        if parts:
            return parts[-1]
    return local_name(term)


def normalize_locator(value: str) -> str:
    text = re.sub(r"/+", "/", value.replace("\\", "/").strip())
    if text.startswith("./"):
        text = text[2:]
    while text.startswith("../"):
        text = text[3:]
    if text and value.endswith("/") and not text.endswith("/"):
        text = f"{text}/"
    return text


def locator_lookup_keys(value: str) -> set[str]:
    normalized = normalize_locator(value)
    keys = {value.strip(), normalized}
    if normalized.endswith("/"):
        keys.add(normalized.rstrip("/"))
    elif normalized:
        keys.add(f"{normalized}/")
    return {key for key in keys if key}


def load_yaml_file(path: Path) -> dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def index_candidates(root: Path) -> list[Path]:
    return [
        root / "agent-context" / "index" / "index.yaml",
        root / "index.yaml",
    ]


def register_data_ref(
    registry: dict[str, dict[str, str]],
    *,
    data_id_value: str,
    data_type: str,
    locator: str,
    source: str,
) -> None:
    locator_norm = normalize_locator(locator)
    if not data_id_value or not locator_norm:
        return
    ref = {
        "id": data_id_value,
        "data_type": data_type or "local_file",
        "locator": locator_norm,
        "source": source,
    }
    for key in locator_lookup_keys(locator_norm):
        registry.setdefault(key, ref)


def load_data_registry(root: Path) -> dict[str, dict[str, str]]:
    registry: dict[str, dict[str, str]] = {}
    index_path = next((path for path in index_candidates(root) if path.exists()), None)
    if index_path is None:
        return registry

    doc = load_yaml_file(index_path)
    for item in doc.get("data_registry", []) or []:
        if not isinstance(item, dict):
            continue
        data_id_value = str(item.get("id") or "").strip()
        data_type = str(item.get("data_type") or item.get("type") or "local_file").strip()
        locator = str(
            item.get("locator")
            or item.get("location")
            or item.get("path")
            or item.get("endpoint")
            or item.get("resource")
            or ""
        ).strip()
        register_data_ref(
            registry,
            data_id_value=data_id_value,
            data_type=data_type,
            locator=locator,
            source="data_registry",
        )

    for module in doc.get("modules", []) or []:
        if not isinstance(module, dict):
            continue
        module_id = str(module.get("id") or "").strip()
        module_path = str(module.get("path") or "").strip()
        register_data_ref(
            registry,
            data_id_value=module_id,
            data_type=str(module.get("data_type") or "local_file"),
            locator=module_path,
            source="module",
        )
        for subdir in module.get("subdirs", []) or []:
            if not isinstance(subdir, dict):
                continue
            sub_path = str(subdir.get("path") or "").strip()
            sub_id = str(subdir.get("id") or "").strip()
            if not sub_id:
                sub_slug = normalize_locator(sub_path).strip("/").replace("/", ".")
                sub_id = f"{module_id}.{sub_slug}" if sub_slug else module_id
            register_data_ref(
                registry,
                data_id_value=sub_id,
                data_type=str(subdir.get("data_type") or "local_file"),
                locator=f"{module_path}{sub_path}",
                source="subdir",
            )
    return registry


def literal_text(value: Literal | str) -> str:
    return str(value).replace("\n", " ").strip()


def preferred_label(graph: Graph, term: URIRef | Literal | str) -> str:
    if isinstance(term, Literal):
        return literal_text(term)
    if not isinstance(term, URIRef):
        return str(term)

    for predicate in (RDFS.label, WF.label, SKOS.prefLabel):
        value = graph.value(term, predicate)
        if value:
            return literal_text(value)
    return local_name(term)


def mermaid_id(prefix: str, term: URIRef | Literal | str) -> str:
    digest = hashlib.sha1(str(term).encode("utf-8")).hexdigest()[:10]
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", local_name(term))[:40].strip("_")
    if not cleaned:
        cleaned = "node"
    return f"{prefix}_{cleaned}_{digest}"


def mermaid_label(text: str, max_len: int = 72) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) > max_len:
        compact = compact[: max_len - 1].rstrip() + "..."
    return compact.replace('"', "'")


def mermaid_shape(node_id: str, label: str, shape: str = "rect") -> str:
    if shape == "circle":
        return f"{node_id}(({label}))"
    if shape == "stadium":
        return f'{node_id}(["{label}"])'
    if shape == "hexagon":
        return f'{node_id}{{{{"{label}"}}}}'
    if shape == "trapezoid":
        return f'{node_id}[/"{label}"\\]'
    return f'{node_id}["{label}"]'


def mermaid_node_label(graph: Graph, term: URIRef, suffix: str = "") -> str:
    label = preferred_label(graph, term)
    node_id = display_id(term)
    parts = [label]
    if node_id and node_id != label:
        parts.append(f"id: {node_id}")
    if suffix:
        parts.append(suffix)
    return mermaid_label("\\n".join(parts), 140)


def mermaid_node(graph: Graph, term: URIRef, prefix: str, suffix: str = "", shape: str = "rect") -> str:
    node_id = mermaid_id(prefix, term)
    label = mermaid_node_label(graph, term, suffix)
    return mermaid_shape(node_id, label, shape)


def subjects_of_type(graph: Graph, cls: URIRef) -> list[URIRef]:
    return sorted(
        (subject for subject in graph.subjects(RDF.type, cls) if isinstance(subject, URIRef)),
        key=str,
    )


def first_literal(graph: Graph, subject: URIRef, predicate: URIRef) -> str | None:
    value = graph.value(subject, predicate)
    if isinstance(value, Literal):
        return literal_text(value)
    return None


def write_markdown(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n{body.rstrip()}\n", encoding="utf-8")


def rel_path(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def build_workflow_ssot_report(workflow_dir: Path) -> tuple[str, int]:
    state = workflow_ssot_state(workflow_dir)
    missing = state["yaml_without_abox"]

    def list_paths(paths: list[Path]) -> str:
        if not paths:
            return "- _None._"
        return "\n".join(f"- `{rel_path(path, workflow_dir)}`" for path in paths)

    body = "\n".join(
        [
            "> Workflow observability uses TTL ABox files only. YAML files are legacy migration inputs and are not topology inputs.",
            "",
            "## Summary",
            "",
            f"- YAML workflow files: {len(state['yaml'])}",
            f"- TTL ABox workflow files: {len(state['abox'])}",
            f"- YAML files with sibling TTL ABox: {len(state['yaml_with_abox'])}",
            f"- YAML-only files excluded from topology: {len(missing)}",
            f"- TTL ABox files without legacy YAML source: {len(state['abox_without_yaml'])}",
            "",
            "## YAML-Only Workflows Excluded From Topology",
            "",
            list_paths(missing),
            "",
            "## TTL ABox Inputs Used For Workflow Topology",
            "",
            list_paths(state["abox"]),
            "",
            "## Migration",
            "",
            "Import legacy YAML into sibling `.abox.ttl` files before relying on workflow topology views:",
            "",
            "```bash",
            "python skills/mso-workflow-design/scripts/migrate_workflows_to_ttl.py agent-context/workflow",
            "```",
        ]
    )
    return body, len(missing)


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                yield {"_parse_error": True, "_path": str(path), "_line": line_number}
                continue
            if isinstance(value, dict):
                value.setdefault("_path", str(path))
                value.setdefault("_line", line_number)
                yield value


def nested_get(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        current: Any = record
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, ""):
            return current
    return None


def normalized_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value[:3])
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:120]
    text = str(value).strip()
    return text or None


def discover_runtime_sources(root: Path) -> dict[str, list[Path]]:
    work_memory = root / "agent-context" / "work-memory"
    return {
        "memory": sorted(
            p
            for p in work_memory.rglob("*.jsonl")
            if p.is_file() and "auditlog" not in p.parts and "worklog" not in p.parts
        )
        if work_memory.exists()
        else [],
        "audit": sorted((work_memory / "auditlog").rglob("*.jsonl"))
        if (work_memory / "auditlog").exists()
        else [],
        "worklog": sorted((work_memory / "worklog").rglob("*.jsonl"))
        if (work_memory / "worklog").exists()
        else [],
        "intent": [root / ".mso-context" / "conversation" / "turns.jsonl"]
        if (root / ".mso-context" / "conversation" / "turns.jsonl").exists()
        else [],
    }


def is_failure_like(record: dict[str, Any]) -> bool:
    fields = [
        nested_get(record, ["status", "result.status", "metadata.status"]),
        nested_get(record, ["event_type", "type", "entry_type", "kind"]),
        nested_get(record, ["error", "exception", "failure", "metadata.severity"]),
    ]
    text = " ".join(str(field).lower() for field in fields if field is not None)
    return any(token in text for token in ("fail", "failed", "error", "blocked", "timeout", "exception"))


def top_items(counter: Counter[str], limit: int = 10) -> str:
    if not counter:
        return "- _No data._"
    return "\n".join(f"- `{key}`: {count}" for key, count in counter.most_common(limit))


def table_rows(rows: list[tuple[str, str, int]], limit: int = 12) -> str:
    if not rows:
        return "_No repeated signals found._"
    lines = ["| Dimension | Value | Count |", "|---|---:|---:|"]
    for dimension, value, count in rows[:limit]:
        lines.append(f"| `{dimension}` | `{value}` | {count} |")
    return "\n".join(lines)


def build_runtime_analysis(root: Path) -> str:
    sources = discover_runtime_sources(root)
    source_counts = {scope: len(paths) for scope, paths in sources.items()}
    records_by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    parse_errors: list[dict[str, Any]] = []

    for scope, paths in sources.items():
        for path in paths:
            for record in iter_jsonl(path):
                if record.get("_parse_error"):
                    parse_errors.append(record)
                records_by_scope[scope].append(record)

    status_counts: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    workflow_counts: Counter[str] = Counter()
    intent_counts: Counter[str] = Counter()
    failure_hotspots: Counter[str] = Counter()
    repeated_signals: Counter[tuple[str, str]] = Counter()
    memory_prefixes: Counter[str] = Counter()

    id_keys = ["id", "entry_id", "metadata.id", "run_id", "ticket_id", "intent_id"]
    hotspot_keys = {
        "workflow": ["workflow", "workflow_id", "metadata.workflow", "metadata.workflow_id"],
        "phase": ["phase", "phase_id", "metadata.phase", "metadata.phase_id"],
        "node": ["node", "node_id", "metadata.node", "metadata.node_id"],
        "tool": ["tool", "tool_name", "tool.name", "metadata.tool", "command"],
        "intent": ["intent_id", "intent.id", "metadata.intent_id"],
    }

    for scope, records in records_by_scope.items():
        for record in records:
            status = normalized_value(nested_get(record, ["status", "result.status", "metadata.status"]))
            event = normalized_value(nested_get(record, ["event_type", "type", "entry_type", "kind"]))
            workflow = normalized_value(nested_get(record, hotspot_keys["workflow"]))
            intent = normalized_value(nested_get(record, hotspot_keys["intent"]))

            if status:
                status_counts[f"{scope}:{status}"] += 1
            if event:
                event_counts[f"{scope}:{event}"] += 1
            if workflow:
                workflow_counts[workflow] += 1
            if intent:
                intent_counts[intent] += 1

            record_id = normalized_value(nested_get(record, id_keys))
            if record_id:
                repeated_signals[(scope, record_id)] += 1
                prefix_match = re.match(r"^([A-Z]{2})[-_]", record_id)
                if prefix_match:
                    memory_prefixes[prefix_match.group(1)] += 1

            if is_failure_like(record):
                for dimension, keys in hotspot_keys.items():
                    value = normalized_value(nested_get(record, keys))
                    if value:
                        failure_hotspots[f"{dimension}:{value}"] += 1
                if not any(normalized_value(nested_get(record, keys)) for keys in hotspot_keys.values()):
                    failure_hotspots[f"{scope}:unknown"] += 1

    repeated_rows = [
        (dimension, value, count)
        for (dimension, value), count in repeated_signals.items()
        if count > 1
    ]
    repeated_rows.sort(key=lambda item: item[2], reverse=True)

    source_lines = "\n".join(f"- `{scope}`: {count} files" for scope, count in source_counts.items())
    record_lines = "\n".join(
        f"- `{scope}`: {len(records)} records" for scope, records in sorted(records_by_scope.items())
    )
    parse_error_lines = "\n".join(
        f"- `{error.get('_path')}` line {error.get('_line')}" for error in parse_errors[:10]
    )

    return "\n".join(
        [
            "> Baseline runtime graph analysis from MSO JSONL sources. Treat this as an operational signal, not a formal audit.",
            "",
            "## Sources",
            "",
            source_lines or "- _No runtime JSONL sources found._",
            "",
            "## Records",
            "",
            record_lines or "- _No records found._",
            "",
            "## Failure Hotspots",
            "",
            top_items(failure_hotspots),
            "",
            "## Workflow Usage",
            "",
            top_items(workflow_counts),
            "",
            "## Intent Usage",
            "",
            top_items(intent_counts),
            "",
            "## Status Counts",
            "",
            top_items(status_counts),
            "",
            "## Event Counts",
            "",
            top_items(event_counts),
            "",
            "## Repeated IDs",
            "",
            table_rows(repeated_rows),
            "",
            "## Memory Entry Prefixes",
            "",
            top_items(memory_prefixes),
            "",
            "## Parse Errors",
            "",
            parse_error_lines or "- _No parse errors._",
        ]
    )


def workflow_scopes(graph: Graph) -> list[str]:
    scopes = {
        scope
        for cls in (WF.Phase, WF.Step, WF.Decision, WF.Oracle, WF.Validation, WF.Group, WF.WorkflowRef)
        for subject in subjects_of_type(graph, cls)
        for scope in [workflow_scope(subject)]
        if scope
    }
    return sorted(scopes)


def scope_label(scope: str) -> str:
    return scope.replace("_", "-")


def filter_scope(terms: Iterable[URIRef], scope: str | None) -> list[URIRef]:
    if scope is None:
        return list(terms)
    return [term for term in terms if workflow_scope(term) == scope]


def workflow_node_terms(graph: Graph, scope: str | None = None) -> list[URIRef]:
    node_terms = {
        node
        for cls in (WF.Step, WF.Decision, WF.Oracle, WF.Validation, WF.Group, WF.WorkflowRef)
        for node in subjects_of_type(graph, cls)
    }
    return filter_scope(sorted(node_terms, key=str), scope)


def data_id(key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", key)[:40].strip("_")
    if not cleaned:
        cleaned = "data"
    return f"data_{cleaned}_{digest}"


def data_label(
    data_type: str,
    location: str,
    detail: str | None = None,
    node_id: str | None = None,
    locator: str | None = None,
) -> str:
    parts = ["DATA"]
    if node_id:
        parts.append(f"id: {node_id}")
    return mermaid_label("\\n".join(parts), 72)


def data_ref_for_locator(
    data_registry: dict[str, dict[str, str]],
    *,
    data_type: str,
    locator: str,
) -> dict[str, str]:
    normalized = normalize_locator(locator)
    for key in locator_lookup_keys(locator):
        ref = data_registry.get(key)
        if ref:
            return {
                "key": f"index:{ref['id']}",
                "id": ref["id"],
                "data_type": ref.get("data_type", data_type),
                "location": f"index:{ref['id']}",
                "locator": ref.get("locator", normalize_locator(locator)),
            }
    prefix_ref: dict[str, str] | None = None
    prefix_len = -1
    for ref in data_registry.values():
        ref_locator = ref.get("locator", "")
        if not ref_locator:
            continue
        prefix = ref_locator if ref_locator.endswith("/") else f"{ref_locator}/"
        if normalized.startswith(prefix) and len(prefix) > prefix_len:
            prefix_ref = ref
            prefix_len = len(prefix)
    if prefix_ref:
        return {
            "key": f"index:{prefix_ref['id']}",
            "id": prefix_ref["id"],
            "data_type": prefix_ref.get("data_type", data_type),
            "location": f"index:{prefix_ref['id']}",
            "locator": prefix_ref.get("locator", normalized),
        }
    fallback_id = f"{data_type}:{normalized}"
    return {
        "key": fallback_id,
        "id": fallback_id,
        "data_type": data_type,
        "location": normalized,
        "locator": normalized,
    }


def deliverable_data_ref(deliverable: str) -> dict[str, str]:
    digest = hashlib.sha1(deliverable.encode("utf-8")).hexdigest()[:10]
    key = f"deliverable:{digest}"
    return {
        "key": key,
        "id": key,
        "data_type": "local_file",
        "location": "declared deliverable",
        "locator": "",
        "detail": deliverable,
    }


def directory_data_for_node(graph: Graph, node: URIRef) -> list[tuple[str, str, str]]:
    data_items: list[tuple[str, str, str]] = []
    for directory in graph.objects(node, WF.directory):
        path_value = graph.value(directory, WF.dirPath)
        if not isinstance(path_value, Literal):
            continue
        role_value = graph.value(directory, WF.dirRole)
        role = literal_text(role_value) if isinstance(role_value, Literal) else "reference"
        path = literal_text(path_value)
        if path:
            data_items.append((role, path, f"local_file:{path}"))
    return data_items


def deliverable_data_for_node(graph: Graph, node: URIRef) -> list[tuple[str, str]]:
    data_items: list[tuple[str, str]] = []
    for value in graph.objects(node, WF.deliverables):
        if isinstance(value, Literal):
            text = literal_text(value)
            if text:
                data_items.append((text, f"deliverable:{text}"))
    return data_items


def data_edge_labels(role: str) -> tuple[bool, bool, str | None]:
    role_norm = role.lower().replace("-", "_")
    produces = "output" in role_norm or role_norm in {"staging", "generated", "write"}
    consumes = (
        "input" in role_norm
        or "reference" in role_norm
        or "instruction" in role_norm
        or role_norm in {"staging", "read"}
    )
    detail = "" if role_norm in {"output", "input", "reference", "input_output"} else role.strip()
    suffix = f":{mermaid_label(detail, 24)}" if detail else ""
    return produces, consumes, suffix


def markdown_cell(value: str | None, max_len: int = 96) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "..."
    return text.replace("|", "\\|") or "-"


def data_keys(graph: Graph, scope: str, data_registry: dict[str, dict[str, str]] | None = None) -> set[str]:
    data_registry = data_registry or {}
    keys: set[str] = set()
    for node in workflow_node_terms(graph, scope):
        for _, path, _ in directory_data_for_node(graph, node):
            keys.add(data_ref_for_locator(data_registry, data_type="local_file", locator=path)["id"])
        for deliverable, _ in deliverable_data_for_node(graph, node):
            keys.add(deliverable_data_ref(deliverable)["id"])
    return keys


def collect_data_streams(
    graph: Graph,
    data_registry: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, object]]:
    data_registry = data_registry or {}
    streams: dict[str, dict[str, object]] = {}
    for scope in workflow_scopes(graph):
        refs: dict[str, dict[str, str]] = {}
        producers: dict[str, set[str]] = {}
        consumers: dict[str, set[str]] = {}
        for node in workflow_node_terms(graph, scope):
            node_id = display_id(node)
            for role, path, _ in directory_data_for_node(graph, node):
                ref = data_ref_for_locator(data_registry, data_type="local_file", locator=path)
                refs.setdefault(ref["id"], ref)
                produces, consumes, _ = data_edge_labels(role)
                if produces:
                    producers.setdefault(ref["id"], set()).add(node_id)
                if consumes:
                    consumers.setdefault(ref["id"], set()).add(node_id)
            for deliverable, _ in deliverable_data_for_node(graph, node):
                ref = deliverable_data_ref(deliverable)
                refs.setdefault(ref["id"], ref)
                producers.setdefault(ref["id"], set()).add(node_id)
        streams[scope] = {
            "refs": refs,
            "producers": producers,
            "consumers": consumers,
        }
    return streams


def build_data_stream_report(
    graph: Graph,
    data_registry: dict[str, dict[str, str]] | None = None,
) -> str:
    streams = collect_data_streams(graph, data_registry)
    if not streams:
        return "_No scoped workflow data streams found._"

    consumers_by_data: dict[str, set[str]] = {}
    for scope, stream in streams.items():
        consumers = stream["consumers"]
        assert isinstance(consumers, dict)
        for data_ref, consumer_nodes in consumers.items():
            for node_id in consumer_nodes:
                consumers_by_data.setdefault(data_ref, set()).add(f"{scope}:{node_id}")

    rows: list[dict[str, str]] = []
    input_rows: list[dict[str, str]] = []
    for scope, stream in streams.items():
        refs = stream["refs"]
        producers = stream["producers"]
        consumers = stream["consumers"]
        assert isinstance(refs, dict)
        assert isinstance(producers, dict)
        assert isinstance(consumers, dict)
        produced_ids = set(producers)
        consumed_ids = set(consumers)
        for data_ref in sorted(produced_ids - consumed_ids):
            ref = refs.get(data_ref, {"id": data_ref})
            external_consumers = sorted(
                consumer for consumer in consumers_by_data.get(data_ref, set()) if not consumer.startswith(f"{scope}:")
            )
            detail = ref.get("detail") or ref.get("locator") or ref.get("location") or ""
            if external_consumers:
                hint = "cross-workflow output"
                next_action = "link cross-workflow dependency or split workflow boundary"
            elif str(data_ref).startswith("deliverable:"):
                hint = "final deliverable candidate"
                next_action = "confirm this is an intentional terminal artifact"
            else:
                hint = "missing consumer candidate"
                next_action = "add upstream use, mark terminal, or move to another workflow"
            rows.append(
                {
                    "scope": scope,
                    "data": data_ref,
                    "producer": ", ".join(sorted(producers[data_ref])),
                    "detail": detail,
                    "hint": hint,
                    "next_action": next_action,
                }
            )

        for data_ref in sorted(consumed_ids - produced_ids):
            ref = refs.get(data_ref, {"id": data_ref})
            input_rows.append(
                {
                    "scope": scope,
                    "data": data_ref,
                    "consumer": ", ".join(sorted(consumers[data_ref])),
                    "detail": ref.get("detail") or ref.get("locator") or ref.get("location") or "",
                }
            )

    by_hint: dict[str, int] = {}
    for row in rows:
        by_hint[row["hint"]] = by_hint.get(row["hint"], 0) + 1

    lines = [
        "> Generated from workflow TTL Data nodes. This report highlights supply-chain breaks that are easy to miss in Mermaid.",
        "",
        "## Summary",
        "",
        f"- Workflow scopes: {len(streams)}",
        f"- Produced but unconsumed data: {len(rows)}",
        f"- External input data: {len(input_rows)}",
    ]
    for hint, count in sorted(by_hint.items()):
        lines.append(f"- {hint}: {count}")

    lines.extend(
        [
            "",
            "## Produced But Unconsumed",
            "",
            "| Workflow | Data | Producer Task(s) | Detail | Hint | Suggested Check |",
            "|---|---|---|---|---|---|",
        ]
    )
    if rows:
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{markdown_cell(row['scope'], 32)}`",
                        f"`{markdown_cell(row['data'], 72)}`",
                        markdown_cell(row["producer"], 72),
                        markdown_cell(row["detail"], 96),
                        markdown_cell(row["hint"], 40),
                        markdown_cell(row["next_action"], 80),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | - |")

    lines.extend(
        [
            "",
            "## External Inputs",
            "",
            "| Workflow | Data | Consumer Task(s) | Detail |",
            "|---|---|---|---|",
        ]
    )
    if input_rows:
        for row in input_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{markdown_cell(row['scope'], 32)}`",
                        f"`{markdown_cell(row['data'], 72)}`",
                        markdown_cell(row["consumer"], 72),
                        markdown_cell(row["detail"], 96),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - |")

    return "\n".join(lines)


def build_workflow_topology(
    graph: Graph,
    scope: str | None = None,
    data_registry: dict[str, dict[str, str]] | None = None,
    view: str = "integrated",
) -> str:
    data_registry = data_registry or {}
    intro = "> Generated from MSO workflow TTL. Edit the TTL source, then regenerate this view."
    notes: list[str] = []
    if scope:
        intro = f"> `{view}` view for workflow scope `{scope}`. Generated from MSO workflow TTL."
        if view == "data-stream":
            notes.append("> Data stream view: `data --upstream--> task --downstream--> data` supply chain only.")
        elif view == "workflow":
            notes.append("> Workflow view: `((start)) --next--> task --next--> task --next--> ((end))` spine derived from shared Data ids where possible.")
        else:
            notes.append("> Integrated view: data stream supply chain plus the derived task workflow spine.")
    include_internal = scope is not None
    show_data_stream = include_internal and view in {"integrated", "data-stream"}
    show_workflow_spine = include_internal and view in {"integrated", "workflow"}
    lines: list[str] = [
        intro,
        *notes,
        "",
        "```mermaid",
        "flowchart LR",
    ]
    declared: set[str] = set()
    emitted_edges: set[str] = set()
    data_refs: dict[str, dict[str, str]] = {}

    def declare(
        term: URIRef,
        prefix: str,
        cls: str | None = None,
        suffix: str = "",
        shape: str = "rect",
    ) -> str:
        node_id = mermaid_id(prefix, term)
        if node_id not in declared:
            lines.append(f"  {mermaid_node(graph, term, prefix, suffix, shape)}")
            if cls:
                lines.append(f"  class {node_id} {cls}")
            declared.add(node_id)
        return node_id

    def declare_data(logical_id: str, label: str) -> str:
        node_id = data_id(logical_id)
        if node_id not in declared:
            lines.append(f'  {mermaid_shape(node_id, label, "stadium")}')
            lines.append(f"  class {node_id} data")
            declared.add(node_id)
        return node_id

    def edge(source_id: str, arrow: str, label: str, target_id: str) -> None:
        label_part = f"|{label}|" if label else ""
        line = f"  {source_id} {arrow}{label_part} {target_id}"
        if line not in emitted_edges:
            lines.append(line)
            emitted_edges.add(line)

    def declare_boundary(kind: str) -> str:
        node_id = mermaid_id(f"boundary_{kind}", f"{scope}:{kind}")
        if node_id not in declared:
            lines.append(f"  {mermaid_shape(node_id, kind, 'circle')}")
            lines.append(f"  class {node_id} boundary")
            declared.add(node_id)
        return node_id

    def visual_kind(term: URIRef) -> tuple[str, str | None, str, str]:
        for rdf_type, css_class in (
            (WF.Step, "step"),
            (WF.Decision, "decision"),
            (WF.Oracle, "oracle"),
            (WF.Validation, "validation"),
            (WF.Group, "group"),
            (WF.WorkflowRef, "workflowRef"),
        ):
            if (term, RDF.type, rdf_type) in graph:
                suffix = local_name(rdf_type)
                status = first_literal(graph, term, WF.status)
                if status:
                    suffix = f"{suffix} / {status}"
                if rdf_type == WF.Decision:
                    shape = "hexagon"
                elif rdf_type == WF.Oracle:
                    shape = "trapezoid"
                else:
                    shape = "rect"
                return local_name(rdf_type).lower(), css_class, suffix, shape
        return "node", None, "", "rect"

    phases = filter_scope(subjects_of_type(graph, WF.Phase), scope)
    if include_internal:
        for phase in phases:
            phase_id = mermaid_id("phase", phase)
            status = first_literal(graph, phase, WF.status)
            suffix = f"Phase / {status}" if status else "Phase"
            label = mermaid_node_label(graph, phase, suffix)
            if phase_id not in declared:
                lines.append(f'  subgraph {phase_id}["{label}"]')
                lines.append("    direction LR")
                declared.add(phase_id)
                for node in sorted(graph.objects(phase, WF.hasNode), key=str):
                    if isinstance(node, URIRef) and workflow_scope(node) == scope:
                        node_prefix, node_cls, node_suffix, node_shape = visual_kind(node)
                        declare(node, node_prefix, node_cls, node_suffix, node_shape)
                for ref in sorted(graph.objects(phase, WF.hasWorkflowRef), key=str):
                    if isinstance(ref, URIRef) and workflow_scope(ref) == scope:
                        declare(ref, "workflowref", "workflowRef", "WorkflowRef")
                lines.append("  end")
    else:
        for phase in phases:
            status = first_literal(graph, phase, WF.status)
            phase_cls = f"status_{status}" if status in {"completed", "active", "pending"} else "phase"
            suffix = f"Phase / {status}" if status else "Phase"
            declare(phase, "phase", phase_cls, suffix)

    if include_internal:
        node_classes = [
            (WF.Step, "step"),
            (WF.Decision, "decision"),
            (WF.Oracle, "oracle"),
            (WF.Validation, "validation"),
            (WF.Group, "group"),
            (WF.WorkflowRef, "workflowRef"),
        ]
        for cls, css_class in node_classes:
            for node in filter_scope(subjects_of_type(graph, cls), scope):
                status = first_literal(graph, node, WF.status)
                suffix = local_name(cls)
                if status:
                    suffix = f"{suffix} / {status}"
                shape = "hexagon" if cls == WF.Decision else "trapezoid" if cls == WF.Oracle else "rect"
                declare(node, local_name(cls).lower(), css_class, suffix, shape)

    for module in filter_scope(subjects_of_type(graph, WF.Module), scope):
        declare(module, "module", "module", "Module")

    for milestone in filter_scope(subjects_of_type(graph, WF.Milestone), scope):
        status = first_literal(graph, milestone, WF.status)
        suffix = f"Milestone / {status}" if status else "Milestone"
        declare(milestone, "milestone", "milestone", suffix)

    for phase in phases:
        phase_id = mermaid_id("phase", phase) if include_internal else declare(phase, "phase")
        for dep in sorted(graph.objects(phase, WF.dependsOn), key=str):
            if isinstance(dep, URIRef) and (scope is None or workflow_scope(dep) == scope):
                dep_id = mermaid_id("phase", dep) if include_internal else declare(dep, "phase")
                edge(dep_id, "-->", "dependsOn", phase_id)

    if include_internal:
        process_nodes = workflow_node_terms(graph, scope)
        control_edges: list[tuple[URIRef, str, str, URIRef]] = []
        control_incoming: set[URIRef] = set()
        control_outgoing: set[URIRef] = set()
        data_node_ids: set[str] = set()
        produced_data_node_ids: set[str] = set()
        consumed_data_node_ids: set[str] = set()
        data_producers: dict[str, set[URIRef]] = {}
        data_consumers: dict[str, set[URIRef]] = {}

        for decision in filter_scope(subjects_of_type(graph, WF.Decision), scope):
            for branch in sorted(graph.objects(decision, WF.hasBranch), key=str):
                if isinstance(branch, URIRef) and workflow_scope(branch) == scope:
                    branch_condition = first_literal(graph, branch, WF.on)
                    branch_label = f"on: {branch_condition}" if branch_condition else "goto"
                    for target in sorted(graph.objects(branch, WF.gotoNode), key=str):
                        if isinstance(target, URIRef) and workflow_scope(target) == scope:
                            control_edges.append((decision, "-.->", mermaid_label(branch_label, 32), target))
                            control_incoming.add(target)
                            control_outgoing.add(decision)

        for node in process_nodes:
            for target in sorted(graph.objects(node, WF.next), key=str):
                if isinstance(target, URIRef) and workflow_scope(target) == scope:
                    control_edges.append((node, "-->", "next", target))
                    control_incoming.add(target)
                    control_outgoing.add(node)

        if show_workflow_spine:
            for source, arrow, label, target in control_edges:
                if arrow != "-.->":
                    continue
                source_prefix, source_cls, source_suffix, source_shape = visual_kind(source)
                target_prefix, target_cls, target_suffix, target_shape = visual_kind(target)
                source_id = declare(source, source_prefix, source_cls, source_suffix, source_shape)
                target_id = declare(target, target_prefix, target_cls, target_suffix, target_shape)
                edge(source_id, arrow, label, target_id)

        for node in process_nodes:
            source_prefix, source_cls, source_suffix, source_shape = visual_kind(node)
            source_id = declare(node, source_prefix, source_cls, source_suffix, source_shape)
            for role, path, _ in directory_data_for_node(graph, node):
                ref = data_ref_for_locator(data_registry, data_type="local_file", locator=path)
                if show_data_stream:
                    data_refs.setdefault(ref["id"], ref)
                    data_node_id = declare_data(
                        ref["id"],
                        data_label(
                            ref["data_type"],
                            ref["location"],
                            node_id=ref["id"],
                            locator=ref["locator"],
                        ),
                    )
                else:
                    data_node_id = data_id(ref["id"])
                data_node_ids.add(data_node_id)
                produces, consumes, label_suffix = data_edge_labels(role)
                if produces:
                    produced_data_node_ids.add(data_node_id)
                    data_producers.setdefault(data_node_id, set()).add(node)
                    if show_data_stream:
                        edge(source_id, "-->", f"downstream{label_suffix}", data_node_id)
                if consumes:
                    consumed_data_node_ids.add(data_node_id)
                    data_consumers.setdefault(data_node_id, set()).add(node)
                    if show_data_stream:
                        edge(data_node_id, "-->", f"upstream{label_suffix}", source_id)

            for deliverable, _ in deliverable_data_for_node(graph, node):
                ref = deliverable_data_ref(deliverable)
                if show_data_stream:
                    data_refs.setdefault(ref["id"], ref)
                    data_node_id = declare_data(
                        ref["id"],
                        data_label(
                            ref["data_type"],
                            ref["location"],
                            deliverable,
                            node_id=ref["id"],
                            locator=ref["locator"],
                        ),
                    )
                else:
                    data_node_id = data_id(ref["id"])
                data_node_ids.add(data_node_id)
                produced_data_node_ids.add(data_node_id)
                data_producers.setdefault(data_node_id, set()).add(node)
                if show_data_stream:
                    edge(source_id, "-->", "downstream", data_node_id)

        stream_task_edges: set[tuple[URIRef, URIRef]] = set()
        for data_node_id in sorted(data_node_ids):
            for producer in data_producers.get(data_node_id, set()):
                for consumer in data_consumers.get(data_node_id, set()):
                    if producer != consumer:
                        stream_task_edges.add((producer, consumer))

        if not stream_task_edges:
            stream_task_edges = {
                (source, target)
                for source, arrow, label, target in control_edges
                if arrow == "-->" and label == "next"
            }

        if show_workflow_spine:
            for source, target in sorted(stream_task_edges, key=lambda pair: (str(pair[0]), str(pair[1]))):
                source_prefix, source_cls, source_suffix, source_shape = visual_kind(source)
                target_prefix, target_cls, target_suffix, target_shape = visual_kind(target)
                source_id = declare(source, source_prefix, source_cls, source_suffix, source_shape)
                target_id = declare(target, target_prefix, target_cls, target_suffix, target_shape)
                edge(source_id, "-->", "next", target_id)

        if show_workflow_spine and process_nodes:
            start_id = declare_boundary("start")
            end_id = declare_boundary("end")
            if stream_task_edges:
                spine_sources = {source for source, _ in stream_task_edges}
                spine_targets = {target for _, target in stream_task_edges}
                entry_nodes = spine_sources - spine_targets
                exit_nodes = spine_targets - spine_sources
            else:
                entry_nodes = {node for node in process_nodes if node not in control_incoming}
                exit_nodes = {node for node in process_nodes if node not in control_outgoing}

            for node in sorted(entry_nodes, key=str):
                node_prefix, node_cls, node_suffix, node_shape = visual_kind(node)
                node_id = declare(node, node_prefix, node_cls, node_suffix, node_shape)
                edge(start_id, "-->", "next", node_id)
            for node in sorted(exit_nodes, key=str):
                node_prefix, node_cls, node_suffix, node_shape = visual_kind(node)
                node_id = declare(node, node_prefix, node_cls, node_suffix, node_shape)
                edge(node_id, "-->", "next", end_id)
        elif show_workflow_spine and process_nodes:
            start_id = declare_boundary("start")
            end_id = declare_boundary("end")
            for node in process_nodes:
                node_prefix, node_cls, node_suffix, node_shape = visual_kind(node)
                node_id = declare(node, node_prefix, node_cls, node_suffix, node_shape)
                if node not in control_incoming:
                    edge(start_id, "-->", "", node_id)
                if node not in control_outgoing:
                    edge(node_id, "-->", "", end_id)

    for module in filter_scope(subjects_of_type(graph, WF.Module), scope):
        module_id = declare(module, "module")
        for dep in sorted(graph.objects(module, WF.criticalDep), key=str):
            if isinstance(dep, URIRef) and (scope is None or workflow_scope(dep) == scope):
                dep_id = declare(dep, "module")
                edge(dep_id, "-->", "criticalDep", module_id)

    for milestone in filter_scope(subjects_of_type(graph, WF.Milestone), scope):
        milestone_id = declare(milestone, "milestone")
        phase = graph.value(milestone, WF.milestoneOf)
        if isinstance(phase, URIRef) and (scope is None or workflow_scope(phase) == scope):
            phase_id = mermaid_id("phase", phase) if include_internal else declare(phase, "phase")
            edge(milestone_id, "-.->", "milestoneOf", phase_id)

    lines.extend(
        [
            "  classDef phase fill:#eef2ff,stroke:#4f46e5,color:#111827",
            "  classDef status_completed fill:#dcfce7,stroke:#16a34a,color:#111827",
            "  classDef status_active fill:#fef3c7,stroke:#d97706,color:#111827",
            "  classDef status_pending fill:#f3f4f6,stroke:#6b7280,color:#111827",
            "  classDef step fill:#ecfeff,stroke:#0891b2,color:#111827",
            "  classDef decision fill:#fae8ff,stroke:#c026d3,color:#111827",
            "  classDef oracle fill:#ffedd5,stroke:#ea580c,color:#111827",
            "  classDef validation fill:#fee2e2,stroke:#dc2626,color:#111827",
            "  classDef group fill:#f5f5f4,stroke:#78716c,color:#111827",
            "  classDef workflowRef fill:#e0f2fe,stroke:#0284c7,color:#111827",
            "  classDef module fill:#f0fdf4,stroke:#15803d,color:#111827",
            "  classDef milestone fill:#fdf2f8,stroke:#db2777,color:#111827",
            "  classDef data fill:#f8fafc,stroke:#475569,stroke-dasharray: 4 3,color:#111827",
            "  classDef boundary fill:#ffffff,stroke:#111827,color:#111827",
            "```",
        ]
    )
    if include_internal and show_data_stream and data_refs:
        lines.extend(
            [
                "",
                "## Data Node Index",
                "",
                "| Id | Type | Location | Locator | Detail |",
                "|---|---|---|---|---|",
            ]
        )
        for ref in sorted(data_refs.values(), key=lambda item: item["id"]):
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{markdown_cell(ref.get('id'), 72)}`",
                        markdown_cell(ref.get("data_type"), 24),
                        f"`{markdown_cell(ref.get('location'), 72)}`",
                        f"`{markdown_cell(ref.get('locator'), 72)}`",
                        markdown_cell(ref.get("detail"), 96),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def build_workflow_subgraph_index(
    graph: Graph,
    data_registry: dict[str, dict[str, str]] | None = None,
) -> str:
    data_registry = data_registry or {}
    scopes = workflow_scopes(graph)
    if not scopes:
        return "_No scoped workflow sub-graphs found. Regenerate TTL ABoxes with scoped workflow URIs._"

    lines = [
        "> Workflow-specific views generated from the same TTL ABox inputs as the repository topology.",
        "",
        "| Workflow Scope | Integrated | Workflow | Data Stream | Phases | Nodes | Data Nodes |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for scope in scopes:
        phase_count = len(filter_scope(subjects_of_type(graph, WF.Phase), scope))
        node_terms = workflow_node_terms(graph, scope)
        data_count = len(data_keys(graph, scope, data_registry))
        file_name = f"{scope}.md"
        lines.append(
            f"| `{scope_label(scope)}` | [`{file_name}`](workflow-subgraphs/{file_name}) | [`{file_name}`](workflow-views/{file_name}) | [`{file_name}`](data-stream-views/{file_name}) | {phase_count} | {len(node_terms)} | {data_count} |"
        )
    return "\n".join(lines)


def build_class_layer_map(graph: Graph) -> str:
    classes = sorted(
        {
            subject
            for subject in graph.subjects(RDF.type, None)
            if isinstance(subject, URIRef)
            and any((subject, RDF.type, cls_type) in graph for cls_type in CLASS_TYPES)
        },
        key=str,
    )
    if not classes:
        return "_No OWL/RDFS classes found._"

    lines = [
        "> Generated from the workflow TBox and parsed TTL files.",
        "",
        "```mermaid",
        "flowchart TB",
    ]
    declared: set[str] = set()

    def declare(cls: URIRef) -> str:
        node_id = mermaid_id("class", cls)
        if node_id not in declared:
            lines.append(f'  {node_id}["{mermaid_label(preferred_label(graph, cls))}"]')
            declared.add(node_id)
        return node_id

    for cls in classes:
        declare(cls)

    for cls in classes:
        child_id = declare(cls)
        parents = sorted(
            (parent for parent in graph.objects(cls, RDFS.subClassOf) if isinstance(parent, URIRef)),
            key=str,
        )
        for parent in parents:
            parent_id = declare(parent)
            lines.append(f"  {parent_id} -->|subClassOf| {child_id}")

    lines.extend(
        [
            "  classDef default fill:#f8fafc,stroke:#64748b,color:#111827",
            "```",
        ]
    )
    return "\n".join(lines)


def build_property_map(graph: Graph, limit: int = 140) -> str:
    properties = sorted(
        {
            subject
            for prop_type in PROPERTY_TYPES
            for subject in graph.subjects(RDF.type, prop_type)
            if isinstance(subject, URIRef)
        },
        key=str,
    )
    if not properties:
        return "_No RDF/OWL properties found._"

    lines = [
        f"> Generated property domain/range map. Showing up to {limit} edges.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    declared: set[str] = set()
    edge_count = 0

    def declare(term: URIRef, prefix: str, cls: str) -> str:
        node_id = mermaid_id(prefix, term)
        if node_id not in declared:
            lines.append(f'  {node_id}["{mermaid_label(preferred_label(graph, term))}"]')
            lines.append(f"  class {node_id} {cls}")
            declared.add(node_id)
        return node_id

    for prop in properties:
        domains = sorted(
            (domain for domain in graph.objects(prop, RDFS.domain) if isinstance(domain, URIRef)),
            key=str,
        ) or [URIRef("urn:mso:AnySubject")]
        ranges = sorted(
            (rng for rng in graph.objects(prop, RDFS.range) if isinstance(rng, URIRef)),
            key=str,
        ) or [URIRef("urn:mso:AnyValue")]

        prop_type = "datatypeProperty" if (prop, RDF.type, OWL.DatatypeProperty) in graph else "objectProperty"
        for domain in domains:
            for rng in ranges:
                if edge_count >= limit:
                    break
                domain_id = declare(domain, "domain", "classNode")
                range_cls = "literalNode" if rng in LITERAL_RANGES or str(rng).startswith(str(XSD)) else "classNode"
                range_id = declare(rng, "range", range_cls)
                label = mermaid_label(f"{preferred_label(graph, prop)} ({prop_type})", 48)
                lines.append(f"  {domain_id} -->|{label}| {range_id}")
                edge_count += 1
            if edge_count >= limit:
                break
        if edge_count >= limit:
            break

    if edge_count >= limit and len(properties) > limit:
        lines.append(f"  note_limit[\"Output truncated at {limit} edges\"]")

    lines.extend(
        [
            "  classDef classNode fill:#eef2ff,stroke:#4f46e5,color:#111827",
            "  classDef literalNode fill:#fef3c7,stroke:#d97706,color:#111827",
            "```",
        ]
    )
    return "\n".join(lines)


def build_readme(workflow_dir: Path, ttl_paths: list[Path], output_dir: Path) -> str:
    generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    rel_paths = []
    for path in ttl_paths:
        try:
            rel_paths.append(path.relative_to(workflow_dir.parent))
        except ValueError:
            rel_paths.append(path)

    inputs = "\n".join(f"- `{path}`" for path in rel_paths)
    return "\n".join(
        [
            f"> Generated at `{generated_at}`.",
            "",
            "## Views",
            "",
            "- [workflow-topology.md](workflow-topology.md) — repository-level workflow graph",
            "- [workflow-subgraph-index.md](workflow-subgraph-index.md) — workflow-specific sub-graph index",
            "- [workflow-subgraphs/](workflow-subgraphs/) — integrated workflow + data stream view per scoped workflow",
            "- [workflow-views/](workflow-views/) — task workflow spine view per scoped workflow",
            "- [data-stream-views/](data-stream-views/) — data supply-chain view per scoped workflow",
            "- [data-stream-report.md](data-stream-report.md) — produced/unconsumed data and external input checklist",
            "- [workflow-ssot-report.md](workflow-ssot-report.md)",
            "- [class-layer-map.md](class-layer-map.md)",
            "- [property-map.md](property-map.md)",
            "- [runtime-analysis.md](runtime-analysis.md)",
            "",
            "## Source TTL",
            "",
            inputs or "- _No TTL input recorded._",
            "",
            "## Regeneration",
            "",
            "Run the MSO graph observability exporter again after changing workflow TTL sources.",
            "",
            "```bash",
            "python skills/mso-graph-observability/scripts/observe_graph.py --root .",
            "```",
            "",
            f"Output directory: `{output_dir}`",
        ]
    )


def main() -> int:
    args = parse_args()
    workflow_dir, output_dir, ttl_paths = resolve_paths(args)
    project_ttl_paths = [path for path in ttl_paths if is_workflow_abox(path)]
    if not project_ttl_paths:
        print("No TTL files found. Point --workflow-dir or --ontology at workflow TTL files.", file=sys.stderr)
        return 2

    graph = parse_graph(ttl_paths)
    data_registry = load_data_registry(args.root.resolve())
    output_dir.mkdir(parents=True, exist_ok=True)
    ssot_report, missing_ttl_count = build_workflow_ssot_report(workflow_dir)

    write_markdown(output_dir / "workflow-topology.md", "MSO Repository Workflow Topology", build_workflow_topology(graph, data_registry=data_registry))
    write_markdown(output_dir / "workflow-subgraph-index.md", "MSO Workflow Sub-Graph Index", build_workflow_subgraph_index(graph, data_registry=data_registry))
    write_markdown(output_dir / "data-stream-report.md", "MSO Data Stream Report", build_data_stream_report(graph, data_registry=data_registry))
    for scope in workflow_scopes(graph):
        write_markdown(
            output_dir / "workflow-subgraphs" / f"{scope}.md",
            f"MSO Integrated Workflow View — {scope_label(scope)}",
            build_workflow_topology(graph, scope=scope, data_registry=data_registry, view="integrated"),
        )
        write_markdown(
            output_dir / "workflow-views" / f"{scope}.md",
            f"MSO Workflow View — {scope_label(scope)}",
            build_workflow_topology(graph, scope=scope, data_registry=data_registry, view="workflow"),
        )
        write_markdown(
            output_dir / "data-stream-views" / f"{scope}.md",
            f"MSO Data Stream View — {scope_label(scope)}",
            build_workflow_topology(graph, scope=scope, data_registry=data_registry, view="data-stream"),
        )
    write_markdown(output_dir / "workflow-ssot-report.md", "MSO Workflow SSOT Report", ssot_report)
    write_markdown(output_dir / "class-layer-map.md", "MSO Workflow Class Layer Map", build_class_layer_map(graph))
    write_markdown(output_dir / "property-map.md", "MSO Workflow Property Map", build_property_map(graph))
    write_markdown(output_dir / "runtime-analysis.md", "MSO Runtime Graph Analysis", build_runtime_analysis(args.root.resolve()))
    write_markdown(output_dir / "README.md", "MSO Graph Observability Views", build_readme(workflow_dir, ttl_paths, output_dir))

    print(f"Wrote graph observability views to {output_dir}")
    if missing_ttl_count:
        print(
            f"WARNING: {missing_ttl_count} workflow YAML file(s) have no sibling *.abox.ttl and were excluded from topology. See workflow-ssot-report.md.",
            file=sys.stderr,
        )
        if args.strict_ssot:
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
