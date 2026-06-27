#!/usr/bin/env python3
"""Project work-memory JSONL entries into TTL and validate graph shape.

JSONL remains the work-memory SSOT because entries are append-only operational
records. This script creates a graph projection for relation/lifecycle
observability and SHACL validation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from rdflib import Graph, Literal, Namespace, RDF, URIRef

WM = Namespace("https://mso.dev/ontology/work-memory#")

TYPE_CLASS = {
    "issue-note": WM.IssueNote,
    "agent-decision": WM.AgentDecision,
    "user-decision": WM.UserDecision,
    "alternatives-record": WM.AlternativesRecord,
    "trouble-shooting": WM.TroubleShooting,
    "episode": WM.Episode,
    "pattern": WM.Pattern,
    "principle": WM.Principle,
    "auditlog": WM.AuditLog,
    "worklog": WM.WorkLog,
}

RELATION_PREDICATE = {
    "raised": WM.raised,
    "followed-by": WM.followedBy,
    "resolved-by": WM.resolvedBy,
    "caused-by": WM.causedBy,
    "analyzed-in": WM.analyzedIn,
    "shows-pattern": WM.showsPattern,
    "generalized-in": WM.generalizedIn,
    "crystallized-in": WM.crystallizedIn,
    "references": WM.references,
    "supersedes": WM.supersedes,
    "refines": WM.refines,
    "depends-on": WM.dependsOn,
}

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TBOX = SKILL_DIR / "references" / "tbox" / "work-memory-tbox.ttl"
DEFAULT_SHAPES = SKILL_DIR / "references" / "shapes" / "work-memory-shapes.ttl"


def entry_uri(entry_id: str) -> URIRef:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", entry_id)
    return WM["entry/" + safe]


def external_uri(value: str) -> URIRef:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:80].strip("_")
    if not safe:
        safe = "external"
    return WM["external/" + safe]


def metadata_predicate(key: str) -> URIRef:
    parts = re.split(r"[^A-Za-z0-9]+", key)
    camel = "".join(part[:1].upper() + part[1:] for part in parts if part)
    return WM["metadata" + (camel or "Value")]


def iter_jsonl(path: Path) -> Iterable[tuple[Path, int, dict[str, Any] | None, str | None]]:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            yield path, line_number, None, str(exc)
            continue
        if not isinstance(parsed, dict):
            yield path, line_number, None, f"non-dict JSONL row ({type(parsed).__name__})"
            continue
        yield path, line_number, parsed, None


def discover_entry_files(workmem_dir: Path, include_runtime: bool = False) -> list[Path]:
    roots = [workmem_dir / "track-record", workmem_dir / "insight-record"]
    if include_runtime:
        roots.extend([workmem_dir / "auditlog", workmem_dir / "worklog"])
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(path for path in root.rglob("*.jsonl") if path.is_file())
    return sorted(files)


def load_entries(workmem_dir: Path, include_runtime: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    issues: list[str] = []
    for path in discover_entry_files(workmem_dir, include_runtime=include_runtime):
        for src, line_number, entry, error in iter_jsonl(path):
            if error:
                issues.append(f"{src}:{line_number}: {error}")
                continue
            assert entry is not None
            entry["_source_file"] = str(src)
            entry["_source_line"] = line_number
            entries.append(entry)
    return entries, issues


def literal_value(value: Any) -> Literal:
    if isinstance(value, (dict, list)):
        return Literal(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return Literal(str(value))


def build_graph(workmem_dir: Path, include_runtime: bool = False) -> tuple[Graph, list[str]]:
    entries, issues = load_entries(workmem_dir, include_runtime=include_runtime)
    graph = Graph()
    graph.bind("wm", WM)

    ids: set[str] = {str(entry.get("id")) for entry in entries if entry.get("id")}
    seen_ids: set[str] = set()
    for entry in entries:
        entry_id = entry.get("id")
        entry_type = entry.get("type")
        if not isinstance(entry_id, str) or not entry_id:
            issues.append(f"{entry.get('_source_file')}:{entry.get('_source_line')}: missing id")
            continue
        if entry_id in seen_ids:
            issues.append(f"{entry.get('_source_file')}:{entry.get('_source_line')}: duplicate id {entry_id}")
        seen_ids.add(entry_id)

        subject = entry_uri(entry_id)
        graph.add((subject, RDF.type, WM.Entry))
        graph.add((subject, WM.entryId, Literal(entry_id)))
        if isinstance(entry_type, str) and entry_type in TYPE_CLASS:
            graph.add((subject, RDF.type, TYPE_CLASS[entry_type]))
            graph.add((subject, WM.typeName, Literal(entry_type)))
        elif entry_type:
            issues.append(f"{entry_id}: unknown type {entry_type}")

        for key, predicate in (
            ("title", WM.title),
            ("text", WM.text),
            ("created_at", WM.createdAt),
            ("source_path", WM.sourcePath),
            ("author", WM.author),
        ):
            value = entry.get(key)
            if value not in (None, ""):
                graph.add((subject, predicate, Literal(str(value))))

        for tag in entry.get("tags") or []:
            graph.add((subject, WM.tag, Literal(str(tag))))

        metadata = entry.get("metadata") or {}
        if isinstance(metadata, dict):
            graph.add((subject, WM.metadata, Literal(json.dumps(metadata, ensure_ascii=False, sort_keys=True))))
            for key, value in metadata.items():
                graph.add((subject, WM.metadataKey, Literal(str(key))))
                graph.add((subject, metadata_predicate(str(key)), literal_value(value)))

        for relation in entry.get("relations") or []:
            if not isinstance(relation, dict):
                issues.append(f"{entry_id}: non-dict relation {relation!r}")
                continue
            rel_type = relation.get("type")
            target = relation.get("target")
            if not rel_type or not target:
                issues.append(f"{entry_id}: relation missing type or target")
                continue
            predicate = RELATION_PREDICATE.get(str(rel_type))
            if predicate is None:
                issues.append(f"{entry_id}: unknown relation type {rel_type}")
                continue
            target_text = str(target)
            if target_text in ids:
                target_uri = entry_uri(target_text)
            elif str(rel_type) == "references":
                target_uri = external_uri(target_text)
                graph.add((target_uri, RDF.type, WM.ExternalReference))
                graph.add((target_uri, WM.externalValue, Literal(target_text)))
            else:
                target_uri = entry_uri(target_text)
            graph.add((subject, predicate, target_uri))

    return graph, issues


def validate_graph(graph: Graph, shapes_path: Path = DEFAULT_SHAPES, tbox_path: Path = DEFAULT_TBOX) -> tuple[bool, str]:
    try:
        from pyshacl import validate as shacl_validate
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit("pyshacl is required for wm_to_ttl.py validate.") from exc

    data_graph = Graph()
    for triple in graph:
        data_graph.add(triple)
    if tbox_path.exists():
        data_graph.parse(tbox_path, format="turtle")
    conforms, _results_graph, results_text = shacl_validate(
        data_graph,
        shacl_graph=str(shapes_path),
        inference="none",
        abort_on_first=False,
    )
    return bool(conforms), str(results_text)


def default_output_path(workmem_dir: Path) -> Path:
    return workmem_dir / "graph" / "work-memory.abox.ttl"


def command_project(args: argparse.Namespace) -> int:
    workmem_dir = Path(args.workmem_dir).resolve()
    graph, issues = build_graph(workmem_dir, include_runtime=args.include_runtime)
    if issues and args.strict:
        for issue in issues:
            print(f"[ERROR] {issue}", file=sys.stderr)
        return 1
    for issue in issues:
        print(f"[WARN] {issue}", file=sys.stderr)
    ttl_text = graph.serialize(format="turtle")
    if args.output:
        out = Path(args.output).resolve()
    else:
        out = default_output_path(workmem_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ttl_text, encoding="utf-8")
    print(f"WRITE {out}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    workmem_dir = Path(args.workmem_dir).resolve()
    graph, issues = build_graph(workmem_dir, include_runtime=args.include_runtime)
    if issues:
        for issue in issues:
            print(f"[ERROR] {issue}", file=sys.stderr)
        return 1
    conforms, results_text = validate_graph(graph)
    if args.ttl_out:
        out = Path(args.ttl_out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(graph.serialize(format="turtle"), encoding="utf-8")
        print(f"WRITE {out}")
    print(results_text)
    return 0 if conforms else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wm_to_ttl",
        description="Project work-memory JSONL entries to TTL and validate SHACL shapes.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    project = sub.add_parser("project", help="write work-memory graph projection TTL")
    project.add_argument("workmem_dir", help="agent-context/work-memory directory")
    project.add_argument("-o", "--output", help="output TTL path")
    project.add_argument("--include-runtime", action="store_true", help="include auditlog/worklog JSONL")
    project.add_argument("--strict", action="store_true", help="fail on JSONL parse/schema projection issues")
    project.set_defaults(func=command_project)

    validate = sub.add_parser("validate", help="validate projected graph with SHACL")
    validate.add_argument("workmem_dir", help="agent-context/work-memory directory")
    validate.add_argument("--ttl-out", help="also write projected TTL to this path")
    validate.add_argument("--include-runtime", action="store_true", help="include auditlog/worklog JSONL")
    validate.set_defaults(func=command_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
