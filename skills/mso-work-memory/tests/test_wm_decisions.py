"""사용자가 위임한 열린 결정 4건의 구현 (v0.16.0): edit 범위 · 미등록 주체 경고 · deprecated principle · scope↔node 경고."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import wm_metadata  # noqa: E402
import wm_store  # noqa: E402

NODE = SCRIPTS / "wm_node.py"
CTX = SCRIPTS / "wm_context.py"
NEW = "2026-11-18T00:00:00Z"


def node(root, *args):
    return subprocess.run([sys.executable, str(NODE), *args], capture_output=True, text=True,
                          env={**os.environ, "WORKMEM_DIR": str(root)})


def read(root, type_dir, type_name):
    return wm_store.load_nt_entries(root / type_dir / f"{type_name}.nt")[0]


def make_ud(root, **extra):
    args = ["new", "user-decision", "--description", "원래 요약", "--content", "원래 본문", "--meta", "rationale=r", "--scope", "repository"]
    for k, v in extra.items():
        args += [f"--{k.replace('_', '-')}", v]
    r = node(root, *args)
    assert r.returncode == 0, r.stderr
    return read(root, "track-record", "user-decision")[-1]


# ── 1. edit 의 범위: description/content 는 needs_review 기록에서만 (append-only 보호) ──

def test_edit_refuses_to_rewrite_description_or_content_of_a_settled_record(tmp_path):
    root = tmp_path / "wm"
    e = make_ud(root)
    for flag, value in (("--description", "고쳐 쓴 요약"), ("--content", "고쳐 쓴 본문")):
        r = node(root, "edit", e["id"], flag, value)
        assert r.returncode != 0 and "needs_review" in (r.stderr + r.stdout) and "--allow-rewrite" in (r.stderr + r.stdout)
    assert read(root, "track-record", "user-decision")[-1]["description"] == "원래 요약"      # 바뀌지 않았다


def test_edit_allows_state_like_fields_on_settled_records_without_any_flag(tmp_path):
    root = tmp_path / "wm"
    e = make_ud(root)
    r = node(root, "edit", e["id"], "--scope", "workflow", "--scope", "task", "--scope-note", "보충", "--component", "c1",
             "--tags", "a,b", "--meta", "structural=true")
    assert r.returncode == 0, r.stderr
    got = read(root, "track-record", "user-decision")[-1]
    assert got["metadata"]["scope"] == ["workflow", "task"] and got["metadata"]["component"] == "c1" and got["tags"] == ["a", "b"]
    assert got["description"] == "원래 요약"                                               # 이력(본문)은 그대로


def test_edit_rewrites_content_for_needs_review_records_and_with_explicit_override(tmp_path):
    root = tmp_path / "wm"
    assert node(root, "new", "user-decision", "--description", "미완성", "--scope", "repository", "--allow-incomplete").returncode == 0
    e = read(root, "track-record", "user-decision")[-1]
    assert e["metadata"]["needs_review"] is True
    ok = node(root, "edit", e["id"], "--description", "보정한 요약", "--meta", "rationale=이유")
    assert ok.returncode == 0, ok.stderr                                                   # needs_review 기록은 보정 경로다
    settled = read(root, "track-record", "user-decision")[-1]
    assert "needs_review" not in settled["metadata"]
    again = node(root, "edit", e["id"], "--description", "또 고침")
    assert again.returncode != 0                                                           # 확정된 뒤에는 다시 잠긴다
    forced = node(root, "edit", e["id"], "--description", "명시적으로 고침", "--allow-rewrite")
    assert forced.returncode == 0 and "[WARN]" in forced.stderr and "이력" in forced.stderr
    assert read(root, "track-record", "user-decision")[-1]["description"] == "명시적으로 고침"


# ── 2. 등록되지 않은 주체(author)는 경고 ──

def test_new_warns_for_unregistered_author_but_not_for_builtin_or_registered(tmp_path):
    root = tmp_path / "wm"
    unknown = node(root, "new", "user-decision", "--description", "d", "--meta", "rationale=r", "--scope", "repository", "--author", "mystery-bot")
    assert unknown.returncode == 0 and "mystery-bot" in unknown.stderr and "agents.yaml" in unknown.stderr
    for author in ("agent", "user"):
        ok = node(root, "new", "user-decision", "--description", "d", "--meta", "rationale=r", "--scope", "repository", "--author", author)
        assert "agents.yaml" not in ok.stderr
    root.mkdir(exist_ok=True)
    (root / "agents.yaml").write_text("agents:\n  - {id: stop-hook, kind: backgroundAgent, onBehalfOf: user, trigger: hook}\n", encoding="utf-8")
    reg = node(root, "new", "user-decision", "--description", "d", "--meta", "rationale=r", "--scope", "repository", "--author", "stop-hook")
    assert "agents.yaml" not in reg.stderr


# ── 3. deprecated principle 은 파생 validity 로 주입에서 제외 ──

def principle(eid, status, **over):
    e = {"id": eid, "type": "principle", "description": f"원칙 {eid}", "content": "본문", "tags": ["pr"], "created_at": NEW,
         "relations": [], "metadata": {"statement": "s", "scope": ["repository"], "status": status}, "node": ["discovery-s-001"]}
    e.update(over)
    return e


def seed_principles(root):
    wm_store.append_entry(root / "insight-record" / "principle.nt", principle("PR-000000000001", "accepted"))
    wm_store.append_entry(root / "insight-record" / "principle.nt", principle("PR-000000000002", "deprecated"))
    wm_store.append_entry(root / "insight-record" / "principle.nt", principle("PR-000000000003", "draft"))


def test_deprecated_principle_is_excluded_from_injection_but_shown_by_include_inactive(tmp_path):
    root = tmp_path / "wm"
    seed_principles(root)
    pack = json.loads(subprocess.run([sys.executable, str(CTX), "node", "--node", "discovery-s-001", "--fallback", "none", "--json"],
                                     capture_output=True, text=True, env={**os.environ, "WORKMEM_DIR": str(root)}).stdout)
    assert {e["id"] for e in pack["entries"]} == {"PR-000000000001", "PR-000000000003"}      # draft 는 남기고 deprecated 만 제외
    all_ = json.loads(subprocess.run([sys.executable, str(CTX), "node", "--node", "discovery-s-001", "--fallback", "none", "--json", "--include-inactive"],
                                     capture_output=True, text=True, env={**os.environ, "WORKMEM_DIR": str(root)}).stdout)
    by_id = {e["id"]: e["validity"] for e in all_["entries"]}
    assert by_id["PR-000000000002"] == "deprecated"


def test_deprecated_validity_is_identical_in_all_three_implementations(tmp_path):
    """wm_release.derive_validity · wm_context.derive_validity · derive.rq(SPARQL) 가 같은 결과를 내야 한다."""
    import importlib.util
    import wm_query
    root = tmp_path / "wm"
    seed_principles(root)
    # 우선순위: invalidated > superseded > deprecated > suspended > active — deprecated 이면서 superseded 인 경우를 함께 시험한다
    wm_store.append_entry(root / "insight-record" / "principle.nt", principle("PR-000000000004", "deprecated"))
    wm_store.append_entry(root / "insight-record" / "principle.nt", principle("PR-000000000005", "accepted",
                          relations=[{"type": "supersedes", "target": "PR-000000000004"}]))
    entries = [e for p in (root / "insight-record").glob("*.nt") for e in wm_store.load_nt_entries(p)[0]]
    def load(name):
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        mod = importlib.util.module_from_spec(spec); sys.modules[f"{name}_dec"] = mod; spec.loader.exec_module(mod); return mod
    rel, ctx = load("wm_release"), load("wm_context")
    py_release = {k: v["validity"] for k, v in rel.derive_validity(entries).items()}
    py_ctx = {k: v["validity"] for k, v in ctx.derive_validity([ctx.normalize_entry(e, "x") for e in entries]).items()}
    store = wm_query.build(root, "rdflib")
    _v, rows = store.select(f"PREFIX wm:<{wm_store.WM}> SELECT ?id ?v WHERE {{ ?e wm:entryId ?id ; wm:validity ?v }}")
    sparql = {r[0]: r[1] for r in rows}
    assert py_release == py_ctx == sparql
    assert sparql["PR-000000000002"] == "deprecated" and sparql["PR-000000000004"] == "superseded" and sparql["PR-000000000001"] == "active"


def test_validity_shape_accepts_deprecated(tmp_path):
    root = tmp_path / "wm"
    seed_principles(root)
    r = subprocess.run([sys.executable, str(SCRIPTS / "wm_to_ttl.py"), "validate", str(root)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ── 4. scope 가 task/workflow 인데 node 가 없으면 경고 ──

def levels(e):
    return wm_metadata.check_entry(e)


def ud_entry(scope, node=None):
    e = {"id": "UD-1", "type": "user-decision", "description": "d", "content": "c", "tags": [], "created_at": NEW, "relations": [],
         "metadata": {"scope": scope, "rationale": "r"}}
    if node:
        e["node"] = node
    return e


@pytest.mark.parametrize("scope", [["task"], ["workflow"], ["repository", "task"]])
def test_task_or_workflow_scope_without_node_warns_never_errors(scope):
    found = levels(ud_entry(scope))
    assert any(lvl == "warn" and "node" in m for lvl, m in found)
    assert [x for x in found if x[0] == "error"] == []


def test_no_node_warning_when_mapped_or_scope_is_broader():
    assert not any("node" in m for _l, m in levels(ud_entry(["task"], node=["discovery-s-001"])))
    assert not any("node" in m for _l, m in levels(ud_entry(["repository"])))
    assert not any("node" in m for _l, m in levels(ud_entry(["artifact", "directory", "memory", "global"])))
