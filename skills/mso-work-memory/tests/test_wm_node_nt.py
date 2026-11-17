"""wm_node.py 가 큐레이션 기록을 N-Triples(.nt)로 쓰고·읽고·고친다 (v0.16.0)."""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import wm_store  # noqa: E402

NODE = SCRIPTS / "wm_node.py"


def node(root, *args):
    return subprocess.run([sys.executable, str(NODE), *args], capture_output=True, text=True,
                          env={**os.environ, "WORKMEM_DIR": str(root)})


def new_ud(root, desc="결정", **kw):
    args = ["new", "user-decision", "--description", desc, "--content", "본문 \"인용\"\n둘째 줄", "--meta", "rationale=이유",
            "--scope", "repository"]
    for k, v in kw.items():
        args += [f"--{k.replace('_', '-')}", v]
    r = node(root, *args)
    assert r.returncode == 0, r.stderr
    return wm_store.load_nt_entries(root / "track-record" / "user-decision.nt")[0][-1]


def test_new_writes_ntriples_one_triple_per_line_and_no_jsonl(tmp_path):
    root = tmp_path / "wm"
    e = new_ud(root)
    path = root / "track-record" / "user-decision.nt"
    assert path.is_file() and not (root / "track-record" / "user-decision.jsonl").exists()
    text = path.read_text(encoding="utf-8")
    assert all(l.endswith(" .") for l in text.splitlines())
    assert e["content"] == '본문 "인용"\n둘째 줄' and "source_path" not in e          # 줄바꿈·따옴표 보존, source_path 미저장
    from rdflib import Graph
    assert len(Graph().parse(path, format="nt")) == len(text.splitlines())          # rdflib 이 그대로 읽는다(= 유효한 TTL)


def test_validate_reads_nt_and_reports_syntax_errors_and_duplicate_fields(tmp_path):
    root = tmp_path / "wm"
    new_ud(root)
    ok = node(root, "validate", str(root))
    assert ok.returncode == 0, ok.stdout
    path = root / "track-record" / "user-decision.nt"
    with open(path, "a", encoding="utf-8") as f:
        f.write("이건 triple 이 아니다\n")
    bad = node(root, "validate", str(root))
    assert bad.returncode != 0 and "[PARSE]" in bad.stdout
    path.write_text("\n".join(l for l in path.read_text(encoding="utf-8").splitlines() if "triple 이 아니다" not in l) + "\n", encoding="utf-8")
    eid = wm_store.load_nt_entries(path)[0][0]["id"]
    extra = wm_store.serialize_triple(wm_store.entry_iri(eid), wm_store.WM + "description", wm_store.L("충돌 복제본의 다른 요약"))
    with open(path, "a", encoding="utf-8") as f:
        f.write(extra + "\n")
    dup = node(root, "validate", str(root))
    assert dup.returncode != 0 and "[DUP-FIELD]" in dup.stdout and "description" in dup.stdout   # 조용히 합치지 않는다


def test_relate_and_map_node_edit_nt_in_place_without_moving_entries(tmp_path):
    root = tmp_path / "wm"
    a = new_ud(root, "A")
    b = new_ud(root, "B")
    c = new_ud(root, "C")
    assert node(root, "relate", b["id"], "refines", a["id"]).returncode == 0
    assert node(root, "map-node", b["id"], "--node", "discovery-s-001").returncode == 0
    entries = wm_store.load_nt_entries(root / "track-record" / "user-decision.nt")[0]
    assert [e["id"] for e in entries] == [a["id"], b["id"], c["id"]]                   # 위치 유지
    assert entries[1]["relations"] == [{"type": "refines", "target": a["id"]}] and entries[1]["node"] == ["discovery-s-001"]
    assert entries[0] == a and entries[2] == c                                           # 다른 기록은 그대로
    assert node(root, "map-node", b["id"], "--node", "discovery-s-001", "--remove").returncode == 0
    assert "node" not in wm_store.load_nt_entries(root / "track-record" / "user-decision.nt")[0][1]
    assert node(root, "validate", str(root)).returncode == 0


def test_edit_changes_content_scope_metadata_and_clears_needs_review_when_complete(tmp_path):
    root = tmp_path / "wm"
    r = node(root, "new", "user-decision", "--description", "미완성", "--scope", "repository", "--allow-incomplete")
    assert r.returncode == 0, r.stderr
    e = wm_store.load_nt_entries(root / "track-record" / "user-decision.nt")[0][0]
    assert e["metadata"].get("needs_review") is True
    ok = node(root, "edit", e["id"], "--description", "보정한 요약", "--content", "보정한 본문", "--meta", "rationale=이유",
              "--scope", "workflow", "--scope", "task", "--scope-note", "보충")
    assert ok.returncode == 0, ok.stderr
    got = wm_store.load_nt_entries(root / "track-record" / "user-decision.nt")[0][0]
    assert got["description"] == "보정한 요약" and got["content"] == "보정한 본문"
    assert got["metadata"]["scope"] == ["workflow", "task"] and got["metadata"]["scope_note"] == "보충"
    assert "needs_review" not in got["metadata"]                                         # 필수가 채워져 표시가 지워진다
    assert got["id"] == e["id"] and got["created_at"] == e["created_at"]                 # id·created_at 은 바뀌지 않는다
    assert node(root, "validate", str(root)).returncode == 0
    assert "변경 없음" in node(root, "edit", e["id"], "--scope", "workflow", "--scope", "task").stdout
    too_long = node(root, "edit", e["id"], "--description", "가" * 201, "--allow-rewrite")   # 확정된 기록이라 --allow-rewrite 가 필요하다
    assert too_long.returncode != 0 and "200자" in (too_long.stderr + too_long.stdout)


def test_edit_refuses_result_that_breaks_the_spec_for_new_records(tmp_path):
    root = tmp_path / "wm"
    e = new_ud(root)
    bad = node(root, "edit", e["id"], "--meta", "structural=maybe")
    assert bad.returncode != 0
    assert wm_store.load_nt_entries(root / "track-record" / "user-decision.nt")[0][0]["metadata"].get("structural") is None


def test_edit_works_on_legacy_jsonl_records_too(tmp_path):
    root = tmp_path / "wm"
    path = root / "track-record" / "issue-note.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"id": "IN-0001", "type": "issue-note", "description": "옛", "content": "c", "tags": [],
                                "created_at": "2026-06-01T00:00:00Z", "relations": [], "metadata": {}}) + "\n", encoding="utf-8")
    refused = node(root, "edit", "IN-0001", "--description", "고침")             # 확정된 기록의 이력은 보호된다
    assert refused.returncode != 0 and "needs_review" in (refused.stderr + refused.stdout)
    r = node(root, "edit", "IN-0001", "--description", "고침", "--scope", "repository", "--allow-rewrite")
    assert r.returncode == 0, r.stderr
    got = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert got["description"] == "고침" and got["metadata"]["scope"] == ["repository"]


def test_new_id_is_unique_across_jsonl_and_nt_files(tmp_path):
    import time
    root = tmp_path / "wm"
    ms = int(time.time() * 1000)
    legacy = root / "track-record" / "user-decision.jsonl"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("".join(json.dumps({"id": f"UD-{ms + k:012x}", "type": "user-decision"}) + "\n" for k in range(3000)), encoding="utf-8")
    e = new_ud(root)
    assert e["id"] not in {f"UD-{ms + k:012x}" for k in range(3000)}


def test_show_nt_prints_the_entrys_triples_and_graph_stats_read_nt(tmp_path):
    root = tmp_path / "wm"
    a = new_ud(root, "A")
    b = new_ud(root, "B")
    node(root, "relate", b["id"], "refines", a["id"])
    shown = node(root, "show", b["id"], "--nt")
    assert shown.returncode == 0 and f"<{wm_store.WM}refines>" in shown.stdout
    assert json.loads(node(root, "show", b["id"]).stdout)["relations"][0]["target"] == a["id"]
    graph = node(root, "graph", b["id"], "--depth", "1")
    assert a["id"] in graph.stdout
    assert "user-decision" in node(root, "stats").stdout and "2" in node(root, "stats").stdout
