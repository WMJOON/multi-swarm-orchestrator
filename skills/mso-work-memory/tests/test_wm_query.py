"""wm_query.py — .nt 정본을 변환 없이 RDF 저장소에 적재해 SPARQL 로 질의한다 (v0.16.0)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
import wm_query  # noqa: E402
import wm_store  # noqa: E402

try:
    import pyoxigraph  # noqa: F401
    BACKENDS = ["pyoxigraph", "rdflib"]
except ImportError:  # pragma: no cover
    BACKENDS = ["rdflib"]

OLD = "2026-06-01T00:00:00Z"
WM = wm_store.WM


def entry(eid, etype, desc, relations=None, metadata=None, node=None, author=None, tags=None, created=OLD):
    e = {"id": eid, "type": etype, "description": desc, "content": "본문", "tags": tags or [], "created_at": created,
         "relations": relations or [], "metadata": {"scope": ["repository"], **(metadata or {})}}
    if node:
        e["node"] = node
    if author:
        e["author"] = author
    return e


DIRS = {"release-note": "release-record", "episode": "insight-record", "pattern": "insight-record", "principle": "insight-record"}


def seed(root: Path, entries, fmt="nt"):
    for e in entries:
        d = root / DIRS.get(e["type"], "track-record")
        if fmt == "nt":
            wm_store.append_entry(d / f"{e['type']}.nt", e)
        else:
            d.mkdir(parents=True, exist_ok=True)
            with open(d / f"{e['type']}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")


LIFECYCLE = [
    entry("RN-000000000001", "release-note", "r9", metadata={"version": "0.9.0", "kind": "release", "released_at": "2026-06-01T00:00:00Z"}),
    entry("RN-000000000002", "release-note", "r15", metadata={"version": "0.15.0", "kind": "release", "released_at": "2026-06-03T00:00:00Z"}),
    entry("RN-000000000003", "release-note", "r10", metadata={"version": "0.10.0", "kind": "release", "released_at": "2026-06-02T00:00:00Z"}),
    entry("RN-000000000004", "release-note", "rollback of r10", metadata={"version": "0.10.1", "kind": "rollback", "released_at": "2026-06-04T00:00:00Z"},
          relations=[{"type": "rolls-back", "target": "RN-000000000003"}]),
    entry("UD-000000000001", "user-decision", "invalidated in 0.15",
          relations=[{"type": "verified-in", "target": "RN-000000000001"}, {"type": "invalidated-by", "target": "RN-000000000002"}]),
    entry("UD-000000000002", "user-decision", "newer", relations=[{"type": "supersedes", "target": "UD-000000000003"}]),
    entry("UD-000000000003", "user-decision", "older (superseded)"),
    entry("UD-000000000004", "user-decision", "held: invalidation rolled back", relations=[{"type": "invalidated-by", "target": "RN-000000000003"}]),
    entry("UD-000000000005", "user-decision", "plain"),
    entry("UD-000000000006", "user-decision", "released in 0.10 and 0.9 (earliest wins)",
          relations=[{"type": "released-in", "target": "RN-000000000003"}, {"type": "verified-in", "target": "RN-000000000001"}]),
]

DERIVED = ["validity", "supersededBy", "versionKey", "validFromVersion", "validFromKey", "invalidatedInVersion", "invalidatedInKey"]


def derived_triples_from_sparql(backend):
    preds = " ".join(f"wm:{p}" for p in DERIVED)
    _, rows = backend.select(f"PREFIX wm:<{WM}> SELECT ?s ?p ?o WHERE {{ VALUES ?p {{ {preds} }} ?s ?p ?o }}")
    return {(s, p, o) for s, p, o in rows}


def derived_triples_from_python_projection(root):
    import wm_to_ttl
    graph, _issues = wm_to_ttl.build_graph(root)
    wanted = {WM + p for p in DERIVED}
    return {(str(s), str(p), str(o)) for s, p, o in graph if str(p) in wanted}


@pytest.mark.parametrize("backend", BACKENDS)
def test_sparql_derive_matches_the_python_derivation_exactly(tmp_path, backend):
    """상태 도출 규칙이 SPARQL(derive.rq)과 Python(wm_release/wm_to_ttl) 두 곳에 있으므로 같은 결과를 내는지 고정한다."""
    root = tmp_path / "wm"
    seed(root, LIFECYCLE)
    store = wm_query.build(root, backend)
    sparql = derived_triples_from_sparql(store)
    python = derived_triples_from_python_projection(root)
    assert sparql == python
    assert any(p == WM + "validity" and o == "suspended" for _s, p, o in sparql)     # 롤백 연쇄가 실제로 시험된다
    assert any(p == WM + "validFromKey" and o == "9000" for _s, p, o in sparql)      # 가장 이른 버전(0.9.0 < 0.10.0)


@pytest.mark.parametrize("backend", BACKENDS)
def test_named_queries_run_on_the_raw_nt_store(tmp_path, backend):
    root = tmp_path / "wm"
    seed(root, LIFECYCLE + [entry("UD-000000000009", "user-decision", "mapped", node=["discovery-s-001"])])
    def ids(name, **params):
        store = wm_query.build(root, backend)
        _vars, rows = store.select(wm_query.render_query(wm_query.load_named(name), params))
        return {r[0] for r in rows}
    active = ids("memory-active")
    assert "UD-000000000002" in active and "UD-000000000004" in active           # suspended 는 남긴다
    assert "UD-000000000001" not in active and "UD-000000000003" not in active   # invalidated / superseded 는 제외
    assert ids("memory-for-node", node="discovery-s-001") == {"UD-000000000009"}
    assert ids("memory-for-node") == {"UD-000000000009"}                         # 기본값
    at_14 = ids("memory-valid-at-version", atKey="14000")
    assert "UD-000000000001" in at_14 and "UD-000000000005" in at_14             # 0.9.0 이후, 0.15.0 이전
    assert "UD-000000000001" not in ids("memory-valid-at-version", atKey="15000")    # 0.15.0 에서 무효화
    assert ids("release-current") == {"RN-000000000002"}                         # 롤백된 0.10.0 과 rollback RN 은 제외


def test_placeholders_defaults_and_missing_required_param():
    assert wm_query.render_query("A {{x:1}} B {{y}}", {"y": "2"}) == "A 1 B 2"
    assert wm_query.render_query("{{x:1}}", {"x": "9"}) == "9"
    with pytest.raises(SystemExit):
        wm_query.render_query("{{need}}")


@pytest.mark.parametrize("backend", BACKENDS)
def test_legacy_jsonl_and_nt_are_queried_together(tmp_path, backend):
    root = tmp_path / "wm"
    seed(root, [entry("UD-000000000001", "user-decision", "nt 기록")], "nt")
    seed(root, [dict(entry("IN-0001", "issue-note", "옛 jsonl 기록"), description=None, title="옛 jsonl 기록", text="x",
                     metadata={"severity": "minor", "status": "open", "reporter": "user", "scope": ["repository"]})], "jsonl")
    store = wm_query.build(root, backend)
    _v, rows = store.select(f"PREFIX wm:<{WM}> SELECT ?id ?d WHERE {{ ?e wm:entryId ?id ; wm:description ?d }} ORDER BY ?id")
    assert dict(map(tuple, rows)) == {"IN-0001": "옛 jsonl 기록", "UD-000000000001": "nt 기록"}


@pytest.mark.parametrize("backend", BACKENDS)
def test_agents_ownership_background_modules_and_related_nodes_are_queryable(tmp_path, backend):
    root = tmp_path / "wm"
    root.mkdir()
    (root / "agents.yaml").write_text(
        "agents:\n  - {id: alice, kind: user}\n  - {id: claude-code, kind: softwareAgent, onBehalfOf: alice}\n"
        "  - {id: stop-hook, kind: backgroundAgent, onBehalfOf: alice, trigger: hook}\n", encoding="utf-8")
    seed(root, [entry("IN-000000000001", "issue-note", "i", author="stop-hook", node=["discovery-s-001"],
                      metadata={"reporter": "claude-code", "severity": "minor", "status": "open", "module": "docs"})])
    store = wm_query.build(root, backend)
    _v, rows = store.select(f"""PREFIX wm:<{WM}>
        SELECT ?id ?owner ?trigger WHERE {{ ?a a wm:BackgroundAgent ; wm:agentId ?id ; wm:onBehalfOf ?o ; wm:trigger ?trigger . ?o wm:agentId ?owner }}""")
    assert rows == [["stop-hook", "alice", "hook"]]                                # 백그라운드 에이전트와 소속(계정 주인)
    _v, rows = store.select(f"PREFIX wm:<{WM}> SELECT ?m WHERE {{ ?e wm:inModule ?mod . ?mod a wm:Module ; wm:moduleId ?m }}")
    assert rows == [["docs"]]
    _v, rows = store.select(f"PREFIX wm:<{WM}> SELECT ?n WHERE {{ ?e wm:relatedNode ?n }}")
    assert rows == [["https://mso.dev/ontology/workflow#node/discovery-s-001"]]


def test_backends_return_identical_results(tmp_path):
    if len(BACKENDS) < 2:
        pytest.skip("pyoxigraph 미설치")
    root = tmp_path / "wm"
    seed(root, LIFECYCLE)
    results = []
    for backend in BACKENDS:
        store = wm_query.build(root, backend)
        _v, rows = store.select(f"PREFIX wm:<{WM}> SELECT ?id ?v WHERE {{ ?e wm:entryId ?id ; wm:validity ?v }} ORDER BY ?id")
        results.append(rows)
    assert results[0] == results[1]


def run_cli(root, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / "wm_query.py"), *args], capture_output=True, text=True,
                          env={**os.environ, "WORKMEM_DIR": str(root)})


def test_cli_list_run_formats_and_errors(tmp_path):
    root = tmp_path / "wm"
    seed(root, LIFECYCLE)
    listing = run_cli(root, "list")
    assert listing.returncode == 0 and "memory-active" in listing.stdout and "derive" not in listing.stdout.split()
    table = run_cli(root, "run", "memory-active")
    assert table.returncode == 0 and "UD-000000000002" in table.stdout and "UD-000000000003" not in table.stdout
    as_json = json.loads(run_cli(root, "run", "memory-active", "--format", "json").stdout)
    assert {r["id"] for r in as_json} >= {"UD-000000000002", "UD-000000000005"}
    tsv = run_cli(root, "run", "--sparql", f"PREFIX wm:<{WM}> SELECT ?id WHERE {{ ?e wm:entryId ?id }} ORDER BY ?id LIMIT 2", "--format", "tsv")
    assert tsv.stdout.splitlines()[0] == "id" and len(tsv.stdout.splitlines()) == 3
    assert run_cli(root, "run", "no-such-query").returncode != 0
    assert run_cli(root, "run").returncode != 0                                   # 질의 미지정
    p = run_cli(root, "run", "memory-valid-at-version", "--param", "atKey=15000", "--format", "tsv")
    assert "UD-000000000001" not in p.stdout


def test_missing_pyoxigraph_falls_back_to_rdflib(tmp_path, monkeypatch):
    root = tmp_path / "wm"
    seed(root, LIFECYCLE)
    import builtins
    real_import = builtins.__import__
    def fake(name, *a, **k):
        if name == "pyoxigraph":
            raise ImportError("blocked")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    store = wm_query.make_backend("auto")
    assert store.name == "rdflib"
    with pytest.raises(SystemExit):
        wm_query.make_backend("pyoxigraph")
