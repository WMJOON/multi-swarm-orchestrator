"""init.py --hook 등록 테스트 — copy-form 배포와 settings.json 갱신 (UD-0015)."""
import importlib.util
import json
import tomllib
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


def _codex_config(project: Path) -> tuple[str, dict]:
    path = project / ".codex" / "config.toml"
    return path.read_text(encoding="utf-8"), tomllib.loads(path.read_text(encoding="utf-8"))


def _agy_hooks(project: Path) -> dict:
    return json.loads((project / ".agents" / "hooks.json").read_text(encoding="utf-8"))


def _agy_section(project: Path) -> dict:
    return _agy_hooks(project)["mso-work-memory"]


def _agy_flat_commands(section: dict, event: str) -> list[str]:
    return [h.get("command", "") for h in section.get(event, [])]


def _agy_grouped_commands(section: dict, event: str) -> list[str]:
    out = []
    for group in section.get(event, []):
        out.extend(h.get("command", "") for h in group.get("hooks", []))
    return out


def test_hook_copies_scripts_including_wm_context(init_mod, project):
    assert init_mod.cmd_hook(project) != 1

    scripts = project / ".claude" / "scripts"
    for name in ("workflow-context-hook.py", "wm_context.py", "wm_release.py", "wm_repos.py",
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


def test_codex_hook_registers_full_provider_parity(init_mod, project, monkeypatch):
    monkeypatch.setattr(init_mod, "_find_uug_ug", lambda: None)
    assert init_mod.cmd_hook(project, provider="codex") != 1

    text, config = _codex_config(project)
    assert config["features"]["hooks"] is True
    assert "[[hooks.PostToolUse]]" in text
    assert 'matcher = "^(Bash|apply_patch)$"' in text
    assert "auditlog.py" in text
    assert "scaffold-check.sh" in text
    assert "workflow-context-hook.py" in text
    assert "release-context.sh" in text
    assert text.count('matcher = "startup"') == 1
    assert "uug-context-hook.py" not in text


def test_codex_hook_enables_existing_disabled_feature_and_preserves_config(init_mod, project, monkeypatch):
    monkeypatch.setattr(init_mod, "_find_uug_ug", lambda: None)
    codex_dir = project / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(
        '[features]\nhooks = false\n\nmodel = "gpt-5.6"\n', encoding="utf-8"
    )

    assert init_mod.cmd_hook(project, provider="codex") != 1
    _, config = _codex_config(project)
    assert config["features"]["hooks"] is True
    assert config["features"]["model"] == "gpt-5.6"


def test_codex_uug_registration_is_install_gated(init_mod, project, monkeypatch):
    monkeypatch.setattr(init_mod, "_find_uug_ug", lambda: Path("/installed/ug.py"))
    assert init_mod.cmd_hook(project, provider="codex") != 1
    text, _ = _codex_config(project)
    assert "uug-context-hook.py" in text


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_worthy_paths_survive_hook_rerun(init_mod, project, provider):
    worthy = "src config agent-context"
    assert init_mod.cmd_hook(project, worthy_paths=worthy, provider=provider) != 1
    assert init_mod.cmd_hook(project, provider=provider) != 1

    if provider == "codex":
        text, _ = _codex_config(project)
        assert f'WM_WORTHY_PATHS="{worthy}"' in text
        assert text.count("# BEGIN MSO_WORK_MEMORY_HOOKS") == 1
    else:
        commands = _commands(_settings(project), "SessionStart")
        assert any(f'WM_WORTHY_PATHS="{worthy}"' in command for command in commands)


def test_antigravity_hook_registers_full_provider_parity(init_mod, project, monkeypatch):
    monkeypatch.setattr(init_mod, "_find_uug_ug", lambda: None)
    assert init_mod.cmd_hook(project, provider="antigravity") != 1

    section = _agy_section(project)
    post = _agy_grouped_commands(section, "PostToolUse")
    assert any("auditlog.py" in c for c in post)
    assert any("scaffold-check.sh" in c for c in post)
    # PostToolUse matcher targets Antigravity tool names, not Claude's.
    matcher = section["PostToolUse"][0]["matcher"]
    assert "run_command" in matcher and "write_to_file" in matcher

    stop = _agy_flat_commands(section, "Stop")
    assert any("stop-check.sh" in c for c in stop)
    assert any("commit-work-memory.sh" in c for c in stop)

    pre = _agy_flat_commands(section, "PreInvocation")
    assert any("adapter_antigravity.py session" in c and "work-memory-check.sh" in c for c in pre)
    assert any("adapter_antigravity.py session" in c and "release-context.sh" in c for c in pre)
    assert any("adapter_antigravity.py turn" in c and "workflow-context-hook.py" in c for c in pre)
    assert not any("uug-context-hook.py" in c for c in pre)

    # every command routes through the camelCase adapter
    for cmd in post + stop + pre:
        assert "adapter_antigravity.py" in cmd

    scripts = project / ".agents" / "scripts"
    assert (scripts / "adapter_antigravity.py").exists()
    assert (scripts / "adapter_antigravity.py").stat().st_mode & 0o111


def test_antigravity_uug_registration_is_install_gated(init_mod, project, monkeypatch):
    monkeypatch.setattr(init_mod, "_find_uug_ug", lambda: Path("/installed/ug.py"))
    assert init_mod.cmd_hook(project, provider="antigravity") != 1
    pre = _agy_flat_commands(_agy_section(project), "PreInvocation")
    assert any("uug-context-hook.py" in c for c in pre)


def test_antigravity_hook_registration_is_idempotent(init_mod, project, monkeypatch):
    monkeypatch.setattr(init_mod, "_find_uug_ug", lambda: None)
    assert init_mod.cmd_hook(project, provider="antigravity") != 1
    first = _agy_hooks(project)
    assert init_mod.cmd_hook(project, provider="antigravity") != 1
    second = _agy_hooks(project)

    assert first == second
    post = _agy_grouped_commands(second["mso-work-memory"], "PostToolUse")
    assert sum("auditlog.py" in c for c in post) == 1


def test_antigravity_worthy_paths_survive_rerun(init_mod, project):
    worthy = "src config agent-context"
    assert init_mod.cmd_hook(project, worthy_paths=worthy, provider="antigravity") != 1
    assert init_mod.cmd_hook(project, provider="antigravity") != 1

    pre = _agy_flat_commands(_agy_section(project), "PreInvocation")
    assert any(f'WM_WORTHY_PATHS="{worthy}"' in c for c in pre)


def test_antigravity_existing_hooks_json_is_preserved(init_mod, project):
    agy_dir = project / ".agents"
    agy_dir.mkdir()
    (agy_dir / "hooks.json").write_text(
        json.dumps({"some-other-hook": {"enabled": False, "Stop": []}}), encoding="utf-8")

    assert init_mod.cmd_hook(project, provider="antigravity") != 1
    hooks = _agy_hooks(project)
    assert hooks["some-other-hook"] == {"enabled": False, "Stop": []}
    assert "mso-work-memory" in hooks


def test_init_bootstraps_release_record_and_provider_neutral_state_ignore(init_mod, tmp_path):
    project = tmp_path / "project"
    init_mod.cmd_init(project, "Test", "test")
    assert (project / "agent-context" / "work-memory" / "release-record").is_dir()
    gitignore = (project / ".gitignore").read_text(encoding="utf-8")
    assert ".mso/state/" in gitignore

    # 기존 v0.10.0 .gitignore도 누락 줄만 보강한다.
    gitignore_path = project / ".gitignore"
    gitignore_path.write_text("agent-context/work-memory/.zvec/\n", encoding="utf-8")
    init_mod._ensure_gitignore(gitignore_path)
    assert ".mso/state/" in gitignore_path.read_text(encoding="utf-8")
