"""workflow cursor + UserPromptSubmit 훅 테스트 (UD-0015)."""
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
WM_CONTEXT = SKILL / "scripts" / "wm_context.py"
HOOK = SKILL / "hooks" / "workflow-context-hook.py"


def _run(script: Path, *args: str, project: Path, workmem: Path | None = None,
         **env_extra) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    if workmem:
        env["WORKMEM_DIR"] = str(workmem)
    env.update(env_extra)
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, env=env)


def _seed_workmem(project: Path) -> Path:
    workmem = project / "agent-context" / "work-memory"
    path = workmem / "insight-record" / "principle.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "id": "PR-0001",
        "type": "principle",
        "title": "Input collection must be explicit",
        "text": "Collect inputs before validation.",
        "tags": ["discovery-s-001", "step"],
        "created_at": "2026-06-01T00:00:00Z",
        "relations": [],
        "metadata": {},
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    return workmem


# ── cursor CLI ──

def test_cursor_set_show_clear_roundtrip(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()

    assert _run(WM_CONTEXT, "cursor", "set", "discovery-s-001", project=project).returncode == 0
    cursor_file = project / ".mso" / "state" / "workflow-cursor.json"
    assert cursor_file.exists()
    assert json.loads(cursor_file.read_text(encoding="utf-8"))["node"] == "discovery-s-001"

    shown = _run(WM_CONTEXT, "cursor", "show", project=project)
    assert json.loads(shown.stdout)["node"] == "discovery-s-001"

    assert _run(WM_CONTEXT, "cursor", "clear", project=project).returncode == 0
    assert not cursor_file.exists()


def test_cursor_show_silent_when_absent(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    result = _run(WM_CONTEXT, "cursor", "show", project=project)
    assert result.returncode == 0
    assert result.stdout == ""


def test_cursor_set_records_ttl_as_absolute_path(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    ttl = project / "wf.abox.ttl"
    ttl.write_text("# ttl", encoding="utf-8")

    _run(WM_CONTEXT, "cursor", "set", "n1", "--ttl", str(ttl), project=project)
    cursor = json.loads((project / ".mso" / "state" / "workflow-cursor.json").read_text(encoding="utf-8"))
    assert Path(cursor["ttl"]).is_absolute()
    assert Path(cursor["ttl"]).exists()


# ── hook ──

def test_hook_injects_pack_for_cursor_node(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    workmem = _seed_workmem(project)
    _run(WM_CONTEXT, "cursor", "set", "discovery-s-001", project=project)

    result = _run(HOOK, project=project, workmem=workmem)
    assert result.returncode == 0
    assert "[work-memory context: discovery-s-001]" in result.stdout
    assert "PR-0001" in result.stdout


def test_hook_silent_without_cursor(tmp_path):
    """workflow 레일 밖 작업 — 잡음이 없어야 한다."""
    project = tmp_path / "proj"
    project.mkdir()
    workmem = _seed_workmem(project)

    result = _run(HOOK, project=project, workmem=workmem)
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_silent_when_disabled(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    workmem = _seed_workmem(project)
    _run(WM_CONTEXT, "cursor", "set", "discovery-s-001", project=project)

    result = _run(HOOK, project=project, workmem=workmem, MSO_WORKFLOW_CONTEXT_DISABLED="1")
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_silent_on_corrupt_cursor(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    workmem = _seed_workmem(project)
    cursor_file = project / ".mso" / "state" / "workflow-cursor.json"
    cursor_file.parent.mkdir(parents=True)
    cursor_file.write_text("{not json", encoding="utf-8")

    result = _run(HOOK, project=project, workmem=workmem)
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_silent_when_workmem_missing(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _run(WM_CONTEXT, "cursor", "set", "discovery-s-001", project=project)

    result = _run(HOOK, project=project, workmem=tmp_path / "nope")
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_reads_legacy_claude_cursor(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    workmem = _seed_workmem(project)
    cursor_file = project / ".claude" / "state" / "workflow-cursor.json"
    cursor_file.parent.mkdir(parents=True)
    cursor_file.write_text(json.dumps({"node": "discovery-s-001"}), encoding="utf-8")

    result = _run(HOOK, project=project, workmem=workmem)
    assert result.returncode == 0
    assert "PR-0001" in result.stdout


def test_hook_runs_with_codex_project_dir_only(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    workmem = _seed_workmem(project)
    env = {key: value for key, value in os.environ.items() if key not in {"PROJECT_DIR", "CLAUDE_PROJECT_DIR"}}
    env.update({"CODEX_PROJECT_DIR": str(project), "WORKMEM_DIR": str(workmem)})
    cursor_file = project / ".mso" / "state" / "workflow-cursor.json"
    cursor_file.parent.mkdir(parents=True)
    cursor_file.write_text(json.dumps({"node": "discovery-s-001"}), encoding="utf-8")

    result = subprocess.run([sys.executable, str(HOOK)], capture_output=True, text=True, env=env)
    assert result.returncode == 0
    assert "PR-0001" in result.stdout


def test_hook_silent_when_no_matching_entries(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    workmem = _seed_workmem(project)
    # include_types 게이트 밖 타입만 남기고, 매칭되는 게 없는 node 로 커서 설정
    _run(WM_CONTEXT, "cursor", "set", "totally-unrelated-node", project=project)

    result = _run(HOOK, project=project, workmem=workmem, MSO_WORKFLOW_CONTEXT_TOP_K="0")
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_finds_wm_context_in_copy_form_layout(tmp_path):
    """init.py --hook 배포 형태: 훅과 wm_context.py 가 같은 .claude/scripts/ 에 나란히 놓인다."""
    import shutil

    project = tmp_path / "proj"
    project.mkdir()
    workmem = _seed_workmem(project)
    scripts_dst = project / ".claude" / "scripts"
    scripts_dst.mkdir(parents=True)
    shutil.copy(HOOK, scripts_dst / HOOK.name)
    shutil.copy(WM_CONTEXT, scripts_dst / WM_CONTEXT.name)
    _run(WM_CONTEXT, "cursor", "set", "discovery-s-001", project=project)

    result = _run(scripts_dst / HOOK.name, project=project, workmem=workmem)
    assert result.returncode == 0
    assert "PR-0001" in result.stdout


def test_hook_respects_top_k_env(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    workmem = _seed_workmem(project)
    extra = workmem / "insight-record" / "principle.jsonl"
    with extra.open("a", encoding="utf-8") as f:
        for n in (2, 3, 4, 5):
            f.write(json.dumps({
                "id": f"PR-000{n}", "type": "principle", "title": f"P{n}", "text": "",
                "tags": ["discovery-s-001"], "created_at": "2026-06-01T00:00:00Z",
                "relations": [], "metadata": {},
            }, ensure_ascii=False) + "\n")
    _run(WM_CONTEXT, "cursor", "set", "discovery-s-001", project=project)

    result = _run(HOOK, project=project, workmem=workmem, MSO_WORKFLOW_CONTEXT_TOP_K="2")
    assert result.returncode == 0
    assert result.stdout.count("  ── PR-") == 2
