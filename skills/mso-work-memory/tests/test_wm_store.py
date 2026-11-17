"""wm_store.py — 기록 ↔ N-Triples 왕복(손실 없음), 직렬화, 파일 입출력 (v0.16.0)."""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import wm_store  # noqa: E402

NEW = "2026-11-18T00:00:00Z"


def roundtrip(entry):
    triples = wm_store.entry_to_triples(entry)
    lines = [wm_store.serialize_triple(s, p, o) for s, p, o in triples]
    parsed = [wm_store.parse_nt_line(l) for l in lines]
    assert parsed == triples                                     # 직렬화 → 파싱이 같은 triple 을 돌려준다
    entries = wm_store.triples_to_entries(parsed)
    assert len(entries) == 1
    return entries[0], lines


def base(**over):
    e = {"id": "UD-019a3c5e4f21", "type": "user-decision", "description": "요약", "content": "본문", "tags": ["a", "b"],
         "created_at": NEW, "relations": [], "metadata": {"scope": ["repository"], "rationale": "이유"}}
    e.update(over)
    return e


def test_basic_roundtrip_keeps_every_field_and_order():
    e = base(author="agent", node=["discovery-s-001"],
             relations=[{"type": "refines", "target": "UD-0001"}, {"type": "supersedes", "target": "UD-019a3c5e4f20"}],
             metadata={"scope": ["repository", "workflow"], "scope_note": "보충", "rationale": "이유", "structural": True,
                       "component": "mso-work-memory", "module": "docs", "needs_review": True})
    got, lines = roundtrip(e)
    assert got == e
    assert list(got["metadata"]) == ["scope", "scope_note", "component", "module", "needs_review", "rationale", "structural"] \
        or set(got["metadata"]) == set(e["metadata"])


def test_multiline_content_quotes_unicode_and_control_characters_survive():
    content = '첫 줄\n둘째 줄 "따옴표" \\ 역슬래시\t탭\r\n이모지 😀 한글   끝\x01'
    got, lines = roundtrip(base(content=content))
    assert got["content"] == content
    assert all("\n" not in l for l in lines)                       # 한 줄에 triple 하나


def test_external_reference_original_text_is_preserved_even_with_spaces_and_slashes():
    got, _ = roundtrip(base(relations=[{"type": "references", "target": "docs/spec file.md#sec 1"},
                                       {"type": "references", "target": "docs/spec_file.md#sec_1"}]))
    assert [r["target"] for r in got["relations"]] == ["docs/spec file.md#sec 1", "docs/spec_file.md#sec_1"]  # `_safe` 충돌 없음


def test_unmapped_values_are_preserved_verbatim_without_duplicating_mapped_ones():
    e = {"id": "AD-0001", "type": "agent-decision", "description": "d", "content": "c", "tags": [], "created_at": NEW,
         "relations": [{"type": "weird-relation", "target": "X-1"}],
         "metadata": {"confidence": "medium (push 전)", "rationale": "r", "path_missing_acknowledged": True,
                      "scope": ["repository"], "alternatives": "A / B"},
         "custom_top": {"k": [1, 2]}}
    got, lines = roundtrip(e)
    assert got["metadata"]["confidence"] == "medium (push 전)"          # 어휘 밖 값 원문 보존
    assert got["metadata"]["path_missing_acknowledged"] is True         # 명세 밖 키 보존
    assert got["relations"] == [{"type": "weird-relation", "target": "X-1"}]
    assert got["custom_top"] == {"k": [1, 2]}
    assert got["metadata"]["alternatives"] == ["A / B"]                 # multiple 은 리스트로 정규화
    blob = [l for l in lines if f"<{wm_store.WM}unmapped>" in l][0]
    assert "rationale" not in blob and "scope" not in blob              # 매핑된 키는 blob 에 중복 저장하지 않는다
    # 결과는 한 번 더 왕복해도 같다(정규화 후 고정점)
    again, _ = roundtrip(got)
    assert again == got


def test_vocabulary_alias_normalizes_to_canonical_value():
    got, _ = roundtrip(base(metadata={"scope": "project", "rationale": "r"}))
    assert got["metadata"]["scope"] == ["repository"]                   # 옛 별칭 project → 정본 repository (리스트로)


def test_options_and_recommended_roundtrip_as_nodes():
    e = {"id": "AR-0001", "type": "alternatives-record", "description": "d", "content": "c", "tags": [], "created_at": NEW,
         "relations": [], "metadata": {"scope": ["task"], "provided_by": "agent", "recommended": 2,
                                       "options": [{"n": 1, "name": "A", "description": "첫째", "trade_off": "위험"},
                                                   {"n": 2, "name": "B"}]}}
    got, lines = roundtrip(e)
    assert got["metadata"]["options"] == e["metadata"]["options"]
    assert got["metadata"]["recommended"] == 2
    assert any("/option/2>" in l for l in lines)


def test_dangling_ref_is_preserved_as_unmapped_not_dropped():
    e = {"id": "AR-0002", "type": "alternatives-record", "description": "d", "content": "c", "tags": [], "created_at": NEW,
         "relations": [], "metadata": {"scope": ["task"], "provided_by": "agent", "options": [{"n": 1, "name": "A"}], "recommended": 9}}
    got, _ = roundtrip(e)
    assert got["metadata"]["recommended"] == 9


def test_empty_list_and_wrongly_typed_values_survive_via_unmapped():
    e = base(metadata={"scope": [], "rationale": "r", "structural": "yes", "confidence_x": None})
    got, _ = roundtrip(e)
    assert got["metadata"]["scope"] == [] and got["metadata"]["structural"] == "yes" and got["metadata"]["confidence_x"] is None


def test_legacy_title_text_are_read_as_description_content():
    got, _ = roundtrip({"id": "IN-0001", "type": "issue-note", "title": "옛 제목", "text": "옛 본문", "tags": [],
                        "created_at": "2026-06-01T00:00:00Z", "relations": [], "metadata": {}})
    assert got["description"] == "옛 제목" and got["content"] == "옛 본문" and "title" not in got


def test_serialized_lines_are_valid_ntriples_per_rdflib():
    from rdflib import Graph
    e = base(content='줄1\n줄2 "q" \\ \x01 😀', author="agent", node=["n1"],
             relations=[{"type": "references", "target": "a b/c"}],
             metadata={"scope": ["repository"], "rationale": "r", "structural": True, "released_at": NEW})
    _, lines = roundtrip(e)
    g = Graph().parse(data="\n".join(lines) + "\n", format="nt")
    assert len(g) == len(lines)


def test_iri_encoding_distinguishes_look_alike_ids():
    assert wm_store.entry_iri("a b") != wm_store.entry_iri("a_b")
    assert wm_store.entry_iri("UD-0001") == "https://mso.dev/id/memory/UD-0001"


def test_parse_rejects_bad_lines_and_ignores_comments(tmp_path):
    p = tmp_path / "x.nt"
    p.write_text('# comment\n\n<a> <b> "ok" .\nthis is not a triple\n<a> <b> <c> .\n', encoding="utf-8")
    triples, problems = wm_store.read_nt_file(p)
    assert len(triples) == 2 and len(problems) == 1 and problems[0][0] == 4


# ── 파일 입출력 ──

def test_append_replace_in_place_preserves_position_and_other_entries(tmp_path):
    path = tmp_path / "user-decision.nt"
    a, b, c = base(id="UD-000000000001"), base(id="UD-000000000002", description="B"), base(id="UD-000000000003")
    for e in (a, b, c):
        wm_store.append_entry(path, e)
    edited = dict(b, description="B 수정", node=["n1"], relations=[{"type": "refines", "target": "UD-000000000001"}])
    assert wm_store.replace_entry(path, edited) is True
    entries, problems = wm_store.load_nt_entries(path)
    assert problems == [] and [e["id"] for e in entries] == [a["id"], b["id"], c["id"]]       # 위치 유지
    assert entries[1]["description"] == "B 수정" and entries[1]["node"] == ["n1"]
    assert entries[0] == a and entries[2] == c
    assert wm_store.replace_entry(path, base(id="UD-ffffffffffff")) is False
    assert not list(tmp_path.glob(".*.tmp"))                                                    # 임시 파일이 남지 않는다


def test_nt_entry_ids_and_duplicate_single_valued_detection(tmp_path):
    path = tmp_path / "user-decision.nt"
    wm_store.append_entry(path, base(id="UD-000000000001"))
    assert wm_store.nt_entry_ids(path) == {"UD-000000000001"}
    assert wm_store.duplicate_single_valued(path) == []
    # 병합/충돌 복제본이 같은 subject 에 다른 description 을 더하면 조용히 합치지 않고 보고한다
    extra = wm_store.serialize_triple(wm_store.entry_iri("UD-000000000001"), wm_store.WM + "description", wm_store.L("다른 요약"))
    with open(path, "a", encoding="utf-8") as f:
        f.write(extra + "\n")
    assert ("UD-000000000001", "description") in wm_store.duplicate_single_valued(path)


def test_external_reference_node_written_once_per_file(tmp_path):
    path = tmp_path / "user-decision.nt"
    wm_store.append_entry(path, base(id="UD-000000000001", relations=[{"type": "references", "target": "docs/x.md"}]))
    wm_store.append_entry(path, base(id="UD-000000000002", relations=[{"type": "references", "target": "docs/x.md"}]))
    assert path.read_text(encoding="utf-8").count(f"<{wm_store.WM}externalValue>") == 1
    entries, _ = wm_store.load_nt_entries(path)
    assert [e["relations"] for e in entries] == [[{"type": "references", "target": "docs/x.md"}]] * 2


def test_iter_curated_entries_reads_nt_and_legacy_jsonl_and_skips_dot_dirs(tmp_path):
    root = tmp_path / "wm"
    wm_store.append_entry(root / "track-record" / "user-decision.nt", base(id="UD-000000000001"))
    legacy = root / "track-record" / "issue-note.jsonl"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"id": "IN-0001", "type": "issue-note", "title": "t", "text": "x"}) + "\n", encoding="utf-8")
    hidden = root / "track-record" / ".migration-archive" / "old.jsonl"
    hidden.parent.mkdir(parents=True, exist_ok=True)
    hidden.write_text(json.dumps({"id": "IN-9999", "type": "issue-note"}) + "\n", encoding="utf-8")
    got = {(e["id"], fmt) for e, _p, _n, fmt in wm_store.iter_curated_entries(root)}
    assert got == {("UD-000000000001", "nt"), ("IN-0001", "jsonl")}


@pytest.mark.parametrize("etype,md", [
    ("issue-note", {"scope": ["repository"], "reporter": "user", "severity": "major", "status": "partially-resolved"}),
    ("agent-decision", {"scope": ["task"], "rationale": "r", "confidence": "high", "alternatives": ["A", "B"]}),
    ("trouble-shooting", {"scope": ["artifact"], "resolution": "r", "root_cause": "c", "prevention": "p"}),
    ("release-note", {"scope": ["repository"], "version": "0.9.0", "kind": "release", "released_at": NEW}),
    ("episode", {"scope": ["workflow"], "event_date": NEW, "participants": ["user", "agent"], "timeline": "t"}),
    ("pattern", {"scope": ["directory"], "context": "c", "frequency": 3, "sources": ["EP-0001"]}),
    ("principle", {"scope": ["global", "memory"], "statement": "s", "status": "accepted"}),
])
def test_every_type_roundtrips(etype, md):
    e = {"id": f"{wm_store.TYPE_CLASS[etype][:2].upper()}-019a3c5e4f21", "type": etype, "description": "d", "content": "c",
         "tags": ["t"], "created_at": NEW, "relations": [], "metadata": md}
    got, _ = roundtrip(e)
    assert got["metadata"] == md
