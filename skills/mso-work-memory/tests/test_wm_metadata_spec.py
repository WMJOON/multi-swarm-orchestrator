"""타입별 metadata 명세 (references/metadata-spec.yaml) — 검사, TTL 투영, 생성 파일 동기화 (v0.16.0)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
import wm_metadata  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import wm_store  # noqa: E402


def _nt_entries(workmem, type_dir, type_name):
    """new 가 만든 큐레이션 기록(.nt)을 읽는다."""
    return wm_store.load_nt_entries(workmem / type_dir / f"{type_name}.nt")[0]


TO_TTL = SCRIPTS / "wm_to_ttl.py"
NODE = SCRIPTS / "wm_node.py"
GEN = SCRIPTS / "wm_gen_vocab.py"
NEW = "2026-11-18T00:00:00Z"   # enforce_from 이후
OLD = "2026-06-01T00:00:00Z"   # enforce_from 이전
WMNS = "https://mso.dev/ontology/work-memory#"
IDNS = "https://mso.dev/id/"


def entry(eid, etype, metadata, created_at=NEW, **extra):
    # scope 는 모든 타입의 필수 metadata 라 기본으로 채운다(필수 시험은 scope 를 빼서 따로 한다)
    return {"id": eid, "type": etype, "description": "d", "content": "c", "tags": [],
            "created_at": created_at, "relations": [], "metadata": {"scope": "repository", **metadata}, **extra}


def write(root: Path, e: dict):
    path = root / ("release-record" if e["type"] == "release-note" else "track-record") / f"{e['type']}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")


def project(root: Path, out: Path) -> Path:
    r = subprocess.run([sys.executable, str(TO_TTL), "project", str(root), "-o", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return out


def query(ttl: Path, q: str):
    from rdflib import Graph
    g = Graph().parse(ttl, format="turtle")
    return [tuple(str(v) if v is not None else None for v in row) for row in g.query(q)]


# ── 검사기 ──

def levels(e):
    return [(lvl, msg) for lvl, msg in wm_metadata.check_entry(e)]


def test_new_issue_note_requires_reporter_severity_status():
    errors = [m for lvl, m in levels(entry("IN-1", "issue-note", {})) if lvl == "error"]
    assert any("reporter" in m for m in errors) and any("severity" in m for m in errors) and any("status" in m for m in errors)


def test_old_issue_note_missing_metadata_is_only_a_warning():
    found = levels(entry("IN-1", "issue-note", {}, created_at=OLD))
    assert found and all(lvl == "warn" for lvl, _ in found)


def test_needs_review_downgrades_new_record_errors_to_warnings():
    found = levels(entry("IN-1", "issue-note", {"needs_review": True}))
    assert found and all(lvl == "warn" for lvl, _ in found)


def test_controlled_vocabulary_and_types_are_enforced_on_new_records():
    bad = entry("IN-1", "issue-note", {"reporter": "user", "severity": "huge", "status": "open"})
    assert any(lvl == "error" and "severity" in m and "허용" in m for lvl, m in levels(bad))
    good = entry("IN-1", "issue-note", {"reporter": "user", "severity": "major", "status": "partially-resolved"})
    assert [x for x in levels(good) if x[0] == "error"] == []
    ts = entry("TS-1", "trouble-shooting", {"resolution": "r", "root_cause": "c"})
    assert [x for x in levels(ts) if x[0] == "error"] == []
    assert any("boolean" in m or "true/false" in m for _, m in levels(entry("UD-1", "user-decision", {"rationale": "r", "structural": "yes"})))
    assert any("정수" in m for _, m in levels(entry("PT-1", "pattern", {"context": "c", "frequency": "many"})))


def test_unknown_metadata_key_warns_never_errors():
    found = levels(entry("UD-1", "user-decision", {"rationale": "r", "path_missing_acknowledged": True}))
    assert ("warn", "metadata.path_missing_acknowledged 는 명세에 없는 키 (user-decision)") in found
    assert [x for x in found if x[0] == "error"] == []


def test_legacy_free_text_confidence_resolves_by_leading_token():
    spec = wm_metadata.load_spec()
    assert wm_metadata.normalize_vocab(spec, "confidence", "medium (push 전)") == "medium"
    assert wm_metadata.normalize_vocab(spec, "issueStatus", "partially-resolved") == "partiallyResolved"
    assert wm_metadata.normalize_vocab(spec, "confidence", "아주 높음") is None


def test_runtime_types_are_exempt():
    assert wm_metadata.check_entry({"id": "AU-1", "type": "auditlog", "metadata": {"x": 1}, "created_at": NEW}) == []


# ── wm_node validate/new 연동 ──

def run_node(root, *args):
    return subprocess.run([sys.executable, str(NODE), *args], capture_output=True, text=True,
                          env={**os.environ, "WORKMEM_DIR": str(root)})


def test_validate_reports_new_record_errors_and_old_record_warnings(tmp_path):
    root = tmp_path / "wm"
    write(root, entry("IN-0001", "issue-note", {}, created_at=OLD))
    ok = run_node(root, "validate", str(root))
    assert ok.returncode == 0 and "⚠" in ok.stdout and "경고" in ok.stdout
    write(root, entry("IN-0002", "issue-note", {}, created_at=NEW))
    bad = run_node(root, "validate", str(root))
    assert bad.returncode != 0 and "[META] issue-note.jsonl:2" in bad.stdout


def test_new_fills_derivable_defaults_and_refuses_missing_required(tmp_path):
    root = tmp_path / "wm"
    refused = run_node(root, "new", "issue-note", "--description", "x")
    assert refused.returncode != 0 and "severity" in refused.stderr and "scope" in refused.stderr and "--allow-incomplete" in refused.stderr
    assert not (root / "track-record").exists()
    ok = run_node(root, "new", "issue-note", "--description", "x", "--meta", "severity=minor", "--scope", "repository", "--author", "user")
    assert ok.returncode == 0, ok.stderr
    md = wm_store.load_nt_entries(root / "track-record" / "issue-note.nt")[0][0]["metadata"]
    assert md == {"scope": ["repository"], "reporter": "user", "status": "open", "severity": "minor"}     # reporter=author, status=open 기본
    assert run_node(root, "validate", str(root)).returncode == 0


# ── TTL 투영 ──

def test_projection_uses_slash_iris_and_object_properties_for_vocab_and_agents(tmp_path):
    root = tmp_path / "wm"
    write(root, entry("IN-0001", "issue-note",
                      {"reporter": "user", "severity": "major", "status": "partially-resolved", "module": "mso-work-memory"},
                      author="agent"))
    ttl = project(root, tmp_path / "wm.ttl")
    rows = query(ttl, f"""PREFIX wm: <{WMNS}>
        SELECT ?e ?sev ?st ?rep ?mod ?au WHERE {{ ?e wm:severity ?sev ; wm:status ?st ; wm:reportedBy ?rep ;
            wm:inModule ?mod ; wm:author ?au }}""")
    assert rows == [(IDNS + "memory/IN-0001", IDNS + "vocab/severity/major", IDNS + "vocab/issueStatus/partiallyResolved",
                     IDNS + "agent/user", IDNS + "module/mso-work-memory", IDNS + "agent/agent")]
    # 통제 어휘 값은 TBox 에서 선언된 individual 이다
    from rdflib import Graph
    tbox = Graph().parse(SKILL / "references/tbox/work-memory-metadata-tbox.ttl", format="turtle")
    from rdflib import URIRef, RDF
    assert (URIRef(IDNS + "vocab/severity/major"), RDF.type, URIRef(WMNS + "Severity")) in tbox
    assert (URIRef(IDNS + "vocab/issueStatus/partiallyResolved"), RDF.type, URIRef(WMNS + "IssueStatus")) in tbox


def test_projection_keeps_free_text_as_datatype_and_typed_literals(tmp_path):
    root = tmp_path / "wm"
    write(root, entry("TS-0001", "trouble-shooting", {"resolution": "patched", "root_cause": "bug"}))
    write(root, entry("PT-0001", "pattern", {"context": "c", "frequency": 3}))
    write(root, entry("RN-0001", "release-note", {"version": "0.9.0", "kind": "release", "released_at": NEW}))
    ttl = project(root, tmp_path / "wm.ttl")
    assert query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?r ?c WHERE {{ ?e wm:resolution ?r ; wm:rootCause ?c }}") == [("patched", "bug")]
    assert query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?f WHERE {{ ?e wm:frequency ?f . FILTER(DATATYPE(?f) = <http://www.w3.org/2001/XMLSchema#integer>) }}") == [("3",)]
    assert query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?k WHERE {{ ?e wm:releaseKind ?k }}") == [(IDNS + "vocab/releaseKind/release",)]
    assert len(query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?t WHERE {{ ?e wm:releasedAt ?t . FILTER(DATATYPE(?t) = <http://www.w3.org/2001/XMLSchema#dateTime>) }}")) == 1
    # 옛 `wm:metadata<Key>` 형태는 더 이상 내보내지 않는다
    assert query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?p WHERE {{ ?e ?p ?o . FILTER(STRSTARTS(STR(?p), '{WMNS}metadata') && STR(?p) != '{WMNS}metadata') }}") == []


def test_agent_ownership_and_background_agents_from_registry(tmp_path):
    root = tmp_path / "wm"
    (root).mkdir(parents=True)
    (root / "agents.yaml").write_text(
        "agents:\n"
        "  - {id: alice, kind: user}\n"
        "  - {id: claude-code, kind: softwareAgent, onBehalfOf: alice}\n"
        "  - {id: stop-hook, kind: backgroundAgent, onBehalfOf: alice, trigger: hook}\n", encoding="utf-8")
    write(root, entry("IN-0001", "issue-note", {"reporter": "alice", "severity": "minor", "status": "open"}, author="claude-code"))
    write(root, entry("IN-0002", "issue-note", {"reporter": "stop-hook", "severity": "minor", "status": "open"}, author="stop-hook"))
    ttl = project(root, tmp_path / "wm.ttl")
    owners = dict(query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?a ?o WHERE {{ ?a wm:onBehalfOf ?o }}"))
    assert owners[IDNS + "agent/claude-code"] == IDNS + "agent/alice"
    assert owners[IDNS + "agent/stop-hook"] == IDNS + "agent/alice"
    classes = {a: c for a, c in query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?a ?c WHERE {{ ?a a ?c . FILTER(?c IN (wm:User, wm:SoftwareAgent, wm:BackgroundAgent)) }}")}
    assert classes[IDNS + "agent/alice"] == WMNS + "User"
    bg = query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?a ?t WHERE {{ ?a a wm:BackgroundAgent ; wm:trigger ?t }}")
    assert bg == [(IDNS + "agent/stop-hook", "hook")]          # 백그라운드 에이전트는 별개로 구분된다


def test_builtin_agents_without_registry(tmp_path):
    root = tmp_path / "wm"
    write(root, entry("IN-0001", "issue-note", {"reporter": "user", "severity": "minor", "status": "open"}, author="agent"))
    ttl = project(root, tmp_path / "wm.ttl")
    rows = query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?a ?c WHERE {{ ?a a ?c . FILTER(?c IN (wm:User, wm:SoftwareAgent)) }}")
    assert (IDNS + "agent/user", WMNS + "User") in rows and (IDNS + "agent/agent", WMNS + "SoftwareAgent") in rows


# ── SHACL ──

def validate_ttl(root):
    return subprocess.run([sys.executable, str(TO_TTL), "validate", str(root)], capture_output=True, text=True)


def test_shacl_enforces_required_metadata_only_for_new_records(tmp_path):
    root = tmp_path / "wm"
    write(root, entry("IN-0001", "issue-note", {}, created_at=OLD))
    assert validate_ttl(root).returncode == 0                      # 옛 기록은 누락해도 통과
    write(root, entry("IN-0002", "issue-note", {}, created_at=NEW))
    bad = validate_ttl(root)
    assert bad.returncode != 0 and "metadata.severity 필수" in bad.stdout
    root2 = tmp_path / "wm2"
    write(root2, entry("IN-0002", "issue-note", {"needs_review": True}, created_at=NEW))
    assert validate_ttl(root2).returncode == 0                    # needs_review 는 면제


def test_shacl_accepts_complete_new_records_of_every_type(tmp_path):
    root = tmp_path / "wm"
    write(root, entry("IN-0001", "issue-note", {"reporter": "user", "severity": "minor", "status": "open"}))
    write(root, entry("AD-0001", "agent-decision", {"rationale": "r", "confidence": "high"}))
    write(root, entry("UD-0001", "user-decision", {"rationale": "r"}))
    write(root, entry("AR-0001", "alternatives-record", {"provided_by": "agent", "options": [{"n": 1, "name": "A"}]}))
    write(root, entry("TS-0001", "trouble-shooting", {"resolution": "r", "root_cause": "c"}))
    write(root, entry("RN-0001", "release-note", {"version": "1.0.0", "kind": "release"}))
    write(root, entry("EP-0001", "episode", {"event_date": NEW}))
    write(root, entry("PT-0001", "pattern", {"context": "c", "sources": ["EP-0001"]}))
    write(root, entry("PR-0001", "principle", {"statement": "s", "scope": "project", "status": "accepted"}))
    r = validate_ttl(root)
    assert r.returncode == 0, r.stdout
    assert run_node(root, "validate", str(root)).returncode == 0


def test_shacl_rejects_wrong_range_for_vocab_object(tmp_path):
    """통제 어휘 자리에 엉뚱한 개체가 들어오면 SHACL 이 잡는다(투영은 어휘 밖 값을 내보내지 않으므로 그래프를 직접 만든다)."""
    from rdflib import Graph, URIRef, RDF, Literal
    sys.path.insert(0, str(SCRIPTS))
    import wm_to_ttl
    g = Graph()
    e = URIRef(IDNS + "memory/IN-0001")
    g.add((e, RDF.type, URIRef(WMNS + "Entry"))); g.add((e, RDF.type, URIRef(WMNS + "IssueNote")))
    g.add((e, URIRef(WMNS + "entryId"), Literal("IN-0001"))); g.add((e, URIRef(WMNS + "typeName"), Literal("issue-note")))
    g.add((e, URIRef(WMNS + "description"), Literal("d"))); g.add((e, URIRef(WMNS + "content"), Literal("c")))
    g.add((e, URIRef(WMNS + "createdAt"), Literal(OLD)))
    g.add((e, URIRef(WMNS + "severity"), URIRef(IDNS + "vocab/issueStatus/open")))   # Severity 가 아니라 IssueStatus
    conforms, text = wm_to_ttl.validate_graph(g)
    assert not conforms and "severity" in text


# ── 생성 파일 동기화 ──

def test_generated_tbox_and_shapes_match_spec():
    r = subprocess.run([sys.executable, str(GEN), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_property_naming_convention_lower_camel_and_classes_upper_camel():
    import re
    from rdflib import Graph, RDF, OWL
    tbox = Graph().parse(SKILL / "references/tbox/work-memory-metadata-tbox.ttl", format="turtle")
    for s in tbox.subjects(RDF.type, OWL.ObjectProperty):
        assert re.fullmatch(r"[a-z][A-Za-z0-9]*", str(s).rsplit("#", 1)[1]), s
    for s in tbox.subjects(RDF.type, OWL.DatatypeProperty):
        assert re.fullmatch(r"[a-z][A-Za-z0-9]*", str(s).rsplit("#", 1)[1]), s
    for s in tbox.subjects(RDF.type, OWL.Class):
        assert re.fullmatch(r"[A-Z][A-Za-z0-9]*", str(s).rsplit("#", 1)[1]), s
    spec = wm_metadata.load_spec()
    for v in spec["vocabularies"].values():
        for item in v["values"]:
            assert re.fullmatch(r"[a-z][A-Za-z0-9]*", item["id"]), item


def test_severity_vocabulary_is_minor_major_critical_only():
    """정본 severity 어휘(결정: 2026-11-17). 옛 low/medium/high 는 새 기록에서 오류, 옛 기록에서 경고다."""
    spec = wm_metadata.load_spec()
    assert set(wm_metadata.vocab_values(spec, "severity")) == {"minor", "major", "critical"}
    assert wm_metadata.normalize_vocab(spec, "severity", "low") is None
    new = entry("IN-1", "issue-note", {"reporter": "user", "severity": "low", "status": "open"})
    assert any(lvl == "error" and "severity" in m for lvl, m in levels(new))
    old = entry("IN-1", "issue-note", {"reporter": "user", "severity": "low", "status": "open"}, created_at=OLD)
    assert all(lvl == "warn" for lvl, _ in levels(old))


def test_scope_is_mandatory_controlled_vocabulary_separate_from_scope_note(tmp_path):
    """scope(강제, 통제 어휘: 대상의 층)와 scope_note(자유 서술, skos:scopeNote)는 별개다."""
    root = tmp_path / "wm"
    write(root, entry("UD-0001", "user-decision", {"rationale": "r", "scope": "workflow", "scope_note": "authoring-workflow"}))
    write(root, entry("TS-0001", "trouble-shooting", {"resolution": "r", "root_cause": "c", "scope": "task"}))
    write(root, entry("RN-0001", "release-note", {"version": "1.0.0", "kind": "release", "scope": "repository"}))
    write(root, entry("PR-0001", "principle", {"statement": "s", "status": "accepted", "scope": "artifact"}))
    ttl = project(root, tmp_path / "wm.ttl")
    scopes = dict(query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?id ?s WHERE {{ ?e wm:entryId ?id ; wm:scope ?s }}"))
    assert scopes == {"UD-0001": IDNS + "vocab/scope/workflow", "TS-0001": IDNS + "vocab/scope/task",
                      "RN-0001": IDNS + "vocab/scope/repository", "PR-0001": IDNS + "vocab/scope/artifact"}
    notes = query(ttl, """PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX wm: <https://mso.dev/ontology/work-memory#>
        SELECT ?id ?n WHERE { ?e wm:entryId ?id ; skos:scopeNote ?n }""")
    assert notes == [("UD-0001", "authoring-workflow")]
    assert validate_ttl(root).returncode == 0


def test_missing_or_invalid_scope_is_an_error_for_new_records_and_warning_for_old(tmp_path):
    spec = wm_metadata.load_spec()
    assert set(wm_metadata.vocab_values(spec, "scope")) >= {"repository", "workflow", "task", "artifact", "directory"}
    no_scope = entry("UD-1", "user-decision", {"rationale": "r"})
    no_scope["metadata"].pop("scope")
    assert any(lvl == "error" and "scope 필수" in m for lvl, m in levels(no_scope))
    bad = entry("UD-1", "user-decision", {"rationale": "r", "scope": "everything"})
    assert any(lvl == "error" and "scope" in m for lvl, m in levels(bad))
    old = entry("UD-1", "user-decision", {"rationale": "r", "scope": "authoring-workflow"}, created_at=OLD)
    assert all(lvl == "warn" for lvl, _ in levels(old))
    root = tmp_path / "wm"
    write(root, no_scope)
    assert validate_ttl(root).returncode != 0                                           # SHACL 도 강제한다


def test_component_and_module_are_separate_properties(tmp_path):
    """component(구성요소 이름, 문자열)와 module(스캐폴드 index module id, 개체)은 별개다."""
    root = tmp_path / "wm"
    write(root, entry("IN-0001", "issue-note", {"reporter": "user", "severity": "minor", "status": "open",
                                                "component": "mso-repository-setup", "module": "docs"}))
    ttl = project(root, tmp_path / "wm.ttl")
    assert query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?c WHERE {{ ?e wm:component ?c }}") == [("mso-repository-setup",)]
    assert query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?m WHERE {{ ?e wm:inModule ?m }}") == [(IDNS + "module/docs",)]


def test_multiple_property_accepts_legacy_scalar_string():
    ad = entry("AD-1", "agent-decision", {"rationale": "r", "confidence": "high", "alternatives": "A 안 / B 안"})
    assert [x for x in levels(ad) if x[0] == "error"] == []


# ── scope 는 리스트(최소 1개) ──

def test_scope_accepts_list_with_at_least_one_value_and_scalar_legacy():
    ok_list = entry("UD-1", "user-decision", {"rationale": "r", "scope": ["repository", "workflow"]})
    assert [x for x in levels(ok_list) if x[0] == "error"] == []
    ok_scalar = entry("UD-1", "user-decision", {"rationale": "r", "scope": "task"})
    assert [x for x in levels(ok_scalar) if x[0] == "error"] == []
    empty = entry("UD-1", "user-decision", {"rationale": "r", "scope": []})
    assert any(lvl == "error" and "최소 1개" in m for lvl, m in levels(empty))
    one_bad = entry("UD-1", "user-decision", {"rationale": "r", "scope": ["repository", "everything"]})
    assert any(lvl == "error" and "everything" in m for lvl, m in levels(one_bad))


def test_scope_list_projects_one_triple_per_value_and_shacl_requires_at_least_one(tmp_path):
    root = tmp_path / "wm"
    write(root, entry("UD-0001", "user-decision", {"rationale": "r", "scope": ["repository", "workflow", "task"]}))
    ttl = project(root, tmp_path / "wm.ttl")
    got = sorted(r[0] for r in query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?s WHERE {{ ?e wm:scope ?s }}"))
    assert got == sorted(IDNS + f"vocab/scope/{v}" for v in ("repository", "workflow", "task"))
    assert validate_ttl(root).returncode == 0
    empty_root = tmp_path / "empty"
    write(empty_root, entry("UD-0001", "user-decision", {"rationale": "r", "scope": []}))
    bad = validate_ttl(empty_root)
    # 빈 리스트는 triple 이 없어 표현할 수 없다 — 투영 이슈로 막힌다(원문은 wm:unmapped 에 보존)
    assert bad.returncode != 0 and "metadata.scope" in (bad.stdout + bad.stderr)


def test_new_accepts_repeated_scope_and_dedups(tmp_path):
    root = tmp_path / "wm"
    ok = run_node(root, "new", "user-decision", "--description", "x", "--meta", "rationale=r",
                  "--scope", "repository", "--scope", "workflow", "--scope", "repository")
    assert ok.returncode == 0, ok.stderr
    md = wm_store.load_nt_entries(root / "track-record" / "user-decision.nt")[0][0]["metadata"]
    assert md["scope"] == ["repository", "workflow"]                               # 중복 제거, 순서 유지
    assert run_node(root, "validate", str(root)).returncode == 0


# ── alternatives-record 의 options 는 Option 노드로 구조화된다 ──

def ar(options, recommended=None, created_at=NEW):
    md = {"provided_by": "agent", "options": options}
    if recommended is not None:
        md["recommended"] = recommended
    return entry("AR-0001", "alternatives-record", md, created_at=created_at)


OPTS = [{"n": 1, "name": "A", "description": "첫째", "trade_off": "빠르지만 위험"},
        {"n": 2, "name": "B", "trade_off": "느리지만 안전"}]


def test_option_structure_is_validated_on_new_records():
    assert [x for x in levels(ar(OPTS, recommended=2)) if x[0] == "error"] == []
    assert any("name 필수" in m for lvl, m in levels(ar([{"n": 1}])) if lvl == "error")
    assert any("n 필수" in m for lvl, m in levels(ar([{"name": "A"}])) if lvl == "error")
    assert any("정수" in m for lvl, m in levels(ar([{"n": "one", "name": "A"}])) if lvl == "error")
    assert any("중복" in m for lvl, m in levels(ar([{"n": 1, "name": "A"}, {"n": 1, "name": "B"}])) if lvl == "error")
    assert any("객체여야" in m for lvl, m in levels(ar(["A", "B"])) if lvl == "error")
    assert any("최소 1개" in m for lvl, m in levels(ar([])) if lvl == "error")
    assert any(lvl == "warn" and "extra" in m for lvl, m in levels(ar([{"n": 1, "name": "A", "extra": 1}])))


def test_recommended_must_reference_an_existing_option():
    assert [x for x in levels(ar(OPTS, recommended=1)) if x[0] == "error"] == []
    bad = levels(ar(OPTS, recommended=9))
    assert any(lvl == "error" and "recommended=9" in m for lvl, m in bad)


def test_old_alternatives_record_with_incomplete_options_only_warns():
    assert all(lvl == "warn" for lvl, _ in levels(ar([{"n": 1}], created_at=OLD)))


def test_options_project_as_option_nodes_with_recommended_reference(tmp_path):
    root = tmp_path / "wm"
    write(root, ar(OPTS, recommended=2))
    ttl = project(root, tmp_path / "wm.ttl")
    base = IDNS + "memory/AR-0001/option/"
    rows = query(ttl, f"""PREFIX wm: <{WMNS}>
        SELECT ?o ?n ?name ?tradeOff WHERE {{ ?e wm:option ?o . ?o a wm:Option ; wm:optionNumber ?n ; wm:optionName ?name .
            OPTIONAL {{ ?o wm:tradeOff ?tradeOff }} }} ORDER BY ?n""")
    assert rows == [(base + "1", "1", "A", "빠르지만 위험"), (base + "2", "2", "B", "느리지만 안전")]
    assert query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?r WHERE {{ ?e wm:recommendedOption ?r }}") == [(base + "2",)]
    # 추천된 선택지의 트레이드오프를 한 번에 질의할 수 있다 (JSON 리터럴이면 불가능했다)
    assert query(ttl, f"""PREFIX wm: <{WMNS}>
        SELECT ?name ?t WHERE {{ ?e wm:recommendedOption ?o . ?o wm:optionName ?name ; wm:tradeOff ?t }}""") == [("B", "느리지만 안전")]
    typed = query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?n WHERE {{ ?o wm:optionNumber ?n . FILTER(DATATYPE(?n) = <http://www.w3.org/2001/XMLSchema#integer>) }}")
    assert len(typed) == 2
    assert validate_ttl(root).returncode == 0


def test_option_without_n_uses_position_and_option_shape_requires_key(tmp_path):
    root = tmp_path / "wm"
    write(root, ar([{"name": "A"}, {"name": "B"}], created_at=OLD))
    ttl = project(root, tmp_path / "wm.ttl")
    nums = sorted(r[0] for r in query(ttl, f"PREFIX wm: <{WMNS}> SELECT ?n WHERE {{ ?o wm:optionNumber ?n }}"))
    assert nums == ["1", "2"]                                  # 순번이 key 가 된다
    assert validate_ttl(root).returncode == 0                  # 옛 기록은 통과


def test_generated_option_vocabulary_naming():
    import re
    from rdflib import Graph, RDF, OWL
    tbox = Graph().parse(SKILL / "references/tbox/work-memory-metadata-tbox.ttl", format="turtle")
    from rdflib import URIRef
    assert (URIRef(WMNS + "Option"), RDF.type, OWL.Class) in tbox
    for p in ("optionNumber", "optionName", "optionDescription", "tradeOff"):
        assert (URIRef(WMNS + p), RDF.type, OWL.DatatypeProperty) in tbox, p
    assert (URIRef(WMNS + "option"), RDF.type, OWL.ObjectProperty) in tbox
    assert (URIRef(WMNS + "recommendedOption"), RDF.type, OWL.ObjectProperty) in tbox
