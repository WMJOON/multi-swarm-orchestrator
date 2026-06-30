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
import shutil
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
ARTIFACT_TYPES = {
    "knowledge_store",
    "event_store",
    "local_database",
    "document",
    "media",
    "tool",
    "table",
}
ARTIFACT_LABELS = {
    "knowledge_store": "KNOWLEDGE STORE",
    "event_store": "EVENT STORE",
    "local_database": "LOCAL DATABASE",
    "document": "DOCUMENT",
    "media": "MEDIA",
    "tool": "TOOL",
    "table": "TABLE",
}
ARTIFACT_PRIMARY_CONSUMERS = {
    "knowledge_store": "Agent",
    "event_store": "Agent",
    "local_database": "Agent",
    "document": "Human + Agent",
    "media": "Human",
    "tool": "Agent + Eval",
    "table": "Tool + Agent",
}
MACHINE_NATIVE_ARTIFACTS = {"knowledge_store", "event_store", "local_database", "table"}
KNOWLEDGE_STORE_MARKERS = {
    "ontology",
    "schema",
    "embedding",
    "api",
    "mcp",
    "graph",
    "rdf",
    "owl",
    "shacl",
    "ttl",
    "tbox",
    "abox",
    "workflow",
    "visual-dom",
    "catalog",
}
EVENT_STORE_MARKERS = {
    "work-memory",
    "work_memory",
    "auditlog",
    "audit-log",
    "worklog",
    "work-log",
    "event",
    "jsonl",
}
LOCAL_DATABASE_MARKERS = {
    "database",
    "sqlite",
    "duckdb",
    "cache.db",
    ".db",
}
MEDIA_EXTENSIONS = {
    ".html",
    ".pdf",
    ".pptx",
    ".png",
    ".svg",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp4",
}
TOOL_ARTIFACT_MARKERS = {
    "[[process]]",
    "[[tool]]",
    "engine process",
    "nlu engine process",
    "processing artifact",
    "tool use",
}
TABLE_MARKERS = {
    "table:",
    "sqlite_table:",
    "db_table:",
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
        help="Exit non-zero when legacy workflow YAML files remain after TTL migration.",
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


def is_legacy_workflow_yaml(path: Path, workflow_dir: Path) -> bool:
    if not path.is_file() or path.suffix != ".yaml":
        return False
    if path.name.endswith(".schema.yaml"):
        return False
    try:
        rel = path.relative_to(workflow_dir)
    except ValueError:
        return False
    if len(rel.parts) != 1:
        return False
    return path.name.startswith("workflow-")


def default_output_dir(root: Path, workflow_dir: Path) -> Path:
    agent_context = root / "agent-context"
    if agent_context.exists():
        return agent_context / "observability" / "graph"
    return workflow_dir / "observability"


def workflow_ssot_state(workflow_dir: Path) -> dict[str, list[Path]]:
    yaml_paths = sorted(
        p
        for p in workflow_dir.rglob("*.yaml")
        if is_legacy_workflow_yaml(p, workflow_dir)
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


def legacy_yaml_refs_in_graph(graph: Graph) -> list[str]:
    refs: set[str] = set()
    for value in graph.objects(None, WF.ref):
        if not isinstance(value, Literal):
            continue
        text = literal_text(value).strip()
        path_part = text.split("#", 1)[0]
        if path_part.endswith((".yaml", ".yml")):
            refs.add(text)
    return sorted(refs)


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


def _contains_any(text: str, markers: set[str]) -> bool:
    return any(marker in text for marker in markers)


def is_tool_artifact_ref(text: str) -> bool:
    haystack = text.lower()
    return _contains_any(haystack, TOOL_ARTIFACT_MARKERS) or bool(
        re.search(r"\[\[[^\]]*(process|tool|processing artifact)[^\]]*\]\]", haystack)
    )


def artifact_type_from_resource_kind(
    resource_kind: str | None,
    haystack: str,
) -> str | None:
    kind = (resource_kind or "").strip().lower()
    if kind == "data":
        if _contains_any(haystack, EVENT_STORE_MARKERS):
            return "event_store"
        if _contains_any(haystack, LOCAL_DATABASE_MARKERS):
            return "local_database"
        return "knowledge_store"
    if kind == "file":
        suffix = Path(haystack.split()[0] if haystack.split() else "").suffix.lower()
        if suffix in MEDIA_EXTENSIONS or _contains_any(haystack, MEDIA_EXTENSIONS):
            return "media"
        return "document"
    return None


def infer_artifact_type(
    *,
    data_type: str,
    locator: str,
    source: str = "",
    explicit: str | None = None,
    resource_kind: str | None = None,
    role: str | None = None,
    artifact_id: str | None = None,
    detail: str | None = None,
) -> str:
    explicit_norm = (explicit or "").strip().lower()
    if explicit_norm in ARTIFACT_TYPES:
        return explicit_norm

    data_type_norm = (data_type or "local_file").strip().lower()
    haystack = " ".join(
        [
            artifact_id or "",
            locator or "",
            source or "",
            role or "",
            detail or "",
        ]
    ).lower()
    legacy = artifact_type_from_resource_kind(resource_kind, haystack)
    if legacy:
        return legacy

    if data_type_norm == "database":
        return "local_database"
    if any(str(part or "").lower().startswith(marker) for part in (locator, artifact_id, detail) for marker in TABLE_MARKERS):
        return "table"
    if "#" in haystack and _contains_any(haystack, LOCAL_DATABASE_MARKERS | {"sqlite", ".db"}):
        return "table"
    if data_type_norm in {"api", "mcp", "object_store", "external_url"}:
        return "knowledge_store"
    if _contains_any(haystack, LOCAL_DATABASE_MARKERS):
        return "local_database"
    if _contains_any(haystack, EVENT_STORE_MARKERS):
        return "event_store"
    if _contains_any(haystack, KNOWLEDGE_STORE_MARKERS):
        return "knowledge_store"
    if is_tool_artifact_ref(haystack):
        return "tool"
    if any(ext in haystack for ext in MEDIA_EXTENSIONS):
        return "media"
    return "document"


def infer_resource_kind(
    **kwargs: str | None,
) -> str:
    artifact_type = infer_artifact_type(**kwargs)
    return "data" if artifact_type in MACHINE_NATIVE_ARTIFACTS else "file"


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
    artifact_type: str | None = None,
    resource_kind: str | None = None,
    role: str | None = None,
) -> None:
    locator_norm = normalize_locator(locator)
    if not data_id_value or not locator_norm:
        return
    ref = {
        "id": data_id_value,
        "data_type": data_type or "local_file",
        "artifact_type": infer_artifact_type(
            data_type=data_type or "local_file",
            locator=locator_norm,
            source=source,
            explicit=artifact_type,
            resource_kind=resource_kind,
            role=role,
            artifact_id=data_id_value,
        ),
        "resource_kind": infer_resource_kind(
            data_type=data_type or "local_file",
            locator=locator_norm,
            source=source,
            explicit=artifact_type,
            resource_kind=resource_kind,
            role=role,
            artifact_id=data_id_value,
        ),
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
        artifact_type = str(item.get("artifact_type") or item.get("artifact_kind") or "").strip()
        resource_kind = str(item.get("resource_kind") or item.get("kind") or "").strip()
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
            artifact_type=artifact_type,
            resource_kind=resource_kind,
            role=str(item.get("role") or "").strip(),
        )

    for module in doc.get("modules", []) or []:
        if not isinstance(module, dict):
            continue
        # skip planned/inactive modules — their dirs pollute suffix-match results
        module_status = str(module.get("status") or "active").strip().lower()
        if module_status not in ("active", ""):
            continue
        module_id = str(module.get("id") or "").strip()
        module_path = str(module.get("path") or "").strip()
        register_data_ref(
            registry,
            data_id_value=module_id,
            data_type=str(module.get("data_type") or "local_file"),
            locator=module_path,
            source="module",
            artifact_type=str(module.get("artifact_type") or module.get("artifact_kind") or "").strip(),
            resource_kind=str(module.get("resource_kind") or module.get("kind") or "").strip(),
            role=str(module.get("role") or "").strip(),
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
                artifact_type=str(subdir.get("artifact_type") or subdir.get("artifact_kind") or "").strip(),
                resource_kind=str(subdir.get("resource_kind") or subdir.get("kind") or "").strip(),
                role=str(subdir.get("role") or "").strip(),
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
    if shape == "database":
        return f'{node_id}[("{label}")]'
    if shape == "document":
        return f'{node_id}@{{ shape: doc, label: "{label}" }}'
    if shape == "hexagon":
        return f'{node_id}{{{{"{label}"}}}}'
    if shape == "trapezoid":
        return f'{node_id}[/"{label}"/]'
    if shape == "subroutine":
        return f'{node_id}[["{label}"]]'
    return f'{node_id}["{label}"]'


def mermaid_node_label(graph: Graph, term: URIRef, suffix: str = "") -> str:
    label = preferred_label(graph, term)
    node_id = display_id(term)
    parts = [label]
    if node_id and node_id != label:
        parts.append(f"id: {node_id}")
    if suffix:
        parts.append(suffix)
    return "<br>".join(mermaid_label(p, 140) for p in parts)


def mermaid_node(graph: Graph, term: URIRef, prefix: str, suffix: str = "", shape: str = "rect") -> str:
    node_id = mermaid_id(prefix, term)
    label = mermaid_node_label(graph, term, suffix)
    return mermaid_shape(node_id, label, shape)


def subjects_of_type(graph: Graph, cls: URIRef) -> list[URIRef]:
    return sorted(
        (subject for subject in graph.subjects(RDF.type, cls) if isinstance(subject, URIRef)),
        key=str,
    )


def process_units(graph: Graph) -> list[URIRef]:
    # v0.6.1 phase-less: process unit = workflow/sub-workflow.
    # legacy wf:Phase 는 읽기 호환으로만 포함한다.
    units = list(subjects_of_type(graph, WF.Phase))
    seen = set(units)
    for o in graph.objects(None, WF.has_subWorkflow):
        if isinstance(o, URIRef) and o not in seen:
            seen.add(o)
            units.append(o)
    return sorted(units, key=str)


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


def build_workflow_ssot_report(workflow_dir: Path, graph: Graph | None = None) -> tuple[str, int]:
    state = workflow_ssot_state(workflow_dir)
    removal_candidates = state["yaml_with_abox"]
    migration_blockers = state["yaml_without_abox"]
    legacy_refs = legacy_yaml_refs_in_graph(graph) if graph is not None else []

    def list_paths(paths: list[Path]) -> str:
        if not paths:
            return "- _None._"
        return "\n".join(f"- `{rel_path(path, workflow_dir)}`" for path in paths)

    def list_refs(refs: list[str]) -> str:
        if not refs:
            return "- _None._"
        return "\n".join(f"- `{ref}`" for ref in refs)

    body = "\n".join(
        [
            "> Workflow observability uses TTL ABox files only. Legacy workflow YAML is a one-time migration input, not a topology source. After migration, remove the YAML.",
            "",
            "## Summary",
            "",
            f"- Legacy workflow YAML files remaining: {len(state['yaml'])}",
            f"- TTL ABox workflow files: {len(state['abox'])}",
            f"- Legacy YAML ready to remove (sibling TTL exists): {len(removal_candidates)}",
            f"- Migration blockers (legacy YAML without sibling TTL): {len(migration_blockers)}",
            f"- Legacy YAML references inside TTL: {len(legacy_refs)}",
            f"- TTL ABox files without legacy YAML source: {len(state['abox_without_yaml'])}",
            "",
            "## Legacy Workflow YAML Ready To Remove",
            "",
            list_paths(removal_candidates),
            "",
            "## Migration Blockers: Legacy YAML Without TTL",
            "",
            list_paths(migration_blockers),
            "",
            "## Legacy YAML References Inside TTL",
            "",
            list_refs(legacy_refs),
            "",
            "## TTL ABox Inputs Used For Workflow Topology",
            "",
            list_paths(state["abox"]),
            "",
            "## TTL-Only Policy",
            "",
            "1. Import any remaining legacy workflow YAML into sibling `.abox.ttl` files.",
            "2. Verify the generated TTL with the workflow validator.",
            "3. Update `wf:ref` links so TTL points to TTL or stable graph identifiers, not YAML files.",
            "4. Remove the migrated legacy YAML. Do not edit YAML or regenerate YAML from TTL.",
            "",
            "```bash",
            "python skills/mso-workflow-design/scripts/migrate_workflows_to_ttl.py agent-context/workflow",
            "```",
        ]
    )
    return body, len(state["yaml"]) + len(legacy_refs)


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
        for cls in (WF.Phase, WF.Step, WF.Decision, WF.Eval, WF.Group)
        for subject in subjects_of_type(graph, cls)
        for scope in [workflow_scope(subject)]
        if scope
    }
    return sorted(scopes)


def scope_label(scope: str) -> str:
    return scope.replace("_", "-")


def scope_dir_name(scope: str) -> str:
    label = scope_label(scope).strip()
    return re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-") or "workflow"


def filter_scope(terms: Iterable[URIRef], scope: str | None) -> list[URIRef]:
    if scope is None:
        return list(terms)
    return [term for term in terms if workflow_scope(term) == scope]


def workflow_node_terms(graph: Graph, scope: str | None = None) -> list[URIRef]:
    node_terms = {
        node
        for cls in (WF.Step, WF.Decision, WF.Eval, WF.Group)
        for node in subjects_of_type(graph, cls)
    }
    return filter_scope(sorted(node_terms, key=str), scope)


def build_oracle_view(graph: Graph) -> str:
    """Oracle layer view (v0.6.0 SPEC §3.3 축 A): evolves/exercises/has_subWorkflow/
    target edge-필터 subgraph. base(delegatesTo/produces/check/next)와 분리된 관점."""
    lines = ["```mermaid", "flowchart TD"]
    seen: set[str] = set()

    def emit(s: URIRef, label: str, o: URIRef) -> None:
        sid, oid = mermaid_id("o", s), mermaid_id("o", o)
        for term, nid in ((s, sid), (o, oid)):
            if nid not in seen:
                seen.add(nid)
                lines.append(f'    {nid}["{mermaid_label(preferred_label(graph, term))}"]')
        lines.append(f"    {sid} -->|{label}| {oid}")

    for pred, label in ((WF.has_subWorkflow, "has_subWorkflow"), (WF.evolves, "evolves"),
                        (WF.exercises, "exercises"), (WF.target, "target")):
        for s, o in graph.subject_objects(pred):
            emit(s, label, o)
    if not seen:
        lines.append("    %% (no oracle edges)")
    lines.append("```")
    return "\n".join(lines)


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
    artifact_type: str = "document",
) -> str:
    type_label = ARTIFACT_LABELS.get(artifact_type, artifact_type.upper())
    # 사람이 읽을 수 있는 이름: detail(deliverable 설명) > locator(파일 경로) > id 접두사 제거
    if detail:
        name = detail
    elif locator:
        name = locator
    elif node_id:
        name = node_id.removeprefix("local_file:").removeprefix("index:").removeprefix("deliverable:")
    else:
        name = location
    if artifact_type == "table" and "#" in name:
        db_path, table_name = name.rsplit("#", 1)
        db_name = db_path.rstrip("/").rsplit("/", 1)[-1] or db_path
        name = f"{db_name}#{table_name}"
    parts = [mermaid_label(name, 52), type_label]
    return "<br>".join(p for p in parts if p)


def enrich_artifact_ref(ref: dict[str, str], *, data_type: str, locator: str) -> dict[str, str]:
    ref_data_type = ref.get("data_type", data_type)
    artifact_type = ref.get("artifact_type") or infer_artifact_type(
        data_type=ref_data_type,
        locator=ref.get("locator", locator),
        source=ref.get("source", ""),
        resource_kind=ref.get("resource_kind"),
        artifact_id=ref["id"],
        detail=ref.get("detail"),
    )
    resource_kind = ref.get("resource_kind") or ("data" if artifact_type in MACHINE_NATIVE_ARTIFACTS else "file")
    enriched = dict(ref)
    enriched["data_type"] = ref_data_type
    enriched["artifact_type"] = artifact_type
    enriched["resource_kind"] = resource_kind
    enriched["primary_consumer"] = ARTIFACT_PRIMARY_CONSUMERS.get(artifact_type, "-")
    return enriched


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
            enriched = enrich_artifact_ref(ref, data_type=data_type, locator=normalize_locator(locator))
            return {
                "key": f"index:{enriched['id']}",
                "id": enriched["id"],
                "data_type": enriched["data_type"],
                "artifact_type": enriched["artifact_type"],
                "resource_kind": enriched["resource_kind"],
                "primary_consumer": enriched["primary_consumer"],
                "location": f"index:{enriched['id']}",
                "locator": enriched.get("locator", normalize_locator(locator)),
            }
    explicit_type = infer_artifact_type(
        data_type=data_type,
        locator=normalized,
        artifact_id=f"{data_type}:{normalized}",
    )
    if explicit_type == "table":
        fallback_id = f"{data_type}:{normalized}"
        return {
            "key": fallback_id,
            "id": fallback_id,
            "data_type": data_type,
            "artifact_type": explicit_type,
            "resource_kind": "data",
            "primary_consumer": ARTIFACT_PRIMARY_CONSUMERS.get(explicit_type, "-"),
            "location": normalized,
            "locator": normalized,
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
        enriched = enrich_artifact_ref(prefix_ref, data_type=data_type, locator=normalized)
        return {
            "key": f"index:{enriched['id']}",
            "id": enriched["id"],
            "data_type": enriched["data_type"],
            "artifact_type": enriched["artifact_type"],
            "resource_kind": enriched["resource_kind"],
            "primary_consumer": enriched["primary_consumer"],
            "location": f"index:{enriched['id']}",
            "locator": enriched.get("locator", normalized),
        }
    # Suffix match: TTL may store module-relative paths (e.g. "data/") while
    # the index registers root-relative paths (e.g. "04.modules/.../data/").
    # Pick the longest registry locator that ends with the query locator.
    suffix_ref: dict[str, str] | None = None
    suffix_match_len = -1
    for ref in data_registry.values():
        ref_locator = ref.get("locator", "")
        if not ref_locator:
            continue
        norm_ref = normalize_locator(ref_locator)
        if norm_ref.endswith(normalized) and len(norm_ref) > len(normalized):
            if len(norm_ref) > suffix_match_len:
                suffix_ref = ref
                suffix_match_len = len(norm_ref)
    if suffix_ref:
        enriched = enrich_artifact_ref(suffix_ref, data_type=data_type, locator=normalized)
        return {
            "key": f"index:{enriched['id']}",
            "id": enriched["id"],
            "data_type": enriched["data_type"],
            "artifact_type": enriched["artifact_type"],
            "resource_kind": enriched["resource_kind"],
            "primary_consumer": enriched["primary_consumer"],
            "location": f"index:{enriched['id']}",
            "locator": enriched.get("locator", normalized),
        }
    fallback_id = f"{data_type}:{normalized}"
    artifact_type = infer_artifact_type(
        data_type=data_type,
        locator=normalized,
        artifact_id=fallback_id,
    )
    return {
        "key": fallback_id,
        "id": fallback_id,
        "data_type": data_type,
        "artifact_type": artifact_type,
        "resource_kind": "data" if artifact_type in MACHINE_NATIVE_ARTIFACTS else "file",
        "primary_consumer": ARTIFACT_PRIMARY_CONSUMERS.get(artifact_type, "-"),
        "location": normalized,
        "locator": normalized,
    }


def deliverable_data_ref(deliverable: str) -> dict[str, str]:
    digest = hashlib.sha1(deliverable.encode("utf-8")).hexdigest()[:10]
    key = f"deliverable:{digest}"
    artifact_type = infer_artifact_type(
        data_type="local_file",
        locator="",
        artifact_id=key,
        detail=deliverable,
    )
    return {
        "key": key,
        "id": key,
        "data_type": "local_file",
        "artifact_type": artifact_type,
        "resource_kind": "data" if artifact_type in MACHINE_NATIVE_ARTIFACTS else "file",
        "primary_consumer": ARTIFACT_PRIMARY_CONSUMERS.get(artifact_type, "-"),
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


def has_supply_chain(graph: Graph, node: URIRef) -> bool:
    """artifact-stream 뷰에 표시할 공급망 연결이 있는지 확인.
    wf:directory 또는 wf:deliverables 또는 eval targetArtifact 중 하나라도 있으면 True."""
    for directory in graph.objects(node, WF.directory):
        role_value = graph.value(directory, WF.dirRole)
        role = literal_text(role_value) if isinstance(role_value, Literal) else "reference"
        produces, consumes, _ = data_edge_labels(role)
        if produces or consumes:
            return True
    if list(graph.objects(node, WF.deliverables)):
        return True
    if graph.value(node, WF.targetArtifact) is not None:
        return True
    if graph.value(node, WF.usesTool) is not None:
        return True
    return False


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
        for role, path, _ in directory_data_for_node(graph, node):
            produces, consumes, _ = data_edge_labels(role)
            if not produces and not consumes:
                continue
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
                produces, consumes, _ = data_edge_labels(role)
                if not produces and not consumes:
                    continue
                refs.setdefault(ref["id"], ref)
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
        return "_No scoped workflow artifact streams found._"

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
            artifact_type = str(ref.get("artifact_type") or "document")
            external_consumers = sorted(
                consumer for consumer in consumers_by_data.get(data_ref, set()) if not consumer.startswith(f"{scope}:")
            )
            detail = ref.get("detail") or ref.get("locator") or ref.get("location") or ""
            if external_consumers:
                hint = f"cross-workflow {artifact_type} artifact"
                next_action = "link the downstream consumer workflow or split the artifact boundary intentionally"
            elif artifact_type in MACHINE_NATIVE_ARTIFACTS:
                hint = f"missing agent consumer for {artifact_type}"
                next_action = "add an agent consumer task, mark as external artifact output, or move it to a workflow that reads it"
            elif artifact_type == "media":
                hint = "terminal media deliverable candidate"
                next_action = "confirm a human review/delivery consumer exists, otherwise skip the artifact"
            else:
                hint = "terminal/review document candidate"
                next_action = "confirm agent/user consumer; else omit or convert to jsonl/ttl/sqlite"
            rows.append(
                {
                    "scope": scope,
                    "artifact_type": artifact_type,
                    "primary_consumer": ref.get("primary_consumer") or ARTIFACT_PRIMARY_CONSUMERS.get(artifact_type, "-"),
                    "artifact": data_ref,
                    "producer": ", ".join(sorted(producers[data_ref])),
                    "detail": detail,
                    "hint": hint,
                    "next_action": next_action,
                }
            )

        for data_ref in sorted(consumed_ids - produced_ids):
            ref = refs.get(data_ref, {"id": data_ref})
            artifact_type = str(ref.get("artifact_type") or "document")
            input_rows.append(
                {
                    "scope": scope,
                    "artifact_type": artifact_type,
                    "primary_consumer": ref.get("primary_consumer") or ARTIFACT_PRIMARY_CONSUMERS.get(artifact_type, "-"),
                    "artifact": data_ref,
                    "consumer": ", ".join(sorted(consumers[data_ref])),
                    "detail": ref.get("detail") or ref.get("locator") or ref.get("location") or "",
                    "hint": f"external input ({artifact_type})",
                }
            )

    by_hint: dict[str, int] = {}
    for row in rows:
        by_hint[row["hint"]] = by_hint.get(row["hint"], 0) + 1
    output_by_type = Counter(row["artifact_type"] for row in rows)
    input_by_type = Counter(row["artifact_type"] for row in input_rows)

    lines = [
        "> Generated from workflow TTL Artifact nodes. This report highlights supply-chain breaks that are easy to miss in Mermaid.",
        "",
        "## Summary",
        "",
        f"- Workflow scopes: {len(streams)}",
        f"- Produced but unconsumed artifacts: {len(rows)}",
        f"- External input artifacts: {len(input_rows)}",
    ]
    for artifact_type in sorted(ARTIFACT_TYPES):
        lines.append(f"- Produced but unconsumed {artifact_type}: {output_by_type.get(artifact_type, 0)}")
    for artifact_type in sorted(ARTIFACT_TYPES):
        lines.append(f"- External input {artifact_type}: {input_by_type.get(artifact_type, 0)}")
    for hint, count in sorted(by_hint.items()):
        lines.append(f"- {hint}: {count}")

    lines.extend(
        [
            "",
            "## Consumer Fit Heuristic",
            "",
            "- Review the visualized workflow topology to decide whether each produced Artifact has a suitable consumer.",
            "- For `document` artifacts such as Markdown, confirm an Agent or Human review/handoff/eval consumer exists in the workflow.",
            "- If a document has no consumer, omit it. If the content must be retrieved, queried, replayed, or reasoned over later, prefer `event_store` JSONL, `knowledge_store` TTL/schema, or `local_database` SQLite instead.",
            "- Directory creation follows the workflow and artifact supply chain. Do not preserve directories that do not serve an Artifact consumer.",
            "",
            "## Produced But Unconsumed",
            "",
            "| Workflow | Artifact Type | Primary Consumer | Artifact | Producer Task(s) | Detail | Hint | Suggested Check |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    if rows:
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{markdown_cell(row['scope'], 32)}`",
                        markdown_cell(row["artifact_type"], 18),
                        markdown_cell(row["primary_consumer"], 18),
                        f"`{markdown_cell(row['artifact'], 72)}`",
                        markdown_cell(row["producer"], 72),
                        markdown_cell(row["detail"], 96),
                        markdown_cell(row["hint"], 40),
                        markdown_cell(row["next_action"], 80),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - |")

    lines.extend(
        [
            "",
            "## External Inputs",
            "",
            "| Workflow | Artifact Type | Primary Consumer | Artifact | Consumer Task(s) | Detail | Hint |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    if input_rows:
        for row in input_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{markdown_cell(row['scope'], 32)}`",
                        markdown_cell(row["artifact_type"], 18),
                        markdown_cell(row["primary_consumer"], 18),
                        f"`{markdown_cell(row['artifact'], 72)}`",
                        markdown_cell(row["consumer"], 72),
                        markdown_cell(row["detail"], 96),
                        markdown_cell(row["hint"], 40),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - |")

    return "\n".join(lines)


def build_resource_stream_report(
    graph: Graph,
    data_registry: dict[str, dict[str, str]] | None = None,
) -> str:
    return build_data_stream_report(graph, data_registry)


def build_artifact_stream_report(
    graph: Graph,
    data_registry: dict[str, dict[str, str]] | None = None,
) -> str:
    return build_data_stream_report(graph, data_registry)


def build_process_map(
    graph: Graph,
    data_registry: dict[str, dict[str, str]] | None = None,
) -> str:
    """Workflow/sub-workflow process map: [['scope<br>workflow']] subroutine nodes + shared artifact cylinders.

    Shows only cross-scope artifacts and machine-native (local_database/event_store/knowledge_store)
    artifacts. Deliverable free-text nodes are intentionally excluded — they have no stable id and
    fragment the supply chain view.
    """
    data_registry = data_registry or {}

    # --- Workflow → Node reverse mapping (via wf:hasNode) ---
    step_to_phase: dict[str, str] = {}
    for phase in process_units(graph):
        for step in graph.objects(phase, WF.hasNode):
            if isinstance(step, URIRef):
                step_to_phase[str(step)] = str(phase)

    phases = process_units(graph)
    if not phases:
        return "_No wf:Workflow process units found in TTL. Add workflows[] to your workflow ABox to generate a process map._"

    phase_scope_map: dict[str, str] = {}
    phase_label_map: dict[str, str] = {}
    phase_node_ids: dict[str, str] = {}
    for phase in phases:
        scope = workflow_scope(phase)
        if not scope:
            continue
        pstr = str(phase)
        phase_scope_map[pstr] = scope
        phase_label_map[pstr] = preferred_label(graph, phase) or display_id(phase)
        phase_node_ids[pstr] = mermaid_id("proc", phase)

    # --- Collect artifact refs per workflow (aggregate from all nodes in that workflow) ---
    node_types = (WF.Step, WF.Decision, WF.Eval, WF.Group)
    all_nodes = [n for cls in node_types for n in subjects_of_type(graph, cls)]

    all_refs: dict[str, dict[str, str]] = {}
    phase_arts: dict[str, dict[str, tuple[bool, bool]]] = {}  # pstr → {aid: (produces, consumes)}

    for node in all_nodes:
        nstr = str(node)
        pstr = step_to_phase.get(nstr)
        if not pstr:
            scope = workflow_scope(node)
            if scope:
                candidates = [p for p, s in phase_scope_map.items() if s == scope]
                if len(candidates) == 1:
                    pstr = candidates[0]
        if not pstr:
            continue

        for role, path, _ in directory_data_for_node(graph, node):
            ref = data_ref_for_locator(data_registry, data_type="local_file", locator=path)
            all_refs.setdefault(ref["id"], ref)
            produces, consumes, _ = data_edge_labels(role)
            prev = phase_arts.setdefault(pstr, {}).get(ref["id"], (False, False))
            phase_arts[pstr][ref["id"]] = (prev[0] or produces, prev[1] or consumes)

        for deliverable, _ in deliverable_data_for_node(graph, node):
            ref = deliverable_data_ref(deliverable)
            all_refs.setdefault(ref["id"], ref)
            prev = phase_arts.setdefault(pstr, {}).get(ref["id"], (False, False))
            phase_arts[pstr][ref["id"]] = (True, prev[1])

    # --- Decide which artifacts to display ---
    artifact_scope_set: dict[str, set[str]] = {}
    for pstr, arts in phase_arts.items():
        scope = phase_scope_map.get(pstr, "")
        for aid in arts:
            artifact_scope_set.setdefault(aid, set()).add(scope)

    cross_scope = {aid for aid, scopes in artifact_scope_set.items() if len(scopes) > 1}
    machine_native = {
        aid for aid, ref in all_refs.items()
        if ref.get("artifact_type") in MACHINE_NATIVE_ARTIFACTS
    }
    display_aids = (cross_scope | machine_native) - {
        aid for aid in all_refs if aid.startswith("deliverable:")
    }

    # --- Build Mermaid ---
    lines: list[str] = ["flowchart LR", ""]

    artifact_nids: dict[str, str] = {}
    for aid in sorted(display_aids):
        ref = all_refs.get(aid, {})
        atype = ref.get("artifact_type", "document")
        shape = "database" if atype in MACHINE_NATIVE_ARTIFACTS else "document"
        a_nid = data_id(aid)
        artifact_nids[aid] = a_nid
        label = data_label(
            ref.get("data_type", "local_file"),
            ref.get("location", aid),
            artifact_type=atype,
            node_id=aid,
        )
        lines.append(f"  {mermaid_shape(a_nid, label, shape)}")
    lines.append("")

    scopes_ordered = list(dict.fromkeys(
        phase_scope_map.get(str(p), "") for p in phases
        if phase_scope_map.get(str(p))
    ))
    for scope in scopes_ordered:
        sg_id = re.sub(r"[^A-Za-z0-9_]", "_", scope)
        lines.append(f"  subgraph {sg_id}[{scope_label(scope)}]")
        for phase in phases:
            pstr = str(phase)
            if phase_scope_map.get(pstr) != scope:
                continue
            nid = phase_node_ids.get(pstr, "")
            if not nid:
                continue
            plabel = f"{scope_label(scope)}<br>{mermaid_label(phase_label_map.get(pstr, ''), 36)}"
            lines.append(f'    {mermaid_shape(nid, plabel, "subroutine")}')
        lines.append("  end")
        lines.append("")

    for pstr, arts in sorted(phase_arts.items()):
        p_nid = phase_node_ids.get(pstr, "")
        if not p_nid:
            continue
        for aid, (produces, consumes) in sorted(arts.items()):
            if aid not in display_aids:
                continue
            a_nid = artifact_nids.get(aid, "")
            if not a_nid:
                continue
            if produces:
                lines.append(f"  {p_nid} -.->|produces| {a_nid}")
            if consumes:
                lines.append(f"  {a_nid} -.->|consumes| {p_nid}")

    if not artifact_nids and not phase_node_ids:
        return "_No displayable process nodes or shared artifacts found._"

    body = "\n".join(lines)
    return f"> Workflow/sub-workflow process map. Each `[[...]]` node is a workflow process unit; cylinders are shared machine-native artifacts.\n\n```mermaid\n{body}\n```"


def _sort_steps_by_next_chain(graph: Graph, steps: list[URIRef]) -> list[URIRef]:
    if not steps:
        return steps
    step_strs = {str(s): s for s in steps}
    next_map: dict[str, str] = {}
    for step in steps:
        for nxt in graph.objects(step, WF.next):
            if isinstance(nxt, URIRef) and str(nxt) in step_strs:
                next_map[str(step)] = str(nxt)
    pointed_to = set(next_map.values())
    starts = [s for s in steps if str(s) not in pointed_to]
    if not starts:
        return steps
    result: list[URIRef] = []
    current: str | None = str(starts[0])
    visited: set[str] = set()
    while current and current not in visited:
        visited.add(current)
        node = step_strs.get(current)
        if node:
            result.append(node)
        current = next_map.get(current)
    for s in steps:
        if str(s) not in visited:
            result.append(s)
    return result


def build_process_flow(
    graph: Graph,
    scope: str,
    data_registry: dict[str, dict[str, str]] | None = None,
) -> str:
    """Internal flow view for one workflow scope.

    Workflows are boxed subgraphs with nodes inside. Workflow sequence follows URI order
    (or wf:order when available). Local-database artifacts are shown as cylinders.
    """
    data_registry = data_registry or {}

    phases = [p for p in process_units(graph) if workflow_scope(p) == scope]
    if not phases:
        return f"_No `wf:Workflow` process units found for scope `{scope}`._"

    def phase_sort_key(p: URIRef) -> tuple[int, str]:
        order_val = graph.value(p, WF.order)
        if isinstance(order_val, Literal):
            try:
                return (int(str(order_val)), "")
            except ValueError:
                pass
        local = display_id(p)
        m = re.match(r"(?:phase[-_])?(\d+)", local)
        return (int(m.group(1)), local) if m else (999, local)

    phases_sorted = sorted(phases, key=phase_sort_key)

    # --- Workflow → Nodes ---
    phase_steps: dict[str, list[URIRef]] = {}
    step_to_phase: dict[str, str] = {}
    for phase in phases_sorted:
        raw_steps: list[URIRef] = []
        for step in graph.objects(phase, WF.hasNode):
            if isinstance(step, URIRef):
                raw_steps.append(step)
                step_to_phase[str(step)] = str(phase)
        phase_steps[str(phase)] = _sort_steps_by_next_chain(graph, raw_steps)

    # --- Artifact collection (machine-native only) ---
    phase_arts: dict[str, dict[str, tuple[dict[str, str], bool, bool]]] = {}
    all_refs: dict[str, dict[str, str]] = {}
    node_types = (WF.Step, WF.Decision, WF.Eval, WF.Group)
    all_scope_nodes = [n for cls in node_types for n in subjects_of_type(graph, cls) if workflow_scope(n) == scope]
    for node in all_scope_nodes:
        pstr = step_to_phase.get(str(node))
        if not pstr:
            continue
        for role, path, _ in directory_data_for_node(graph, node):
            ref = data_ref_for_locator(data_registry, data_type="local_file", locator=path)
            if ref.get("artifact_type") not in MACHINE_NATIVE_ARTIFACTS:
                continue
            all_refs.setdefault(ref["id"], ref)
            produces, consumes, _ = data_edge_labels(role)
            prev_p, prev_c = phase_arts.setdefault(pstr, {}).get(ref["id"], (ref, False, False))[1:]
            phase_arts[pstr][ref["id"]] = (ref, prev_p or produces, prev_c or consumes)

    display_aids = set(all_refs) - {a for a in all_refs if a.startswith("deliverable:")}

    # --- Mermaid ---
    lines: list[str] = ["flowchart TD", ""]

    artifact_nids: dict[str, str] = {}
    for aid in sorted(display_aids):
        ref = all_refs[aid]
        a_nid = data_id(aid)
        artifact_nids[aid] = a_nid
        label = data_label(ref.get("data_type", "local_file"), ref.get("location", aid),
                           artifact_type=ref.get("artifact_type", "local_database"), node_id=aid)
        lines.append(f"  {mermaid_shape(a_nid, label, 'database')}")
    if display_aids:
        lines.append("")

    phase_nids: dict[str, str] = {}
    step_nids: dict[str, str] = {}
    for phase in phases_sorted:
        pstr = str(phase)
        p_nid = mermaid_id("ph", phase)
        phase_nids[pstr] = p_nid
        plabel = preferred_label(graph, phase) or display_id(phase)
        sg_id = re.sub(r"[^A-Za-z0-9_]", "_", display_id(phase))
        lines.append(f"  subgraph {sg_id}[\"{mermaid_label(plabel, 48)}\"]")
        steps = phase_steps.get(pstr, [])
        if steps:
            for step in steps:
                s_nid = mermaid_id("s", step)
                step_nids[str(step)] = s_nid
                slabel = preferred_label(graph, step) or display_id(step)
                shape = "rect"
                if (step, RDF.type, WF.Decision) in graph:
                    shape = "hexagon"
                elif (step, RDF.type, WF.Eval) in graph:
                    shape = "trapezoid"
                lines.append(f'    {mermaid_shape(s_nid, mermaid_label(slabel, 44), shape)}')
            for i in range(len(steps) - 1):
                lines.append(f"    {mermaid_id('s', steps[i])} --> {mermaid_id('s', steps[i + 1])}")
        else:
            lines.append(f'    {mermaid_shape(p_nid, mermaid_label(plabel, 44), "subroutine")}')
        lines.append("  end")
        lines.append("")

    for i in range(len(phases_sorted) - 1):
        cur, nxt = phases_sorted[i], phases_sorted[i + 1]
        cur_steps = phase_steps.get(str(cur), [])
        nxt_steps = phase_steps.get(str(nxt), [])
        src = mermaid_id("s", cur_steps[-1]) if cur_steps else phase_nids.get(str(cur), "")
        dst = mermaid_id("s", nxt_steps[0]) if nxt_steps else phase_nids.get(str(nxt), "")
        if src and dst:
            lines.append(f"  {src} --> {dst}")

    if phases_sorted:
        lines.append("")

    for phase in phases_sorted:
        pstr = str(phase)
        arts = phase_arts.get(pstr, {})
        steps = phase_steps.get(pstr, [])
        produce_src = mermaid_id("s", steps[-1]) if steps else phase_nids.get(pstr, "")
        consume_dst = mermaid_id("s", steps[0]) if steps else phase_nids.get(pstr, "")
        for aid, (ref, produces, consumes) in arts.items():
            if aid not in display_aids:
                continue
            a_nid = artifact_nids.get(aid, "")
            if not a_nid:
                continue
            if produces and produce_src:
                lines.append(f"  {produce_src} -.->|produces| {a_nid}")
            if consumes and consume_dst:
                lines.append(f"  {a_nid} -.->|consumes| {consume_dst}")

    body = "\n".join(lines)
    return (
        f"> Internal flow for `{scope_label(scope)}`. "
        "Boxed subgraphs = workflows; nodes inside = workflow nodes. "
        "Cylinders = machine-native artifacts.\n\n"
        f"```mermaid\n{body}\n```"
    )


def build_workflow_topology(
    graph: Graph,
    scope: str | None = None,
    data_registry: dict[str, dict[str, str]] | None = None,
    view: str = "integrated",
) -> str:
    data_registry = data_registry or {}
    stream_view_names = {"artifact-stream", "data-stream"}
    display_view = "artifact-stream" if view == "data-stream" else view
    intro = "> Generated from MSO workflow TTL. Edit the TTL source, then regenerate this view."
    notes: list[str] = []
    if scope:
        intro = f"> `{display_view}` view for workflow scope `{scope}`. Generated from MSO workflow TTL."
        if view in stream_view_names:
            notes.append("> Artifact stream view: `artifact --consumes--> actor/tool --produces--> artifact` supply chain only.")
        elif view == "workflow":
            notes.append("> Workflow view: `((start)) --next--> task --next--> task --next--> ((end))` spine derived from shared artifact ids where possible.")
        else:
            notes.append("> Integrated view: artifact stream supply chain plus the derived task workflow spine.")
    include_internal = scope is not None
    show_data_stream = include_internal and view in {"integrated", *stream_view_names}
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
    emitted_styles: set[str] = set()
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
                if cls == "decision":
                    style_node(node_id, decision_style(term, inferred=is_inferred_branch_step(term)))
            declared.add(node_id)
        return node_id

    def declare_data(logical_id: str, label: str, artifact_type: str) -> str:
        node_id = data_id(logical_id)
        if node_id not in declared:
            if artifact_type in MACHINE_NATIVE_ARTIFACTS:
                shape = "database"
            elif artifact_type == "media":
                shape = "stadium"
            elif artifact_type == "tool":
                shape = "subroutine"
            else:
                shape = "document"
            css_class = artifact_type
            lines.append(f"  {mermaid_shape(node_id, label, shape)}")
            lines.append(f"  class {node_id} {css_class}")
            declared.add(node_id)
        return node_id

    def task_tool_node_id(task: URIRef) -> str | None:
        tool_value = first_literal(graph, task, WF.usesTool)
        if not tool_value:
            return None
        ref = data_ref_for_locator(data_registry, data_type="local_file", locator=tool_value)
        if show_data_stream:
            data_refs.setdefault(ref["id"], ref)
            tool_node_id = declare_data(
                ref["id"],
                data_label(
                    ref["data_type"],
                    ref["location"],
                    node_id=ref["id"],
                    locator=ref["locator"],
                    artifact_type=ref.get("artifact_type", "tool"),
                ),
                ref.get("artifact_type", "tool"),
            )
            data_node_ids.add(tool_node_id)
            return tool_node_id
        return data_id(ref["id"])

    def edge(source_id: str, arrow: str, label: str, target_id: str) -> None:
        label_part = f"|{label}|" if label else ""
        line = f"  {source_id} {arrow}{label_part} {target_id}"
        if line not in emitted_edges:
            lines.append(line)
            emitted_edges.add(line)

    def style_node(node_id: str, style: str | None) -> None:
        if not style:
            return
        line = f"  style {node_id} {style}"
        if line not in emitted_styles:
            lines.append(line)
            emitted_styles.add(line)

    def declare_boundary(kind: str) -> str:
        node_id = mermaid_id(f"boundary_{kind}", f"{scope}:{kind}")
        if node_id not in declared:
            lines.append(f"  {mermaid_shape(node_id, kind, 'circle')}")
            lines.append(f"  class {node_id} boundary")
            declared.add(node_id)
        return node_id

    def rendered_outgoing_targets(term: URIRef) -> set[str]:
        targets: set[str] = set()
        for target in graph.objects(term, WF.next):
            if isinstance(target, URIRef) and in_scope(target):
                targets.add(f"next:{target}")
        for branch in graph.objects(term, WF.hasBranch):
            if isinstance(branch, URIRef):
                for target in graph.objects(branch, WF.gotoNode):
                    if isinstance(target, URIRef) and in_scope(target):
                        targets.add(f"goto:{target}")
        return targets

    def is_inferred_branch_step(term: URIRef) -> bool:
        if (term, RDF.type, WF.Step) not in graph:
            return False
        targets = rendered_outgoing_targets(term)
        return len(targets) >= 2

    def decision_style(term: URIRef, *, inferred: bool = False) -> str | None:
        subject = decision_subject(term, inferred=inferred)
        if subject == "user":
            return "fill:#ffedd5,stroke:#ea580c,color:#111827"
        if subject == "agent":
            return "fill:#dbeafe,stroke:#2563eb,color:#111827"
        return None

    def decision_subject(term: URIRef, *, inferred: bool = False) -> str | None:
        explicit = (first_literal(graph, term, WF.decisionSubject) or "").strip().lower()
        if explicit in {"user", "agent"}:
            return explicit
        legacy_judge = (first_literal(graph, term, WF.judge) or "").strip().upper()
        if legacy_judge in {"HITL", "HITLFE"}:
            return "user"
        if legacy_judge in {"HOTL", "HOOTL"} or inferred:
            return "agent"
        return "agent" if inferred else None

    def first_decision_criterion(term: URIRef) -> str | None:
        for predicate in (
            WF.decisionCriteria,
            WF.threshold,
            WF.passCriteria,
            WF.successCriteria,
            WF.criteria,
            WF.description,
        ):
            value = first_literal(graph, term, predicate)
            if value:
                return value
        return None

    def decision_branch_label(decision: URIRef, branch: URIRef) -> str:
        branch_condition = first_literal(graph, branch, WF.on)
        label = f"on: {branch_condition}" if branch_condition else "goto"
        criterion = first_literal(graph, branch, WF.decisionCriteria) or first_literal(graph, branch, WF.criteria)
        if not criterion and branch_condition:
            decision_criterion = first_decision_criterion(decision)
            if decision_criterion:
                criterion = decision_criterion
        if criterion:
            label = f"{label} / {criterion}"
        return mermaid_label(label, 56)

    def visual_kind(term: URIRef) -> tuple[str, str | None, str, str]:
        for rdf_type, css_class in (
            (WF.Step, "step"),
            (WF.Decision, "decision"),
            (WF.Eval, "eval"),
            (WF.Group, "group"),
        ):
            if (term, RDF.type, rdf_type) in graph:
                suffix = local_name(rdf_type)
                status = first_literal(graph, term, WF.status)
                if status:
                    suffix = f"{suffix} / {status}"
                if rdf_type == WF.Step and is_inferred_branch_step(term):
                    suffix = "Decision / inferred-branch"
                    shape = "hexagon"
                    return "decision", "decision", suffix, shape
                if rdf_type == WF.Decision:
                    shape = "hexagon"
                    subject = decision_subject(term)
                    if subject:
                        suffix = f"{suffix}<br>subject: {subject}"
                elif rdf_type == WF.Eval:
                    shape = "trapezoid"
                    judge = first_literal(graph, term, WF.judge)
                    oracle_subj = (
                        first_literal(graph, term, WF.oracle)
                        or first_literal(graph, term, WF.oracleType)
                    )
                    if not oracle_subj and judge:
                        judge_norm = judge.strip().upper()
                        if judge_norm in {"HITL", "HITLFE", "HOTL", "HOOTL"}:
                            oracle_subj = "user"
                        elif judge_norm == "METRIC":
                            oracle_subj = "metric"
                    if oracle_subj:
                        suffix = f"{suffix}<br>oracle: {oracle_subj}"
                else:
                    shape = "rect"
                return local_name(rdf_type).lower(), css_class, suffix, shape
        return "node", None, "", "rect"

    phases = filter_scope(process_units(graph), scope)

    # Build node→scope reverse map: flat-URI nodes (e.g. node/cd-s-001) have no
    # workflow-id segment, so workflow_scope() returns None for them.
    # Infer scope from the scoped phase that owns the node via wf:hasNode.
    node_to_scope: dict[URIRef, str] = {}
    for _phase_uri in process_units(graph):
        _phase_scope = workflow_scope(_phase_uri)
        if _phase_scope:
            for _node_uri in graph.objects(_phase_uri, WF.hasNode):
                if isinstance(_node_uri, URIRef) and _node_uri not in node_to_scope:
                    node_to_scope[_node_uri] = _phase_scope

    def in_scope(term: URIRef) -> bool:
        return workflow_scope(term) == scope or node_to_scope.get(term) == scope

    if include_internal:
        for phase in phases:
            phase_id = mermaid_id("phase", phase)
            status = first_literal(graph, phase, WF.status)
            if view in stream_view_names:
                # artifact-stream: concise "scope / phase" label — no id/status noise
                _phase_scope = workflow_scope(phase) or (scope or "")
                _phase_lbl = preferred_label(graph, phase) or display_id(phase)
                label = f"{scope_label(_phase_scope)} / {mermaid_label(_phase_lbl, 44)}"
            else:
                suffix = f"Workflow / {status}" if status else "Workflow"
                label = mermaid_node_label(graph, phase, suffix)
            if phase_id not in declared:
                lines.append(f'  subgraph {phase_id}["{label}"]')
                lines.append("    direction LR")
                declared.add(phase_id)
                for node in sorted(graph.objects(phase, WF.hasNode), key=str):
                    if isinstance(node, URIRef) and in_scope(node):
                        if view in stream_view_names and not has_supply_chain(graph, node):
                            continue  # 공급망 연결 없는 노드는 artifact-stream 뷰에서 제외
                        node_prefix, node_cls, node_suffix, node_shape = visual_kind(node)
                        if view in stream_view_names and node_cls not in {"decision", "eval"}:
                            node_suffix = ""  # artifact-stream: label + id only, no type/status
                        declare(node, node_prefix, node_cls, node_suffix, node_shape)
                lines.append("  end")
    else:
        for phase in phases:
            status = first_literal(graph, phase, WF.status)
            phase_cls = f"status_{status}" if status in {"completed", "active", "pending"} else "workflow"
            suffix = f"Workflow / {status}" if status else "Workflow"
            declare(phase, "phase", phase_cls, suffix)

    if include_internal:
        node_classes = [
            (WF.Step, "step"),
            (WF.Decision, "decision"),
            (WF.Eval, "eval"),
            (WF.Group, "group"),
        ]
        for cls, css_class in node_classes:
            for node in subjects_of_type(graph, cls):
                if scope is not None and not in_scope(node):
                    continue
                status = first_literal(graph, node, WF.status)
                if view in stream_view_names:
                    if not has_supply_chain(graph, node):
                        continue  # 공급망 연결 없는 노드는 artifact-stream 뷰에서 제외
                    # artifact-stream: label only for ordinary nodes; eval gates
                    # keep oracle metadata because it is routing signal.
                    node_prefix, node_cls, node_suffix, node_shape = visual_kind(node)
                    node_id = mermaid_id(node_prefix, node)
                    if node_id not in declared:
                        _lbl = preferred_label(graph, node) or display_id(node)
                        if node_cls in {"decision", "eval"}:
                            _lbl_short = mermaid_node_label(graph, node, node_suffix)
                        else:
                            _lbl_short = f"{mermaid_label(_lbl, 52)}<br>id: {display_id(node)}"
                        lines.append(f"  {mermaid_shape(node_id, _lbl_short, node_shape)}")
                        node_class = node_cls or css_class
                        lines.append(f"  class {node_id} {node_class}")
                        if node_class == "decision":
                            style_node(node_id, decision_style(node, inferred=is_inferred_branch_step(node)))
                        declared.add(node_id)
                else:
                    node_prefix, node_cls, node_suffix, node_shape = visual_kind(node)
                    declare(node, node_prefix, node_cls or css_class, node_suffix, node_shape)

    for module in filter_scope(subjects_of_type(graph, WF.Module), scope):
        declare(module, "module", "module", "Module")

    for milestone in filter_scope(subjects_of_type(graph, WF.Milestone), scope):
        status = first_literal(graph, milestone, WF.status)
        suffix = f"Milestone / {status}" if status else "Milestone"
        declare(milestone, "milestone", "milestone", suffix)

    # Implicit discovery → development → testing ordering for lifecycle sub-workflows.
    if include_internal and scope:
        PHASE_ORDER = ["discovery", "development", "testing"]
        ordered: dict[str, URIRef] = {}
        for ph in phases:
            ph_local = display_id(ph)
            if ph_local in PHASE_ORDER:
                ordered[ph_local] = ph
        for i in range(len(PHASE_ORDER) - 1):
            src_key, dst_key = PHASE_ORDER[i], PHASE_ORDER[i + 1]
            if src_key in ordered and dst_key in ordered:
                dst_ph = ordered[dst_key]
                edge(mermaid_id("phase", ordered[src_key]), "-->", "", mermaid_id("phase", dst_ph))

    if include_internal:
        # Use in_scope so flat-URI nodes inferred from wf:hasNode are included
        process_nodes = [n for n in workflow_node_terms(graph) if in_scope(n)]
        control_edges: list[tuple[URIRef, str, str, URIRef]] = []
        terminal_branch_edges: list[tuple[URIRef, str]] = []
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
                    branch_label = decision_branch_label(decision, branch)
                    has_target = False
                    for target in sorted(graph.objects(branch, WF.gotoNode), key=str):
                        if isinstance(target, URIRef) and workflow_scope(target) == scope:
                            has_target = True
                            control_edges.append((decision, "-.->", branch_label, target))
                            control_incoming.add(target)
                            control_outgoing.add(decision)
                    if not has_target:
                        terminal_branch_edges.append((decision, branch_label))
                        control_outgoing.add(decision)

        for eval_node in [n for n in subjects_of_type(graph, WF.Eval) if scope is None or in_scope(n)]:
                on_fail_id = first_literal(graph, eval_node, WF.onFail)
                if on_fail_id:
                    target = WF[f"node/{on_fail_id}"]
                    if in_scope(target):
                        control_edges.append((eval_node, "-.->", "on: fail", target))
                        control_incoming.add(target)
                        control_outgoing.add(eval_node)

        for node in process_nodes:
            for target in sorted(graph.objects(node, WF.next), key=str):
                if isinstance(target, URIRef) and in_scope(target):
                    control_edges.append((node, "-->", "next", target))
                    control_incoming.add(target)
                    control_outgoing.add(node)

        if show_workflow_spine:
            for source, arrow, label, target in control_edges:
                if arrow not in ("-.->",) and label not in ("next",):  # decision branch / workflow next
                    continue
                source_prefix, source_cls, source_suffix, source_shape = visual_kind(source)
                target_prefix, target_cls, target_suffix, target_shape = visual_kind(target)
                source_id = declare(source, source_prefix, source_cls, source_suffix, source_shape)
                target_id = declare(target, target_prefix, target_cls, target_suffix, target_shape)
                edge(source_id, arrow, label, target_id)

        for node in process_nodes:
            if view in stream_view_names and not has_supply_chain(graph, node):
                continue  # artifact-stream: 공급망 없는 노드 선언 제외
            source_prefix, source_cls, source_suffix, source_shape = visual_kind(node)
            source_id = declare(node, source_prefix, source_cls, source_suffix, source_shape)
            stream_actor_id = task_tool_node_id(node) or source_id
            for role, path, _ in directory_data_for_node(graph, node):
                produces, consumes, label_suffix = data_edge_labels(role)
                if not produces and not consumes:
                    continue
                ref = data_ref_for_locator(data_registry, data_type="local_file", locator=path)
                if show_data_stream:
                    data_refs.setdefault(ref["id"], ref)
                    artifact_type = ref.get("artifact_type", "document")
                    data_node_id = declare_data(
                        ref["id"],
                        data_label(
                            ref["data_type"],
                            ref["location"],
                            node_id=ref["id"],
                            locator=ref["locator"],
                            artifact_type=artifact_type,
                        ),
                        artifact_type,
                    )
                else:
                    data_node_id = data_id(ref["id"])
                data_node_ids.add(data_node_id)
                if produces:
                    produced_data_node_ids.add(data_node_id)
                    data_producers.setdefault(data_node_id, set()).add(node)
                    if show_data_stream:
                        edge(stream_actor_id, "-.->", f"produces{label_suffix}", data_node_id)
                if consumes:
                    consumed_data_node_ids.add(data_node_id)
                    data_consumers.setdefault(data_node_id, set()).add(node)
                    if show_data_stream:
                        edge(data_node_id, "-.->", f"consumes{label_suffix}", stream_actor_id)

            for deliverable, _ in deliverable_data_for_node(graph, node):
                ref = deliverable_data_ref(deliverable)
                if show_data_stream:
                    data_refs.setdefault(ref["id"], ref)
                    artifact_type = ref.get("artifact_type", "document")
                    data_node_id = declare_data(
                        ref["id"],
                        data_label(
                            ref["data_type"],
                            ref["location"],
                            deliverable,
                            node_id=ref["id"],
                            locator=ref["locator"],
                            artifact_type=artifact_type,
                        ),
                        artifact_type,
                    )
                else:
                    data_node_id = data_id(ref["id"])
                data_node_ids.add(data_node_id)
                produced_data_node_ids.add(data_node_id)
                data_producers.setdefault(data_node_id, set()).add(node)
                if show_data_stream:
                    edge(stream_actor_id, "-.->", "produces", data_node_id)

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
                entry_nodes = {node for node in spine_sources - spine_targets if node not in control_incoming}
                exit_nodes = {node for node in spine_targets - spine_sources if node not in control_outgoing}
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
            for source, label in terminal_branch_edges:
                source_prefix, source_cls, source_suffix, source_shape = visual_kind(source)
                source_id = declare(source, source_prefix, source_cls, source_suffix, source_shape)
                edge(source_id, "-.->", label, end_id)
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
            for source, label in terminal_branch_edges:
                source_prefix, source_cls, source_suffix, source_shape = visual_kind(source)
                source_id = declare(source, source_prefix, source_cls, source_suffix, source_shape)
                edge(source_id, "-.->", label, end_id)

        # delegation/validation/revision/report edges — shown in ALL scoped views.
        # Eval.targetArtifact means Eval --target--> tool when it points at a tool,
        # while artifacts produced by that tool are --validated_by--> Eval.
        # Non-tool targetArtifact is directly artifact --validated_by--> Eval.
        # Eval --approves--> next task/end. Eval.orderTarget requests a revision.
        # Step.targetArtifact means remediation agentTask --target--> artifact/tool.
        # Step.usesTool means agentTask --delegates_to--> tool.
        if include_internal:
            eval_nodes = {
                n for n in subjects_of_type(graph, WF.Eval)
                if scope is None or in_scope(n)
            }
            target_nodes = {
                n for n in graph.subjects(WF.targetArtifact, None)
                if isinstance(n, URIRef) and (scope is None or in_scope(n))
            }
            delegation_nodes = {
                n for n in graph.subjects(WF.usesTool, None)
                if isinstance(n, URIRef) and (scope is None or in_scope(n))
            }
            for target_node in sorted(eval_nodes | target_nodes | delegation_nodes, key=str):
                node_prefix, node_cls, node_suffix, node_shape = visual_kind(target_node)
                node_nid = declare(target_node, node_prefix, node_cls, node_suffix, node_shape)

                for tool_value in graph.objects(target_node, WF.usesTool):
                    if not isinstance(tool_value, Literal):
                        continue
                    tool_str = literal_text(tool_value)
                    if not tool_str:
                        continue
                    tool_ref = data_ref_for_locator(data_registry, data_type="local_file", locator=tool_str)
                    tool_nid = data_id(tool_ref["id"])
                    if tool_nid not in declared:
                        tool_label_str = data_label(
                            tool_ref["data_type"], tool_ref.get("location", tool_str),
                            locator=tool_ref.get("locator", tool_str),
                            node_id=tool_ref["id"],
                            artifact_type=tool_ref.get("artifact_type", "document"),
                        )
                        declare_data(tool_ref["id"], tool_label_str, tool_ref.get("artifact_type", "document"))
                        data_node_ids.add(tool_nid)
                    edge(node_nid, "-->", "delegates_to", tool_nid)

                is_eval_node = (target_node, RDF.type, WF.Eval) in graph
                art_str = first_literal(graph, target_node, WF.targetArtifact)
                if art_str:
                    ref = data_ref_for_locator(data_registry, data_type="local_file", locator=art_str)
                    art_ref = ref if ref else {
                        "id": f"local_file:{art_str}", "data_type": "local_file",
                        "location": art_str, "locator": art_str, "artifact_type": "document",
                    }
                    art_nid = data_id(art_ref["id"])
                    if art_nid not in declared:
                        art_label_str = data_label(
                            art_ref["data_type"], art_ref.get("location", art_str),
                            locator=art_ref.get("locator", art_str),
                            node_id=art_ref["id"],
                            artifact_type=art_ref.get("artifact_type", "document"),
                        )
                        declare_data(art_ref["id"], art_label_str, art_ref.get("artifact_type", "document"))
                        data_node_ids.add(art_nid)
                    if not is_eval_node:
                        edge(node_nid, "-->", "target", art_nid)
                    elif art_ref.get("artifact_type") == "tool":
                        edge(node_nid, "-->", "target", art_nid)
                        target_locator = normalize_locator(art_ref.get("locator", art_str))
                        for producer in process_nodes:
                            producer_tools = [
                                normalize_locator(literal_text(tool))
                                for tool in graph.objects(producer, WF.usesTool)
                                if isinstance(tool, Literal) and literal_text(tool)
                            ]
                            if target_locator not in producer_tools:
                                continue
                            produced_deliverables: list[tuple[str, dict[str, str]]] = [
                                (deliverable, deliverable_data_ref(deliverable))
                                for deliverable, _ in deliverable_data_for_node(graph, producer)
                            ]
                            has_table_deliverable = any(
                                ref.get("artifact_type") == "table" for _, ref in produced_deliverables
                            )
                            if not has_table_deliverable:
                                for role, path, _ in directory_data_for_node(graph, producer):
                                    produces, _, _ = data_edge_labels(role)
                                    if not produces:
                                        continue
                                    produced_ref = data_ref_for_locator(
                                        data_registry, data_type="local_file", locator=path
                                    )
                                    produced_nid = declare_data(
                                        produced_ref["id"],
                                        data_label(
                                            produced_ref["data_type"],
                                            produced_ref["location"],
                                            node_id=produced_ref["id"],
                                            locator=produced_ref["locator"],
                                            artifact_type=produced_ref.get("artifact_type", "document"),
                                        ),
                                        produced_ref.get("artifact_type", "document"),
                                    )
                                    data_node_ids.add(produced_nid)
                                    edge(produced_nid, "-.->", "validated_by", node_nid)
                            for deliverable, produced_ref in produced_deliverables:
                                produced_nid = declare_data(
                                    produced_ref["id"],
                                    data_label(
                                        produced_ref["data_type"],
                                        produced_ref["location"],
                                        deliverable,
                                        node_id=produced_ref["id"],
                                        locator=produced_ref["locator"],
                                        artifact_type=produced_ref.get("artifact_type", "document"),
                                    ),
                                    produced_ref.get("artifact_type", "document"),
                                )
                                data_node_ids.add(produced_nid)
                                edge(produced_nid, "-.->", "validated_by", node_nid)
                    elif is_eval_node:
                        edge(art_nid, "-.->", "validated_by", node_nid)

                if is_eval_node:
                    approval_targets = [
                        t for t in sorted(graph.objects(target_node, WF.next), key=str)
                        if isinstance(t, URIRef) and in_scope(t)
                    ]
                    if approval_targets:
                        for approved_target in approval_targets:
                            a_prefix, a_cls, a_suffix, a_shape = visual_kind(approved_target)
                            a_nid = declare(approved_target, a_prefix, a_cls, a_suffix, a_shape)
                            edge(node_nid, "-->", "approves", a_nid)
                    else:
                        edge(node_nid, "-->", "approves", declare_boundary("end"))

                # requests_revision — eval --> downstream task/decision
                order_str = first_literal(graph, target_node, WF.orderTarget)
                if order_str:
                    for cand in (WF[f"node/{order_str}"], WF[f"node/{scope}/{order_str}"]):
                        if isinstance(cand, URIRef) and in_scope(cand):
                            t_prefix, t_cls, t_suffix, t_shape = visual_kind(cand)
                            t_nid = declare(cand, t_prefix, t_cls, t_suffix, t_shape)
                            edge(node_nid, "-->", "requests_revision", t_nid)
                            break

                # report — eval -.-> orderArtifact
                report_str = first_literal(graph, target_node, WF.orderArtifact)
                if report_str:
                    d_ref = deliverable_data_ref(report_str)
                    r_nid = data_id(d_ref["id"])
                    if r_nid not in declared:
                        r_label_str = data_label(
                            d_ref["data_type"], d_ref["location"],
                            detail=d_ref.get("detail"),
                            node_id=d_ref["id"],
                            artifact_type=d_ref.get("artifact_type", "document"),
                        )
                        declare_data(d_ref["id"], r_label_str, d_ref.get("artifact_type", "document"))
                        data_node_ids.add(r_nid)
                    edge(node_nid, "-.->", "report", r_nid)

        # artifact-stream intentionally omits workflow control edges such as
        # next/on:. Eval lifecycle and tool delegation edges above remain visible
        # because they explain artifact validation and revision flow.

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
            "  classDef step fill:#dbeafe,stroke:#2563eb,color:#111827",
            "  classDef decision fill:#f3f4f6,stroke:#6b7280,color:#111827",
            "  classDef eval fill:#fee2e2,stroke:#dc2626,color:#111827",
            "  classDef validation fill:#e0f2fe,stroke:#0284c7,color:#111827",
            "  classDef group fill:#f5f5f4,stroke:#78716c,color:#111827",
            "  classDef workflowRef fill:#e0f2fe,stroke:#0284c7,color:#111827",
            "  classDef module fill:#f0fdf4,stroke:#15803d,color:#111827",
            "  classDef milestone fill:#fdf2f8,stroke:#db2777,color:#111827",
            "  classDef knowledge_store fill:#f0f9ff,stroke:#0369a1,stroke-dasharray: 4 3,color:#111827",
            "  classDef event_store fill:#f5f3ff,stroke:#7c3aed,stroke-dasharray: 4 3,color:#111827",
            "  classDef local_database fill:#ecfdf5,stroke:#047857,stroke-dasharray: 4 3,color:#111827",
            "  classDef document fill:#fefce8,stroke:#a16207,color:#111827",
            "  classDef media fill:#fff7ed,stroke:#ea580c,color:#111827",
            "  classDef tool fill:#eef2ff,stroke:#4f46e5,color:#111827",
            "  classDef table fill:#ecfeff,stroke:#0891b2,stroke-dasharray: 4 3,color:#111827",
            "  classDef boundary fill:#ffffff,stroke:#111827,color:#111827",
            "```",
        ]
    )
    if include_internal and show_data_stream and data_refs:
        lines.extend(
            [
                "",
                "## Artifact Node Index",
                "",
                "| Artifact Type | Primary Consumer | Id | Medium | Location | Locator | Detail |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for ref in sorted(data_refs.values(), key=lambda item: item["id"]):
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(ref.get("artifact_type"), 18),
                        markdown_cell(ref.get("primary_consumer"), 18),
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
        "> Workflow-specific graph views generated from TTL ABox inputs. Each workflow has its own output directory.",
        "",
        "| Workflow Scope | Repository Graph | Workflow Graph | Artifact Stream Graph | Workflows | Nodes | Artifact Nodes |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for scope in scopes:
        phase_count = len(filter_scope(process_units(graph), scope))
        node_terms = workflow_node_terms(graph, scope)
        data_count = len(data_keys(graph, scope, data_registry))
        folder = scope_dir_name(scope)
        lines.append(
            f"| `{scope_label(scope)}` | [`repository-graph.md`]({folder}/repository-graph.md) | [`workflow-graph.md`]({folder}/workflow-graph.md) | [`artifact-stream-graph.md`]({folder}/artifact-stream-graph.md) | {phase_count} | {len(node_terms)} | {data_count} |"
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
                label = mermaid_label(f"{preferred_label(graph, prop)} {prop_type}", 48)
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
            "- [workflow-subgraph-index.md](workflow-subgraph-index.md) — workflow-specific sub-graph index",
            "- `<workflow>/repository-graph.md` — integrated repository graph for one workflow scope",
            "- `<workflow>/workflow-graph.md` — task workflow spine for one workflow scope",
            "- `<workflow>/artifact-stream-graph.md` — artifact supply-chain graph for one workflow scope",
            "- [artifact-stream-report.md](artifact-stream-report.md) — produced/unconsumed artifacts and external input checklist",
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


def clean_generated_graph_views(output_dir: Path) -> None:
    """Remove old generated graph files/directories before writing the current layout."""
    legacy_files = {
        "workflow-topology.md",
        "process-map.md",
        "resource-stream-report.md",
        "data-stream-report.md",
    }
    legacy_dirs = {
        "workflow-subgraphs",
        "workflow-views",
        "artifact-stream-views",
        "process-views",
        "resource-stream-views",
        "data-stream-views",
    }
    if not output_dir.exists():
        return
    for child in output_dir.iterdir():
        if child.is_dir():
            if child.name in legacy_dirs or (
                (child / "repository-graph.md").exists()
                or (child / "workflow-graph.md").exists()
                or (child / "artifact-stream-graph.md").exists()
            ):
                shutil.rmtree(child)
        elif child.name in legacy_files:
            child.unlink()


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
    clean_generated_graph_views(output_dir)
    ssot_report, legacy_yaml_count = build_workflow_ssot_report(workflow_dir, graph)

    write_markdown(output_dir / "workflow-subgraph-index.md", "MSO Workflow Sub-Graph Index", build_workflow_subgraph_index(graph, data_registry=data_registry))
    artifact_report = build_artifact_stream_report(graph, data_registry=data_registry)
    write_markdown(output_dir / "artifact-stream-report.md", "MSO Artifact Stream Report", artifact_report)
    # v0.6.0 oracle layer view (SPEC §3.3 축 A): evolves/exercises/has_subWorkflow/target
    # edge-필터. workflow 간 self-improvement 관계라 scope 무관(전체 graph).
    write_markdown(output_dir / "oracle-graph.md", "MSO Oracle Graph (self-improvement layer)", build_oracle_view(graph))
    for scope in workflow_scopes(graph):
        flow_dir = output_dir / scope_dir_name(scope)
        write_markdown(
            flow_dir / "repository-graph.md",
            f"MSO Repository Graph — {scope_label(scope)}",
            build_workflow_topology(graph, scope=scope, data_registry=data_registry, view="integrated"),
        )
        write_markdown(
            flow_dir / "workflow-graph.md",
            f"MSO Workflow Graph — {scope_label(scope)}",
            build_workflow_topology(graph, scope=scope, data_registry=data_registry, view="workflow"),
        )
        artifact_stream_view = build_workflow_topology(
            graph,
            scope=scope,
            data_registry=data_registry,
            view="artifact-stream",
        )
        write_markdown(
            flow_dir / "artifact-stream-graph.md",
            f"MSO Artifact Stream Graph — {scope_label(scope)}",
            artifact_stream_view,
        )
    write_markdown(output_dir / "workflow-ssot-report.md", "MSO Workflow SSOT Report", ssot_report)
    write_markdown(output_dir / "class-layer-map.md", "MSO Workflow Class Layer Map", build_class_layer_map(graph))
    write_markdown(output_dir / "property-map.md", "MSO Workflow Property Map", build_property_map(graph))
    write_markdown(output_dir / "runtime-analysis.md", "MSO Runtime Graph Analysis", build_runtime_analysis(args.root.resolve()))
    write_markdown(output_dir / "README.md", "MSO Graph Observability Views", build_readme(workflow_dir, ttl_paths, output_dir))

    print(f"Wrote graph observability views to {output_dir}")
    if legacy_yaml_count:
        print(
            f"WARNING: {legacy_yaml_count} legacy workflow YAML file/reference item(s) remain after TTL migration. Remove files after verifying sibling *.abox.ttl and replace YAML refs inside TTL. See workflow-ssot-report.md.",
            file=sys.stderr,
        )
        if args.strict_ssot:
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
