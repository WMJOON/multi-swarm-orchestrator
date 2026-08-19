"""init.py --hook 등록 테스트 — copy-form 배포와 settings.json 갱신 (UD-0015)."""
import importlib.util
import json
from pathlib import Path

import pytest

_INIT_PY = Path(__file__).resolve().parent.parent / "scripts" / "init.py"


def _load_init():
    spec = importlib.util.spec_from_file_location("mso_init", _INIT_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def init_mod():
    return _load_init()


@pytest.fixture
def project(tmp_path):
    (tmp_path / "agent-context" / "work-memory").mkdir(parents=True)
    return tmp_path


def _settings(project: Path) -> dict:
    return json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))


def _commands(settings: dict, event: str) -> list[str]:
    out = []
    for group in settings.get("hooks", {}).get(event, []):
        for hook in group.get("hooks", []):
            out.append(hook.get("command", ""))
    return out


def test_hook_copies_scripts_including_wm_context(init_mod, project):
    assert init_mod.cmd_hook(project) != 1

    scripts = project / ".claude" / "scripts"
    for name in ("workflow-context-hook.py", "wm_context.py", "wm_release.py",
                 "release-context.sh", "auditlog.py"):
        assert (scripts / name).exists(), f"{name} 미복사"

    # 훅은 자기 옆의 wm_context.py 를 먼저 찾는다 — copy-form 자립성
    assert (scripts / "wm_context.py").stat().st_mode & 0o111


def test_hook_registers_workflow_context_on_user_prompt_submit(init_mod, project):
    assert init_mod.cmd_hook(project) != 1

    commands = _commands(_settings(project), "UserPromptSubmit")
    assert any("workflow-context-hook.py" in c for c in commands)


def test_workflow_context_command_carries_workmem_env(init_mod, project):
    assert init_mod.cmd_hook(project) != 1

    command = next(c for c in _commands(_settings(project), "UserPromptSubmit")
                   if "workflow-context-hook.py" in c)
    assert "WORKMEM_DIR=" in command
    # 절대경로를 박지 않는다 — 다른 머신·CI·경로 이동에 견뎌야 한다
    assert str(project) not in command


def test_hook_registration_is_idempotent(init_mod, project):
    assert init_mod.cmd_hook(project) != 1
    first = _commands(_settings(project), "UserPromptSubmit")
    assert init_mod.cmd_hook(project) != 1
    second = _commands(_settings(project), "UserPromptSubmit")

    assert first == second
    assert sum("workflow-context-hook.py" in c for c in second) == 1


def test_existing_settings_are_preserved(init_mod, project):
    claude_dir = project / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps({"model": "claude-sonnet-5", "hooks": {}}), encoding="utf-8")

    assert init_mod.cmd_hook(project) != 1
    settings = _settings(project)
    assert settings["model"] == "claude-sonnet-5"
    assert any("workflow-context-hook.py" in c for c in _commands(settings, "UserPromptSubmit"))
