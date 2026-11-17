"""후속 과제 (v0.16.0): 노드 무관 상시 주입(standing) · 자동 기록의 주체(onBehalfOf) 연결."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
import wm_store  # noqa: E402

CTX = SCRIPTS / "wm_context.py"
HOOK = SKILL / "hooks" / "standing-context-hook.py"
AUDIT = SKILL / "hooks" / "auditlog.py"
NEW = "2026-11-18T00:00:00Z"


def principle(eid, status, scope, desc=None, **over):
    e = {"id": eid, "type": "principle", "description": desc or f"원칙 {eid}", "content": "본문", "tags": [], "created_at": NEW,
         "relations": [], "metadata": {"statement": "s", "scope": scope, "status": status}}
    e.update(over)
    return e


def seed(root, entries):
    for e in entries:
        d = "insight-record" if e["type"] in ("principle", "pattern", "episode") else "track-record"
        wm_store.append_entry(root / d / f"{e['type']}.nt", e)


def run_ctx(root, *args, **env):
    return subprocess.run([sys.executable, str(CTX), *args], capture_output=True, text=True,
                          env={**os.environ, "WORKMEM_DIR": str(root), **env})


ENTRIES = [
    principle("PR-000000000001", "accepted", ["repository"], "저장소 전체 원칙"),
    principle("PR-000000000002", "accepted", ["global"], "전역 원칙"),
    principle("PR-000000000003", "draft", ["repository"], "초안 원칙(합의 전)"),
    principle("PR-000000000004", "deprecated", ["repository"], "폐기된 원칙"),
    principle("PR-000000000005", "accepted", ["task"], "한 task 에만 적용되는 원칙"),
    principle("PR-000000000006", "accepted", ["repository"], "대체된 원칙"),
    principle("PR-000000000007", "accepted", ["repository", "workflow"], "대체한 원칙",
              relations=[{"type": "supersedes", "target": "PR-000000000006"}]),
    {"id": "UD-000000000001", "type": "user-decision", "description": "결정(principle 이 아님)", "content": "c", "tags": [],
     "created_at": NEW, "relations": [], "metadata": {"scope": ["repository"], "rationale": "r"}},
]


def ids(out):
    return [line.split()[1] for line in out.splitlines() if line.strip().startswith("── ")]


# ── 상시 주입 ──

def test_standing_selects_accepted_active_principles_covering_repository_or_global(tmp_path):
    root = tmp_path / "wm"
    seed(root, ENTRIES)
    r = run_ctx(root, "standing")
    assert r.returncode == 0, r.stderr
    assert set(ids(r.stdout)) == {"PR-000000000001", "PR-000000000002", "PR-000000000007"}
    # draft(합의 전)·deprecated(폐기)·superseded(대체됨)·task 범위·principle 이 아닌 타입은 제외
    for excluded in ("PR-000000000003", "PR-000000000004", "PR-000000000005", "PR-000000000006", "UD-000000000001"):
        assert excluded not in r.stdout
    assert "항상 적용되는 교훈" in r.stdout and "본문 펼치기" in r.stdout          # 요약 + 펼치기 명령


def test_standing_options_budget_types_scopes_and_json(tmp_path):
    root = tmp_path / "wm"
    seed(root, ENTRIES)
    assert len(ids(run_ctx(root, "standing", "--top-k", "1").stdout)) == 1
    only_global = run_ctx(root, "standing", "--scopes", "global")
    assert ids(only_global.stdout) == ["PR-000000000002"]
    with_ud = run_ctx(root, "standing", "--types", "principle,user-decision")
    assert "UD-000000000001" in with_ud.stdout
    pack = json.loads(run_ctx(root, "standing", "--json").stdout)
    assert {e["validity"] for e in pack["entries"]} == {"active"}
    tight = run_ctx(root, "standing", "--max-chars", "120")
    assert "more" in tight.stdout and len(ids(tight.stdout)) < 3


def test_standing_accepts_legacy_scope_vocabulary_and_scalar_scope(tmp_path):
    root = tmp_path / "wm"
    seed(root, [principle("PR-000000000001", "accepted", "project", "옛 어휘 project 는 repository")])
    assert ids(run_ctx(root, "standing").stdout) == ["PR-000000000001"]


def test_standing_is_silent_when_nothing_qualifies(tmp_path):
    root = tmp_path / "wm"
    seed(root, [principle("PR-000000000001", "draft", ["repository"]), principle("PR-000000000002", "accepted", ["task"])])
    r = run_ctx(root, "standing")
    assert r.returncode == 0 and r.stdout == ""


def run_hook(project, root, **env):
    return subprocess.run([sys.executable, str(HOOK)], capture_output=True, text=True, input="",
                          env={**os.environ, "CLAUDE_PROJECT_DIR": str(project), "WORKMEM_DIR": str(root), **env})


def test_hook_injects_standing_principles_without_any_cursor_and_respects_env(tmp_path):
    project = tmp_path / "proj"
    root = project / "agent-context" / "work-memory"
    seed(root, ENTRIES)
    r = run_hook(project, root)
    assert r.returncode == 0 and "PR-000000000001" in r.stdout and "PR-000000000003" not in r.stdout     # 워크플로우 커서 없이도 주입
    assert run_hook(project, root, MSO_STANDING_CONTEXT_DISABLED="1").stdout == ""
    assert ids(run_hook(project, root, MSO_STANDING_TOP_K="1").stdout) != ids(r.stdout)
    assert ids(run_hook(project, root, MSO_STANDING_SCOPES="global").stdout) == ["PR-000000000002"]


def test_hook_is_silent_without_work_memory_or_wm_context(tmp_path):
    project = tmp_path / "proj"
    assert run_hook(project, project / "agent-context" / "work-memory").stdout == ""
    copy = tmp_path / "scripts"
    copy.mkdir()
    shutil.copy(HOOK, copy / "standing-context-hook.py")                         # wm_context.py 가 옆에 없다
    root = project / "agent-context" / "work-memory"
    seed(root, ENTRIES)
    r = subprocess.run([sys.executable, str(copy / "standing-context-hook.py")], capture_output=True, text=True,
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(project), "WORKMEM_DIR": str(root)})
    assert r.returncode == 0 and r.stdout == ""


def test_init_registers_the_standing_hook_for_session_start_and_copies_the_script(tmp_path):
    init = SKILL.parent / "mso-repository-setup" / "scripts" / "init.py"
    project = tmp_path / "proj"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run([sys.executable, str(init), "--target", str(project)], capture_output=True, text=True)
    r = subprocess.run([sys.executable, str(init), "--hook", str(project)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (project / ".claude" / "scripts" / "standing-context-hook.py").is_file()
    settings = json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = {(m.get("matcher"), h["command"]) for m in settings["hooks"]["SessionStart"] for h in m["hooks"]
                if "standing-context-hook.py" in h["command"]}
    assert {m for m, _c in commands} == {"startup", "compact", "resume"}          # 세션 시작·압축·재개 때 한 번
    r2 = subprocess.run([sys.executable, str(init), "--hook", str(project), "--provider", "codex"], capture_output=True, text=True)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    toml = (project / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert toml.count("standing-context-hook.py") == 3


# ── 자동 기록의 주체 ──

def test_auditlog_hook_records_the_hook_as_author_and_the_acting_agent_in_metadata(tmp_path):
    root = tmp_path / "wm"
    root.mkdir()
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "a.py"}, "session_id": "s1"})
    subprocess.run([sys.executable, str(AUDIT)], input=payload, capture_output=True, text=True,
                   env={**os.environ, "WORKMEM_DIR": str(root), "MSO_AGENT_ID": "claude-code"})
    record = json.loads(next((root / "auditlog").glob("*.jsonl")).read_text(encoding="utf-8").splitlines()[0])
    assert record["author"] == "auditlog-hook" and record["metadata"]["actor"] == "claude-code"
    default = subprocess.run([sys.executable, str(AUDIT)], input=payload, capture_output=True, text=True,
                             env={k: v for k, v in {**os.environ, "WORKMEM_DIR": str(root)}.items() if k != "MSO_AGENT_ID"})
    lines = next((root / "auditlog").glob("*.jsonl")).read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["metadata"]["actor"] == "agent"


def test_auditlog_author_projects_as_a_background_agent_owned_by_the_account_owner(tmp_path):
    import wm_query
    root = tmp_path / "wm"
    (root / "auditlog").mkdir(parents=True)
    (root / "auditlog" / "AU-2026-11-18.jsonl").write_text(json.dumps({
        "id": "AU-20261118-010101-abc123", "type": "auditlog", "title": "Edit: a.py", "text": "a.py", "tags": ["auditlog"],
        "created_at": NEW, "author": "auditlog-hook", "metadata": {"tool": "Edit", "session_id": "s1", "actor": "agent"}}) + "\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "wm_to_ttl.py"), "project", str(root), "--include-runtime", "-o", str(tmp_path / "wm.ttl")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    from rdflib import Graph
    g = Graph().parse(tmp_path / "wm.ttl", format="turtle")
    q = f"""PREFIX wm:<{wm_store.WM}>
        SELECT ?trigger ?owner WHERE {{ ?e wm:author ?a . ?a a wm:BackgroundAgent ; wm:trigger ?trigger ; wm:onBehalfOf ?o . ?o a wm:User ; wm:agentId ?owner }}"""
    assert [(str(a), str(b)) for a, b in g.query(q)] == [("hook", "user")]          # 훅 → 계정 주인(User)
    # 등록되지 않은 id 는 소속 미상(onBehalfOf 없음)이므로 SHACL 경고 대상이지만 내장 auditlog-hook 은 아니다
    assert subprocess.run([sys.executable, str(SCRIPTS / "wm_to_ttl.py"), "validate", str(root), "--include-runtime"],
                          capture_output=True, text=True).returncode == 0


def test_builtin_agents_include_the_auditlog_hook_in_the_generated_spec():
    spec = json.loads((SKILL / "references" / "metadata-spec.json").read_text(encoding="utf-8"))
    builtin = {a["id"]: a for a in spec["agents"]["builtin"]}
    assert builtin["auditlog-hook"] == {"id": "auditlog-hook", "kind": "backgroundAgent", "onBehalfOf": "user", "trigger": "hook"}
