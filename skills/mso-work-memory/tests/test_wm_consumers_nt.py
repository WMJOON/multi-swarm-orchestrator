"""wm_context · wm_release · 주입 훅 · 투영이 큐레이션 기록(.nt)을 읽는다 (v0.16.0). JSONL 과 같은 결과여야 한다."""
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
import wm_store  # noqa: E402

CTX = SCRIPTS / "wm_context.py"
REL = SCRIPTS / "wm_release.py"
HOOK = SKILL / "hooks" / "workflow-context-hook.py"
OLD = "2026-06-01T00:00:00Z"


def entry(eid, etype, desc, content="본문", tags=None, relations=None, metadata=None, node=None, created=OLD):
    e = {"id": eid, "type": etype, "description": desc, "content": content, "tags": tags or [], "created_at": created,
         "relations": relations or [], "metadata": metadata or {}}
    if node:
        e["node"] = node
    return e


def seed(root: Path, entries, fmt):
    """같은 기록을 .nt 또는 .jsonl 로 심는다."""
    dirs = {"release-note": "release-record", "episode": "insight-record", "pattern": "insight-record", "principle": "insight-record"}
    for e in entries:
        d = root / dirs.get(e["type"], "track-record")
        if fmt == "nt":
            wm_store.append_entry(d / f"{e['type']}.nt", e)
        else:
            d.mkdir(parents=True, exist_ok=True)
            with open(d / f"{e['type']}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")


def run(script, root, *args, **env):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                          env={**os.environ, "WORKMEM_DIR": str(root), **env})


ENTRIES = [
    entry("UD-000000000001", "user-decision", "첫 결정", tags=["discovery-s-001", "step"], node=["discovery-s-001"],
          metadata={"rationale": "r", "scope": ["task"]}),
    entry("UD-000000000002", "user-decision", "새 결정", tags=["discovery-s-001"], node=["discovery-s-001"],
          relations=[{"type": "supersedes", "target": "UD-000000000001"}], metadata={"rationale": "r", "scope": ["task"]}),
    entry("PR-000000000001", "principle", "원칙", tags=["discovery-s-001"], metadata={"statement": "s", "status": "accepted", "scope": ["repository"]}),
]


def test_wm_context_pack_is_identical_for_nt_and_jsonl(tmp_path):
    outs = {}
    for fmt in ("nt", "jsonl"):
        root = tmp_path / fmt
        seed(root, ENTRIES, fmt)
        for args in (("query", "결정", "--tags", "discovery-s-001", "--json"),
                     ("node", "--node", "discovery-s-001", "--fallback", "none", "--json"),
                     ("node", "--node", "discovery-s-001", "--json")):
            r = run(CTX, root, *args)
            assert r.returncode == 0, r.stderr
            pack = json.loads(r.stdout)
            for e in pack["entries"]:
                e.pop("source_path", None)                      # 파일 이름만 다르다(.nt vs .jsonl)
            outs.setdefault(args, []).append(pack)
    for args, (nt_pack, jsonl_pack) in outs.items():
        assert nt_pack == jsonl_pack, args                       # 이행 전후 회수 결과가 같다
    ids = [e["id"] for e in outs[("node", "--node", "discovery-s-001", "--fallback", "none", "--json")][0]["entries"]]
    assert ids == ["UD-000000000002"]                            # 대체된 UD-1 은 제외(파생 validity 는 .nt 에서도 동작)


def test_wm_context_show_and_summary_output_read_nt(tmp_path):
    root = tmp_path / "wm"
    seed(root, ENTRIES, "nt")
    shown = run(CTX, root, "show", "UD-000000000002")
    assert shown.returncode == 0 and "새 결정" in shown.stdout and "(active)" in shown.stdout
    assert "(superseded)" in run(CTX, root, "show", "UD-000000000001").stdout


def test_hook_injects_from_nt_store_and_stays_silent_for_unmapped_node(tmp_path):
    project = tmp_path / "proj"
    root = project / "agent-context" / "work-memory"
    seed(root, ENTRIES, "nt")
    (project / ".mso" / "state").mkdir(parents=True)
    (project / ".mso" / "state" / "workflow-cursor.json").write_text(json.dumps({"node": "discovery-s-001"}), encoding="utf-8")
    env = {"CLAUDE_PROJECT_DIR": str(project)}
    r = run(HOOK, root, **env)
    assert "UD-000000000002" in r.stdout and "UD-000000000001" not in r.stdout and "새 결정" in r.stdout
    (project / ".mso" / "state" / "workflow-cursor.json").write_text(json.dumps({"node": "other"}), encoding="utf-8")
    assert run(HOOK, root, **env).stdout == ""


def test_hook_degrades_silently_when_wm_store_is_missing_in_copy_form(tmp_path):
    """복사된 훅 디렉터리에 wm_store.py 가 없으면 .nt 는 읽지 못하지만 훅은 죽지 않는다."""
    import shutil
    copy = tmp_path / "scripts"
    copy.mkdir()
    for f in ("wm_context.py",):
        shutil.copy(SCRIPTS / f, copy / f)
    shutil.copy(HOOK, copy / "workflow-context-hook.py")
    project = tmp_path / "proj"
    root = project / "agent-context" / "work-memory"
    seed(root, ENTRIES, "nt")
    (project / ".mso" / "state").mkdir(parents=True)
    (project / ".mso" / "state" / "workflow-cursor.json").write_text(json.dumps({"node": "discovery-s-001"}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(copy / "workflow-context-hook.py")], capture_output=True, text=True,
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(project), "WORKMEM_DIR": str(root)}, input="")
    assert r.returncode == 0 and r.stdout == ""                  # 침묵(.nt 를 못 읽음) — 크래시 아님
    shutil.copy(SCRIPTS / "wm_store.py", copy / "wm_store.py")
    shutil.copy(SKILL / "references" / "metadata-spec.json", copy / "metadata-spec.json")   # 복사 배포의 완전한 형태
    r = subprocess.run([sys.executable, str(copy / "workflow-context-hook.py")], capture_output=True, text=True,
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(project), "WORKMEM_DIR": str(root)}, input="")
    assert "UD-000000000002" in r.stdout                          # 완전히 복사하면 읽는다


def test_wm_release_current_and_validity_read_nt(tmp_path):
    root = tmp_path / "wm"
    rn1 = entry("RN-000000000001", "release-note", "v1", metadata={"version": "1.0.0", "kind": "release", "scope": ["repository"]})
    rn2 = entry("RN-000000000002", "release-note", "v2", metadata={"version": "1.1.0", "kind": "release", "scope": ["repository"],
                                                                       "released_at": "2026-06-02T00:00:00Z"})
    ud = entry("UD-000000000001", "user-decision", "d", relations=[{"type": "verified-in", "target": "RN-000000000002"}])
    seed(root, [rn1, rn2, ud], "nt")
    cur = run(REL, root, "current")
    assert cur.returncode == 0 and "1.1.0" in cur.stdout
    val = run(REL, root, "validity", "--id", "UD-000000000001")
    assert "verified-in" in val.stdout and "RN-000000000002" in val.stdout


def test_projection_ttl_graph_is_identical_for_nt_and_jsonl(tmp_path):
    from rdflib import Graph
    from rdflib.compare import isomorphic
    graphs = []
    for fmt in ("nt", "jsonl"):
        root = tmp_path / fmt
        seed(root, ENTRIES, fmt)
        out = tmp_path / f"{fmt}.ttl"
        r = subprocess.run([sys.executable, str(SCRIPTS / "wm_to_ttl.py"), "project", str(root), "-o", str(out)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        graphs.append(Graph().parse(out, format="turtle"))
    # .nt 는 source_path 를 저장하지 않으므로 그 triple 만 제외하고 같아야 한다
    sp = __import__("rdflib").URIRef(wm_store.WM + "sourcePath")
    for g in graphs:
        for t in list(g.triples((None, sp, None))):
            g.remove(t)
    assert isomorphic(graphs[0], graphs[1])
