import json
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "wm_to_ttl.py"


def _write_entry(root: Path, rel_dir: str, entry: dict):
    target = root / rel_dir / f"{entry['id']}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def test_wm_to_ttl_validates_lifecycle_and_external_reference(tmp_path):
    workmem = tmp_path / "work-memory"
    issue = {
        "id": "IN-0001",
        "type": "issue-note",
        "title": "Issue",
        "text": "Something broke.",
        "tags": ["test"],
        "created_at": "2026-06-27T00:00:00Z",
        "relations": [
            {"type": "resolved-by", "target": "TS-0001"},
            {"type": "references", "target": "docs/spec.md"},
        ],
        "metadata": {"severity": "major"},
    }
    fix = {
        "id": "TS-0001",
        "type": "trouble-shooting",
        "title": "Fix",
        "text": "Fixed it.",
        "tags": ["test"],
        "created_at": "2026-06-27T00:01:00Z",
        "relations": [{"type": "caused-by", "target": "IN-0001"}],
        "metadata": {"resolution": "patched", "root_cause": "bug", "prevention": "test"},
    }
    _write_entry(workmem, "track-record/issue-note", issue)
    _write_entry(workmem, "track-record/trouble-shooting", fix)

    ttl_out = tmp_path / "work-memory.abox.ttl"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(workmem), "--ttl-out", str(ttl_out)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    ttl = ttl_out.read_text(encoding="utf-8")
    assert "wm:IssueNote" in ttl
    assert "wm:TroubleShooting" in ttl
    assert "wm:ExternalReference" in ttl
    assert "resolvedBy" in ttl


def test_wm_to_ttl_validates_release_lifecycle(tmp_path):
    workmem = tmp_path / "work-memory"
    fix = {
        "id": "TS-0001",
        "type": "trouble-shooting",
        "title": "Fix",
        "text": "Fixed it.",
        "tags": [],
        "created_at": "2026-07-17T00:00:00Z",
        "relations": [{"type": "released-in", "target": "RN-0001"}],
        "metadata": {"resolution": "patched", "root_cause": "bug", "prevention": "test"},
    }
    principle = {
        "id": "PR-0001",
        "type": "principle",
        "title": "Old rule",
        "text": "No longer holds after v0.7.0.",
        "tags": [],
        "created_at": "2026-07-17T00:00:00Z",
        "relations": [{"type": "invalidated-by", "target": "RN-0001"}],
        "metadata": {"statement": "old rule", "scope": "project", "status": "deprecated"},
    }
    release = {
        "id": "RN-0001",
        "type": "release-note",
        "title": "v0.7.0 release",
        "text": "Shipped the fix.",
        "tags": ["release"],
        "created_at": "2026-07-17T00:01:00Z",
        "relations": [],
        "metadata": {"version": "0.7.0", "released_at": "2026-07-17T00:01:00Z", "kind": "release", "scope": "project"},
    }
    rollback = {
        "id": "RN-0002",
        "type": "release-note",
        "title": "rollback v0.7.0",
        "text": "Rolled back.",
        "tags": ["release", "rollback"],
        "created_at": "2026-07-17T01:00:00Z",
        "relations": [{"type": "rolls-back", "target": "RN-0001"}],
        "metadata": {"version": "0.7.0-rollback", "released_at": "2026-07-17T01:00:00Z", "kind": "rollback", "scope": "project"},
    }
    _write_entry(workmem, "track-record/trouble-shooting", fix)
    _write_entry(workmem, "insight-record/principle", principle)
    _write_entry(workmem, "release-record/release-note", release)
    _write_entry(workmem, "release-record/release-note", rollback)

    ttl_out = tmp_path / "work-memory.abox.ttl"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(workmem), "--ttl-out", str(ttl_out)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    ttl = ttl_out.read_text(encoding="utf-8")
    assert "wm:ReleaseNote" in ttl
    assert "releasedIn" in ttl
    assert "invalidatedBy" in ttl
    assert "rollsBack" in ttl


def test_wm_to_ttl_rejects_rolls_back_from_non_release_note(tmp_path):
    workmem = tmp_path / "work-memory"
    fix = {
        "id": "TS-0001",
        "type": "trouble-shooting",
        "title": "Fix",
        "text": "Fixed it.",
        "tags": [],
        "created_at": "2026-07-17T00:00:00Z",
        "relations": [{"type": "rolls-back", "target": "RN-0001"}],
        "metadata": {"resolution": "patched", "root_cause": "bug", "prevention": "test"},
    }
    release = {
        "id": "RN-0001",
        "type": "release-note",
        "title": "v0.7.0 release",
        "text": "Shipped.",
        "tags": [],
        "created_at": "2026-07-17T00:01:00Z",
        "relations": [],
        "metadata": {"version": "0.7.0", "released_at": "2026-07-17T00:01:00Z", "kind": "release", "scope": "project"},
    }
    _write_entry(workmem, "track-record/trouble-shooting", fix)
    _write_entry(workmem, "release-record/release-note", release)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(workmem)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "TS-0001" in result.stdout
    assert "ReleaseNote" in result.stdout


def test_wm_to_ttl_rejects_wrong_invalidated_by_target_type(tmp_path):
    workmem = tmp_path / "work-memory"
    principle = {
        "id": "PR-0001",
        "type": "principle",
        "title": "Rule",
        "text": "Invalidated by a non-release target (invalid).",
        "tags": [],
        "created_at": "2026-07-17T00:00:00Z",
        "relations": [{"type": "invalidated-by", "target": "TS-0001"}],
        "metadata": {"statement": "rule", "scope": "project", "status": "accepted"},
    }
    fix = {
        "id": "TS-0001",
        "type": "trouble-shooting",
        "title": "Fix",
        "text": "Fixed it.",
        "tags": [],
        "created_at": "2026-07-17T00:01:00Z",
        "relations": [],
        "metadata": {"resolution": "patched", "root_cause": "bug", "prevention": "test"},
    }
    _write_entry(workmem, "insight-record/principle", principle)
    _write_entry(workmem, "track-record/trouble-shooting", fix)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(workmem)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "invalidatedBy" in result.stdout


def test_wm_to_ttl_rejects_wrong_resolved_by_target_type(tmp_path):
    workmem = tmp_path / "work-memory"
    issue = {
        "id": "IN-0001",
        "type": "issue-note",
        "title": "Issue",
        "text": "Something broke.",
        "tags": [],
        "created_at": "2026-06-27T00:00:00Z",
        "relations": [{"type": "resolved-by", "target": "AD-0001"}],
        "metadata": {},
    }
    decision = {
        "id": "AD-0001",
        "type": "agent-decision",
        "title": "Decision",
        "text": "Chose a path.",
        "tags": [],
        "created_at": "2026-06-27T00:01:00Z",
        "relations": [],
        "metadata": {"rationale": "fast", "alternatives": ["a"], "confidence": "high"},
    }
    _write_entry(workmem, "track-record/issue-note", issue)
    _write_entry(workmem, "track-record/agent-decision", decision)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(workmem)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "resolvedBy" in result.stdout


# ── v0.16.0: description/content, 파생 validity, 버전 정렬 키, related node ──

def _sparql(ttl_path: Path, query: str):
    from rdflib import Graph
    g = Graph().parse(ttl_path, format="turtle")
    return [tuple(str(v) if v is not None else None for v in row) for row in g.query(query)]


def _project(workmem: Path, entries: list[dict], tmp_path: Path) -> Path:
    for entry in entries:
        _write_entry(workmem, "track-record", entry)
    out = tmp_path / "wm.ttl"
    result = subprocess.run([sys.executable, str(SCRIPT), "project", str(workmem), "-o", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return out


def _e(eid, etype, desc, relations=None, **extra):
    return {"id": eid, "type": etype, "description": desc, "content": "body", "tags": [],
            "created_at": "2026-06-27T00:00:00Z", "relations": relations or [], "metadata": {}, **extra}


def test_projection_emits_description_content_and_falls_back_for_legacy(tmp_path):
    workmem = tmp_path / "work-memory"
    legacy = {"id": "IN-0002", "type": "issue-note", "title": "옛 제목", "text": "옛 본문", "tags": [],
              "created_at": "2026-06-27T00:00:00Z", "relations": [], "metadata": {}}
    ttl = _project(workmem, [_e("IN-0001", "issue-note", "새 설명"), legacy], tmp_path)
    rows = dict((r[0], r[1:]) for r in _sparql(ttl, """
        PREFIX wm: <https://mso.dev/ontology/work-memory#>
        SELECT ?id ?d ?c WHERE { ?e wm:entryId ?id ; wm:description ?d ; wm:content ?c }"""))
    assert rows["IN-0001"] == ("새 설명", "body")
    assert rows["IN-0002"] == ("옛 제목", "옛 본문")
    # 옛 predicate 는 더 이상 내보내지 않는다
    assert _sparql(ttl, "PREFIX wm: <https://mso.dev/ontology/work-memory#> SELECT ?e WHERE { ?e wm:title ?t }") == []


def test_projection_validity_supersedes_and_rollback_cascade(tmp_path):
    workmem = tmp_path / "work-memory"
    entries = [
        _e("UD-0001", "user-decision", "old", relations=[{"type": "invalidated-by", "target": "RN-0001"}]),
        _e("UD-0002", "user-decision", "newer", relations=[{"type": "supersedes", "target": "UD-0003"}]),
        _e("UD-0003", "user-decision", "older"),
        _e("UD-0004", "user-decision", "held", relations=[{"type": "invalidated-by", "target": "RN-0002"}]),
        _e("RN-0001", "release-note", "r1", metadata={"version": "0.9.0"}),
        _e("RN-0002", "release-note", "r2", metadata={"version": "0.10.0"}),
        _e("RN-0003", "release-note", "rb", relations=[{"type": "rolls-back", "target": "RN-0002"}],
           metadata={"version": "0.10.1", "kind": "rollback"}),
    ]
    ttl = _project(workmem, entries, tmp_path)
    validity = dict(_sparql(ttl, """
        PREFIX wm: <https://mso.dev/ontology/work-memory#>
        SELECT ?id ?v WHERE { ?e wm:entryId ?id ; wm:validity ?v }"""))
    assert validity["UD-0001"] == "invalidated"
    assert validity["UD-0003"] == "superseded" and validity["UD-0002"] == "active"
    assert validity["UD-0004"] == "suspended"  # 대상 RN 이 롤백됨

    active = {r[0] for r in _sparql(ttl, (Path(SCRIPT).parent.parent / "references/queries/memory-active.rq").read_text())}
    assert "UD-0002" in active and "UD-0004" in active
    assert "UD-0001" not in active and "UD-0003" not in active
    sup = _sparql(ttl, """
        PREFIX wm: <https://mso.dev/ontology/work-memory#>
        SELECT ?id ?by WHERE { ?e wm:entryId ?id ; wm:supersededBy ?n . ?n wm:entryId ?by }""")
    assert sup == [("UD-0003", "UD-0002")]


def test_version_key_orders_numerically_not_lexically(tmp_path):
    workmem = tmp_path / "work-memory"
    entries = [
        _e("RN-0001", "release-note", "old", metadata={"version": "0.9.0"}),
        _e("RN-0002", "release-note", "new", metadata={"version": "0.15.0"}),
        _e("UD-0001", "user-decision", "since 0.9, invalidated in 0.15",
           relations=[{"type": "verified-in", "target": "RN-0001"}, {"type": "invalidated-by", "target": "RN-0002"}]),
    ]
    ttl = _project(workmem, entries, tmp_path)
    keys = dict(_sparql(ttl, """
        PREFIX wm: <https://mso.dev/ontology/work-memory#>
        SELECT ?id ?k WHERE { ?e wm:entryId ?id ; wm:versionKey ?k }"""))
    assert int(keys["RN-0001"]) < int(keys["RN-0002"])          # 9 < 15 (사전순이면 반대)
    assert keys["RN-0001"] == "9000" and keys["RN-0002"] == "15000"
    row = _sparql(ttl, """
        PREFIX wm: <https://mso.dev/ontology/work-memory#>
        SELECT ?fv ?fk ?iv ?ik WHERE { ?e wm:entryId "UD-0001" ;
            wm:validFromVersion ?fv ; wm:validFromKey ?fk ; wm:invalidatedInVersion ?iv ; wm:invalidatedInKey ?ik }""")
    assert row == [("0.9.0", "9000", "0.15.0", "15000")]


def test_related_node_projection(tmp_path):
    workmem = tmp_path / "work-memory"
    ttl = _project(workmem, [_e("UD-0001", "user-decision", "mapped", node=["discovery-s-001"])], tmp_path)
    rows = _sparql(ttl, """
        PREFIX wm: <https://mso.dev/ontology/work-memory#>
        SELECT ?nid ?n WHERE { ?e wm:relatedNodeId ?nid ; wm:relatedNode ?n }""")
    assert rows == [("discovery-s-001", "https://mso.dev/ontology/workflow#node/discovery-s-001")]
    import wm_query
    q = wm_query.render_query((Path(SCRIPT).parent.parent / "references/queries/memory-for-node.rq").read_text())
    assert [r[0] for r in _sparql(ttl, q)] == ["UD-0001"]


def test_shacl_rejects_description_over_200(tmp_path):
    workmem = tmp_path / "work-memory"
    _write_entry(workmem, "track-record", _e("IN-0001", "issue-note", "가" * 201))
    result = subprocess.run([sys.executable, str(SCRIPT), "validate", str(workmem)],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "Conforms: False" in result.stdout or "200" in result.stdout
    ok_root = tmp_path / "ok"
    _write_entry(ok_root, "track-record", _e("IN-0001", "issue-note", "가" * 200))
    ok = subprocess.run([sys.executable, str(SCRIPT), "validate", str(ok_root)], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout


def test_version_filter_query_selects_entries_valid_at_version(tmp_path):
    workmem = tmp_path / "work-memory"
    entries = [
        _e("RN-0001", "release-note", "r", metadata={"version": "0.9.0"}),
        _e("RN-0002", "release-note", "r", metadata={"version": "0.15.0"}),
        _e("UD-0001", "user-decision", "valid 0.9..0.14",
           relations=[{"type": "verified-in", "target": "RN-0001"}, {"type": "invalidated-by", "target": "RN-0002"}]),
        _e("UD-0002", "user-decision", "no version info"),
    ]
    ttl = _project(workmem, entries, tmp_path)
    import wm_query
    raw = (Path(SCRIPT).parent.parent / "references/queries/memory-valid-at-version.rq").read_text()
    ids = {r[0] for r in _sparql(ttl, wm_query.render_query(raw))}                 # 기준 V = 0.14.4 (14004, 기본값)
    assert "UD-0001" in ids and "UD-0002" in ids              # 0.9.0 이후, 0.15.0 이전
    ids15 = {r[0] for r in _sparql(ttl, wm_query.render_query(raw, {"atKey": "15000"}))}
    assert "UD-0001" not in ids15                              # 0.15.0 에서 무효화됨
