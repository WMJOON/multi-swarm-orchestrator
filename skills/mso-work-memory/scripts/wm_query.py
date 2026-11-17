#!/usr/bin/env python3
"""wm_query.py — work-memory(.nt 정본)를 SPARQL 로 질의한다 (v0.16.0).

큐레이션 기록의 정본이 N-Triples 라서 **변환 없이 그대로 RDF 저장소에 적재**한다(별도 TTL 투영 불필요).
백엔드는 pyoxigraph(빠름, 선택 의존성)를 우선 쓰고, 없으면 rdflib 으로 폴백한다 — 결과는 같다.

흐름: 큐레이션 `.nt`(이행 전 `.jsonl` 도 wm_store 로 변환해 함께) 적재
      → derive.rq(파생 validity·버전 정렬 키를 SPARQL UPDATE 로 도출 — 저장하지 않는다, UD-0012)
      → 주체(Agent)·모듈·관련 노드 individual 추가(agents.yaml 레지스트리 반영)
      → SPARQL 실행

사용법:
  wm_query.py list                                   # 번들 질의 목록
  wm_query.py run memory-active                      # references/queries/<이름>.rq
  wm_query.py run memory-for-node --param node=discovery-s-001
  wm_query.py run memory-valid-at-version --param atKey=14004     # 버전 0.14.4 시점에 유효한 기록
  wm_query.py run --file my.rq | --sparql "SELECT ..."
  wm_query.py run ... --format table|json|tsv  [--backend auto|pyoxigraph|rdflib] [--no-derive]

질의 파일은 `{{이름:기본값}}` 자리표시자를 쓸 수 있다(--param 으로 바꾼다). 환경변수 WORKMEM_DIR(기본 ./agent-context/work-memory).
SHACL 검증은 pyshacl(rdflib 위)이라 이 도구의 범위가 아니다(`wm_to_ttl.py validate`).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wm_store  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
QUERY_DIR = SKILL_DIR / "references" / "queries"
WM = wm_store.WM
WF_NODE = "https://mso.dev/ontology/workflow#node/"
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::([^}]*))?\}\}")


def workmem_root() -> Path:
    return Path(os.environ.get("WORKMEM_DIR", "./agent-context/work-memory")).resolve()


# ── 백엔드 ──────────────────────────────────────────────────────────────────

class OxigraphBackend:
    name = "pyoxigraph"

    def __init__(self):
        import pyoxigraph as ox
        self.ox = ox
        self.store = ox.Store()

    def load_nt(self, path: Path) -> None:
        self.store.load(path=str(path), format=self.ox.RdfFormat.N_TRIPLES)

    def _term(self, term: tuple):
        ox = self.ox
        if term[0] == "i":
            return ox.NamedNode(term[1])
        return ox.Literal(term[1], datatype=ox.NamedNode(term[2])) if term[2] else ox.Literal(term[1])

    def add(self, s: str, p: str, o: tuple) -> None:
        ox = self.ox
        self.store.add(ox.Quad(ox.NamedNode(s), ox.NamedNode(p), self._term(o), ox.DefaultGraph()))

    def update(self, sparql: str) -> None:
        self.store.update(sparql)

    def select(self, sparql: str) -> tuple[list[str], list[list[str | None]]]:
        result = self.store.query(sparql)
        variables = [v.value for v in result.variables]
        rows = []
        for solution in result:
            rows.append([self._str(solution[v]) for v in variables])
        return variables, rows

    @staticmethod
    def _str(term) -> str | None:
        return None if term is None else term.value

    def size(self) -> int:
        return len(self.store)


class RdflibBackend:
    name = "rdflib"

    def __init__(self):
        from rdflib import Graph
        self.graph = Graph()

    def load_nt(self, path: Path) -> None:
        self.graph.parse(str(path), format="nt")

    def add(self, s: str, p: str, o: tuple) -> None:
        from rdflib import Literal, URIRef
        obj = URIRef(o[1]) if o[0] == "i" else (Literal(o[1], datatype=URIRef(o[2])) if o[2] else Literal(o[1]))
        self.graph.add((URIRef(s), URIRef(p), obj))

    def update(self, sparql: str) -> None:
        self.graph.update(sparql)

    def select(self, sparql: str) -> tuple[list[str], list[list[str | None]]]:
        result = self.graph.query(sparql)
        variables = [str(v) for v in result.vars]
        return variables, [[None if cell is None else str(cell) for cell in row] for row in result]

    def size(self) -> int:
        return len(self.graph)


def make_backend(preferred: str = "auto"):
    if preferred in ("auto", "pyoxigraph"):
        try:
            return OxigraphBackend()
        except ImportError:
            if preferred == "pyoxigraph":
                raise SystemExit("[ERROR] pyoxigraph 가 설치되어 있지 않다 (pip install pyoxigraph) — --backend rdflib 로 대체할 수 있다")
    try:
        return RdflibBackend()
    except ImportError:
        raise SystemExit("[ERROR] pyoxigraph 도 rdflib 도 없다 — 둘 중 하나를 설치해야 한다")


# ── 적재 ────────────────────────────────────────────────────────────────────

def load_store(backend, root: Path, extra_roots: tuple[Path, ...] = ()) -> dict[str, int]:
    """큐레이션 기록을 적재한다. `.nt` 는 그대로, 이행 전 `.jsonl` 은 wm_store 로 triple 변환해 넣는다."""
    stats = {"nt_files": 0, "jsonl_entries": 0}
    spec = wm_store.load_spec()
    for base in (root, *extra_roots):
        if not base or not Path(base).exists():
            continue
        seen_ids: dict[str, Path] = {}
        for path in wm_store.order_paths(Path(base).rglob("*.nt")):
            rel = path.relative_to(base)
            if any(part.startswith(".") for part in rel.parts[:-1]):
                continue
            if rel.parts[0] not in wm_store.CURATED_DIRS:
                continue
            if wm_store.is_conflict_copy(path):
                # iCloud 충돌 복제본은 같은 subject 를 조용히 합쳐 버리므로 적재하지 않는다(원본이 정본).
                print(f"[WARN] 충돌 복제본은 적재하지 않음: {path.name} — 내용을 확인하고 정리하세요", file=sys.stderr)
                continue
            for entry_id in wm_store.nt_entry_ids(path):
                if entry_id in seen_ids:
                    print(f"[WARN] {entry_id} 가 여러 파일에 있음({seen_ids[entry_id].name}, {path.name}) — 값이 합쳐진다", file=sys.stderr)
                seen_ids.setdefault(entry_id, path)
            backend.load_nt(path)
            stats["nt_files"] += 1
        for dirname in wm_store.CURATED_DIRS:
            for path in sorted((Path(base) / dirname).rglob("*.jsonl")) if (Path(base) / dirname).exists() else []:
                if wm_store.is_conflict_copy(path) and not any(p.startswith(".") for p in path.relative_to(base).parts[:-1]):
                    print(f"[WARN] 충돌 복제본은 적재하지 않음: {path.name} — 내용을 확인하고 정리하세요", file=sys.stderr)
        for entry, _path, _line, fmt in wm_store.iter_curated_entries(Path(base), spec, skip_conflict_copies=True):
            if fmt != "jsonl":
                continue
            for s, p, o in wm_store.entry_to_triples(entry, spec):
                backend.add(s, p, o)
            stats["jsonl_entries"] += 1
    return stats


def add_individuals(backend, root: Path) -> None:
    """질의에 필요한 individual: 주체(User/SoftwareAgent/BackgroundAgent, onBehalfOf), 모듈, 관련 workflow node.
    주체 레지스트리는 <work-memory>/agents.yaml(선택, PyYAML 이 있을 때) — 없으면 명세의 내장 기본을 쓴다."""
    spec = wm_store.load_spec()
    agents = {a["id"]: dict(a) for a in (spec.get("agents") or {}).get("builtin") or []}
    registry = Path(root) / "agents.yaml"
    if registry.is_file():
        try:
            import yaml
            for item in (yaml.safe_load(registry.read_text(encoding="utf-8")) or {}).get("agents") or []:
                if isinstance(item, dict) and item.get("id"):
                    agents[str(item["id"])] = dict(item)
        except ImportError:
            pass                                  # PyYAML 이 없으면 내장 기본만 — 질의 자체는 동작한다
    classes = spec["agents"]["classes"]
    cls = lambda kind: WM + (classes.get(kind) or classes["softwareAgent"])  # noqa: E731

    _, rows = backend.select(f'SELECT DISTINCT ?a WHERE {{ ?s ?p ?a . FILTER(STRSTARTS(STR(?a), "{wm_store.ID_NS}agent/")) }}')
    emitted: set[str] = set()

    def emit(agent_id: str) -> None:
        if agent_id in emitted:
            return
        emitted.add(agent_id)
        info = agents.get(agent_id) or {"id": agent_id, "kind": "softwareAgent"}
        node = wm_store.agent_iri(agent_id)
        backend.add(node, wm_store.RDF_TYPE, wm_store.I(WM + "Agent"))
        backend.add(node, wm_store.RDF_TYPE, wm_store.I(cls(info.get("kind", "softwareAgent"))))
        backend.add(node, WM + "agentId", wm_store.L(agent_id))
        owner = info.get("onBehalfOf")
        if owner and owner != agent_id:
            emit(str(owner))
            backend.add(node, WM + "onBehalfOf", wm_store.I(wm_store.agent_iri(str(owner))))
        if info.get("trigger"):
            backend.add(node, WM + "trigger", wm_store.L(str(info["trigger"])))

    for (iri,) in rows:
        emit(wm_store._tail(iri, wm_store.ID_NS + "agent/") or "")

    _, modules = backend.select(f'SELECT DISTINCT ?m WHERE {{ ?s ?p ?m . FILTER(STRSTARTS(STR(?m), "{wm_store.ID_NS}module/")) }}')
    for (iri,) in modules:
        backend.add(iri, wm_store.RDF_TYPE, wm_store.I(WM + "Module"))
        backend.add(iri, WM + "moduleId", wm_store.L(wm_store._tail(iri, wm_store.ID_NS + "module/") or ""))

    _, nodes = backend.select(f'SELECT DISTINCT ?s ?n WHERE {{ ?s <{WM}relatedNodeId> ?n }}')
    for subject, node_id in nodes:
        backend.add(subject, WM + "relatedNode", wm_store.I(WF_NODE + wm_store._enc(node_id)))


def build(root: Path | None = None, backend_name: str = "auto", derive: bool = True,
          extra_roots: tuple[Path, ...] = ()):
    """저장소를 만들어 돌려준다(적재 + 파생 + individual). 다른 코드(테스트 등)에서 재사용한다."""
    root = Path(root) if root else workmem_root()
    backend = make_backend(backend_name)
    load_store(backend, root, extra_roots)
    if derive:
        backend.update((QUERY_DIR / "derive.rq").read_text(encoding="utf-8"))
    add_individuals(backend, root)
    return backend


# ── 질의 ────────────────────────────────────────────────────────────────────

def render_query(text: str, params: dict[str, str] | None = None) -> str:
    """`{{이름:기본값}}` 자리표시자를 채운다. 기본값도 --param 도 없으면 오류."""
    params = params or {}

    def repl(match: re.Match) -> str:
        name, default = match.group(1), match.group(2)
        if name in params:
            return params[name]
        if default is not None:
            return default.strip()
        raise SystemExit(f"[ERROR] 질의 매개변수 {name} 가 필요하다 (--param {name}=값)")
    return _PLACEHOLDER.sub(repl, text)


def named_queries() -> list[str]:
    return sorted(p.stem for p in QUERY_DIR.glob("*.rq") if p.stem != "derive")


def load_named(name: str) -> str:
    path = QUERY_DIR / f"{name}.rq"
    if not path.is_file() or name == "derive":
        raise SystemExit(f"[ERROR] 번들 질의 없음: {name} (목록: {', '.join(named_queries())})")
    return path.read_text(encoding="utf-8")


def format_rows(variables: list[str], rows: list[list[str | None]], fmt: str) -> str:
    def short(value: str | None) -> str:
        if value is None:
            return ""
        for prefix in (wm_store.ID_NS, WM):
            if value.startswith(prefix):
                return value[len(prefix):]
        return value
    if fmt == "json":
        return json.dumps([dict(zip(variables, row)) for row in rows], ensure_ascii=False, indent=2)
    if fmt == "tsv":
        return "\n".join(["\t".join(variables), *("\t".join("" if c is None else c for c in row) for row in rows)])
    if not rows:
        return "(결과 없음)"
    table = [[short(c) for c in row] for row in rows]
    widths = [max(len(v), *(len(r[i]) for r in table)) for i, v in enumerate(variables)]
    line = lambda cells: "  ".join(c.ljust(w) for c, w in zip(cells, widths))  # noqa: E731
    return "\n".join([line(variables), line(["-" * w for w in widths]), *(line(r) for r in table)])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="work-memory 루트 (기본 WORKMEM_DIR)")
    ap.add_argument("--extra-root", action="append", default=[], help="추가 루트 (반복 가능)")
    ap.add_argument("--backend", choices=("auto", "pyoxigraph", "rdflib"), default="auto")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="번들 질의 목록")
    run = sub.add_parser("run", help="질의 실행")
    run.add_argument("name", nargs="?", help="번들 질의 이름")
    run.add_argument("--file", help="질의 파일")
    run.add_argument("--sparql", help="질의 문자열")
    run.add_argument("--param", action="append", default=[], help="자리표시자 값 name=값 (반복 가능)")
    run.add_argument("--format", choices=("table", "json", "tsv"), default="table")
    run.add_argument("--no-derive", action="store_true", help="파생 속성 도출을 건너뛴다(빠름, validity 질의 불가)")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        for name in named_queries():
            first = next((l[2:].strip() for l in (QUERY_DIR / f"{name}.rq").read_text(encoding="utf-8").splitlines() if l.startswith("# ")), "")
            print(f"{name:34} {first}")
        return 0

    sources = [x for x in (args.name, args.file, args.sparql) if x]
    if len(sources) != 1:
        ap.error("질의는 이름, --file, --sparql 중 정확히 하나로 지정한다")
    text = load_named(args.name) if args.name else (Path(args.file).read_text(encoding="utf-8") if args.file else args.sparql)
    params = {}
    for pair in args.param:
        if "=" not in pair:
            ap.error(f"--param 형식: name=값 (받은 값: {pair})")
        key, value = pair.split("=", 1)
        params[key] = value
    query = render_query(text, params)

    root = Path(args.root).resolve() if args.root else workmem_root()
    backend = build(root, args.backend, derive=not args.no_derive, extra_roots=tuple(Path(p).resolve() for p in args.extra_root))
    variables, rows = backend.select(query)
    print(format_rows(variables, rows, args.format))
    if args.format == "table":
        print(f"\n({len(rows)}건, {backend.name}, 저장소 {backend.size()} triples)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
