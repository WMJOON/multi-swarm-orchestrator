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

from rdflib import Graph, Literal, Namespace, RDF, URIRef, XSD

WM = Namespace("https://mso.dev/ontology/work-memory#")
WF = Namespace("https://mso.dev/ontology/workflow#")
# v0.16.0: 어휘(TBox)와 인스턴스(ABox)를 분리한다. 어휘는 hash 네임스페이스(WM), 인스턴스는 slash 네임스페이스(ID_NS)다.
ID_NS = "https://mso.dev/id/"



sys.path.insert(0, str(Path(__file__).resolve().parent))
import wm_release  # noqa: E402  (derive_validity — validity 규칙의 단일 정본)
import wm_metadata  # noqa: E402  (타입별 metadata 검사)
import wm_store  # noqa: E402  (기록 ↔ triple 변환 규칙의 단일 정의)

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


def version_key(version: Any) -> int | None:
    """semver 문자열을 major*1000000+minor*1000+patch 정수로. 형식이 다르면 None.
    문자열 사전순 비교는 '0.9.0' > '0.15.0' 로 틀리므로 SPARQL 비교용 정렬 키를 따로 낸다."""
    match = _SEMVER_RE.match(str(version or "").strip())
    if not match:
        return None
    major, minor, patch = (int(g) for g in match.groups())
    return major * 1_000_000 + minor * 1_000 + patch


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TBOX = SKILL_DIR / "references" / "tbox" / "work-memory-tbox.ttl"
DEFAULT_SHAPES = SKILL_DIR / "references" / "shapes" / "work-memory-shapes.ttl"
# metadata 명세(references/metadata-spec.yaml)에서 생성된 TBox/shapes. 기본 검증은 둘 다 읽는다.
METADATA_TBOX = SKILL_DIR / "references" / "tbox" / "work-memory-metadata-tbox.ttl"
METADATA_SHAPES = SKILL_DIR / "references" / "shapes" / "work-memory-metadata-shapes.ttl"


def entry_uri(entry_id: str) -> URIRef:
    return URIRef(wm_store.entry_iri(entry_id))


def agent_uri(agent_id: str) -> URIRef:
    return URIRef(wm_store.agent_iri(agent_id))


def module_uri(module_id: str) -> URIRef:
    return URIRef(wm_store.module_iri(module_id))


def _agent_class(kind: str, spec: dict[str, Any]) -> URIRef:
    return WM[(spec["agents"]["classes"].get(kind) or spec["agents"]["classes"]["softwareAgent"])]


def add_agent(graph: Graph, agent_id: str, agents: dict[str, dict[str, Any]], spec: dict[str, Any], emitted: set[str]) -> URIRef:
    """주체 individual 을 (한 번만) 내보낸다. 소속(onBehalfOf)과 백그라운드 구분(trigger)을 함께 낸다."""
    node = agent_uri(agent_id)
    if agent_id in emitted:
        return node
    emitted.add(agent_id)
    info = wm_metadata.agent_info(agents, agent_id)
    graph.add((node, RDF.type, WM.Agent))
    graph.add((node, RDF.type, _agent_class(info.get("kind", "softwareAgent"), spec)))
    graph.add((node, WM.agentId, Literal(agent_id)))
    owner = info.get("onBehalfOf")
    if owner and owner != agent_id:
        graph.add((node, WM.onBehalfOf, add_agent(graph, str(owner), agents, spec, emitted)))
    if info.get("trigger"):
        graph.add((node, WM.trigger, Literal(str(info["trigger"]))))
    return node


def _to_term(term: tuple):
    if term[0] == "i":
        return URIRef(term[1])
    return Literal(term[1], datatype=URIRef(term[2])) if term[2] else Literal(term[1])


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
    """큐레이션은 `.nt`(정본)와 이행 전 `.jsonl`, 런타임 로그(auditlog/worklog)는 `.jsonl`."""
    roots = [workmem_dir / d for d in wm_store.CURATED_DIRS]
    if include_runtime:
        roots.extend([workmem_dir / "auditlog", workmem_dir / "worklog"])
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(path for path in [*root.rglob("*.jsonl"), *root.rglob("*.nt")]
                         if path.is_file() and not any(part.startswith(".") for part in path.relative_to(root).parts[:-1]))
    return wm_store.order_paths(files)


def load_entries(workmem_dir: Path, include_runtime: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    issues: list[str] = []
    spec = wm_store.load_spec()
    for path in discover_entry_files(workmem_dir, include_runtime=include_runtime):
        if path.suffix == ".nt":
            loaded, problems = wm_store.load_nt_entries(path, spec)
            for number, message in problems:
                issues.append(f"{path}:{number}: {message}")
            for entry in loaded:
                entry["_source_file"] = str(path)
                entry["_source_line"] = None
                entries.append(entry)
            continue
        for src, line_number, entry, error in iter_jsonl(path):
            if error:
                issues.append(f"{src}:{line_number}: {error}")
                continue
            assert entry is not None
            entry["_source_file"] = str(src)
            entry["_source_line"] = line_number
            entries.append(entry)
    return entries, issues


def build_graph(workmem_dir: Path, include_runtime: bool = False) -> tuple[Graph, list[str]]:
    """기록 → RDF 그래프. 기록 ↔ triple 변환 규칙은 wm_store.entry_to_triples 하나만 쓴다(여기서 다시 구현하지 않는다).
    이 함수는 투영 단계에서만 붙는 것(주체·모듈·관련 노드 individual, 파생 validity)을 더한다."""
    entries, issues = load_entries(workmem_dir, include_runtime=include_runtime)
    graph = Graph()
    graph.bind("wm", WM)
    graph.bind("skos", "http://www.w3.org/2004/02/skos/core#")

    spec = wm_store.load_spec()
    agents = wm_metadata.load_agents(workmem_dir, spec)
    emitted_agents: set[str] = set()
    seen_ids: set[str] = set()
    strict_keys = set()
    for entry in entries:
        entry_id = entry.get("id")
        entry_type = entry.get("type")
        where = f"{entry.get('_source_file')}:{entry.get('_source_line')}"
        if not isinstance(entry_id, str) or not entry_id:
            issues.append(f"{where}: missing id")
            continue
        if entry_id in seen_ids:
            issues.append(f"{where}: duplicate id {entry_id}")
        seen_ids.add(entry_id)
        if entry_type and entry_type not in wm_store.TYPE_CLASS:
            issues.append(f"{entry_id}: unknown type {entry_type}")
        for relation in entry.get("relations") or []:
            if not isinstance(relation, dict):
                issues.append(f"{entry_id}: non-dict relation {relation!r}")
            elif not relation.get("type") or not relation.get("target"):
                issues.append(f"{entry_id}: relation missing type or target")
            elif str(relation["type"]) not in wm_store.RELATION_PREDICATE:
                issues.append(f"{entry_id}: unknown relation type {relation['type']}")

        triples = wm_store.entry_to_triples({k: v for k, v in entry.items() if not k.startswith("_")}, spec)
        for s, p, o in triples:
            graph.add((URIRef(s), URIRef(p), _to_term(o)))
        if entry.get("source_path"):
            graph.add((entry_uri(entry_id), WM.sourcePath, Literal(str(entry["source_path"]))))

        # 새 기록의 metadata 가 명세로 표현되지 않으면(통제 어휘 밖 값·형식 위반) 투영 이슈다. 옛 기록은 wm_node validate 가 경고한다.
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        if wm_metadata.is_new_record(entry, spec) and metadata.get("needs_review") is not True:
            blob = next((o[1] for s, p, o in triples if p == wm_store.WM + "unmapped"), None)
            unmapped_md = (json.loads(blob).get("metadata") or {}) if blob else {}
            defs = wm_store.type_metadata(spec, str(entry_type))
            for key in unmapped_md:
                if key in defs:
                    issues.append(f"{entry_id}: metadata.{key}={unmapped_md[key]!r} 은 명세로 표현할 수 없음 (wm:unmapped 에 원문 보존)")

    # `references` 는 대상이 로드된 entry 일 때만 entry 링크다. 투영에 없는 기록(런타임 로그 WL-…/AU-… 등)을 가리키면 외부 참조로 바꾼다 —
    # 그렇지 않으면 코어 shape(`references` 는 Entry 또는 ExternalReference)를 위반한다. 원문은 externalValue 로 보존된다.
    known = {entry_uri(e["id"]) for e in entries if isinstance(e.get("id"), str) and e["id"]}
    for s_, p_, o_ in list(graph.triples((None, WM.references, None))):
        if isinstance(o_, URIRef) and str(o_).startswith(wm_store.ID_NS + "memory/") and o_ not in known:
            original = wm_store._tail(str(o_), wm_store.ID_NS + "memory/") or str(o_)
            external = URIRef(wm_store.external_iri(original))
            graph.remove((s_, p_, o_))
            graph.add((s_, p_, external))
            graph.add((external, RDF.type, WM.ExternalReference))
            graph.add((external, WM.externalValue, Literal(original)))

    # 투영 단계에서만 붙는 individual: 주체, 모듈, 관련 workflow node
    for s, p, o in list(graph):
        if isinstance(o, URIRef) and str(o).startswith(wm_store.ID_NS + "agent/"):
            add_agent(graph, wm_store._tail(str(o), wm_store.ID_NS + "agent/") or "", agents, spec, emitted_agents)
        elif isinstance(o, URIRef) and str(o).startswith(wm_store.ID_NS + "module/"):
            graph.add((o, RDF.type, WM.Module))
            graph.add((o, WM.moduleId, Literal(wm_store._tail(str(o), wm_store.ID_NS + "module/") or "")))
        elif p == WM.relatedNodeId:
            graph.add((s, WM.relatedNode, WF["node/" + wm_store._enc(str(o))]))

    add_derived(graph, [e for e in entries if isinstance(e.get("id"), str) and e["id"]])
    return graph, issues


def add_derived(graph: Graph, entries: list[dict[str, Any]]) -> None:
    """파생 속성을 투영 결과에만 추가한다 — JSONL 에는 저장하지 않는다(UD-0012).

    validity/supersededBy 는 wm_release.derive_validity 를 재사용하고, 버전 정렬 키는 RN 의
    metadata.version 에서 계산한다. 규칙을 여기서 다시 구현하지 않는다(롤백 연쇄 의미가 갈라지지 않도록).
    """
    by_id = {e["id"]: e for e in entries}
    validity = wm_release.derive_validity(entries)
    rolled = {
        str(r["target"]) for e in entries if e.get("type") == "release-note"
        for r in (e.get("relations") or [])
        if isinstance(r, dict) and r.get("type") == "rolls-back" and r.get("target")
    }

    def release_version(rn_id: str) -> str | None:
        rn = by_id.get(rn_id)
        if not rn or rn.get("type") != "release-note":
            return None
        version = (rn.get("metadata") or {}).get("version")
        return str(version) if version and version_key(version) is not None else None

    for entry in entries:
        subject = entry_uri(entry["id"])
        info = validity[entry["id"]]
        graph.add((subject, WM.validity, Literal(info["validity"])))
        for newer in info["superseded_by"]:
            graph.add((subject, WM.supersededBy, entry_uri(newer)))

        if entry.get("type") == "release-note":
            key = version_key((entry.get("metadata") or {}).get("version"))
            if key is not None:
                graph.add((subject, WM.versionKey, Literal(key, datatype=XSD.integer)))

        rels = [r for r in (entry.get("relations") or []) if isinstance(r, dict)]
        from_versions = [
            v for r in rels if r.get("type") in ("released-in", "verified-in")
            if (v := release_version(str(r.get("target") or "")))
        ]
        inval_versions = [
            v for r in rels if r.get("type") == "invalidated-by" and str(r.get("target")) not in rolled
            if (v := release_version(str(r.get("target") or "")))
        ]
        for versions, ver_pred, key_pred in (
            (from_versions, WM.validFromVersion, WM.validFromKey),
            (inval_versions, WM.invalidatedInVersion, WM.invalidatedInKey),
        ):
            if versions:
                earliest = min(versions, key=lambda v: version_key(v) or 0)
                graph.add((subject, ver_pred, Literal(earliest)))
                graph.add((subject, key_pred, Literal(version_key(earliest), datatype=XSD.integer)))


def validate_graph(graph: Graph, shapes_path: Path | None = None, tbox_path: Path | None = None) -> tuple[bool, str]:
    """SHACL 검증. 기본은 코어 + metadata 명세에서 생성된 TBox/shapes 를 모두 읽는다.
    sh:sparql(필수 metadata)을 위해 advanced=True, 소속 누락 같은 sh:Warning 은 실패로 보지 않는다(allow_warnings)."""
    try:
        from pyshacl import validate as shacl_validate
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit("pyshacl is required for wm_to_ttl.py validate.") from exc

    tbox_paths = [tbox_path] if tbox_path else [DEFAULT_TBOX, METADATA_TBOX]
    shape_paths = [shapes_path] if shapes_path else [DEFAULT_SHAPES, METADATA_SHAPES]
    data_graph = Graph()
    for triple in graph:
        data_graph.add(triple)
    for path in tbox_paths:
        if path.exists():
            data_graph.parse(path, format="turtle")
    shapes_graph = Graph()
    for path in shape_paths:
        if path.exists():
            shapes_graph.parse(path, format="turtle")
    conforms, _results_graph, results_text = shacl_validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="none",
        advanced=True,
        allow_warnings=True,
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
