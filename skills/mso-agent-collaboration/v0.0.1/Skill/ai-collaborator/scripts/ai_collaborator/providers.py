from __future__ import annotations

import os
import shutil
from typing import Any, Dict, List, Optional

PROVIDERS: Dict[str, Dict[str, Any]] = {
    "codex": {
        "env_var": "CODEX_BIN",
        "binary_names": ["codex"],
        "alt_paths": ["/opt/homebrew/bin/codex", "/usr/local/bin/codex", "/Users/wmjoon/.bun/bin/codex"],
        "cmd": ["exec", "--skip-git-repo-check"],
        "stdin_cmd": ["exec", "--skip-git-repo-check"],
        "description": "OpenAI Codex - Best for overall AX/AI strategy",
        "template_env": "CODEX_CMD_TEMPLATE",
        "template_required": False,
    },
    "claude": {
        "env_var": "CLAUDE_BIN",
        "binary_names": ["claude"],
        "alt_paths": ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"],
        "cmd": ["-p"],
        "stdin_cmd": [],
        "description": "Claude Code - High-performance coding assistant",
        "template_env": "CLAUDE_CMD_TEMPLATE",
        "template_required": False,
    },
    "gemini": {
        "env_var": "GEMINI_BIN",
        "binary_names": ["gemini"],
        "alt_paths": ["/opt/homebrew/bin/gemini", "/usr/local/bin/gemini", "/Users/wmjoon/.local/bin/gemini"],
        "cmd": [],
        "stdin_cmd": [],
        "description": "Gemini CLI - Strong in Google ecosystem",
        "template_env": "GEMINI_CMD_TEMPLATE",
        "template_required": False,
    },
    "antigravity": {
        "env_var": "ANTIGRAVITY_BIN",
        "binary_names": ["antigravity"],
        "alt_paths": [
            "/Users/wmjoon/.antigravity/antigravity/bin/antigravity",
            "/opt/homebrew/bin/antigravity",
            "/usr/local/bin/antigravity",
        ],
        "cmd": ["chat", "-"],
        "stdin_cmd": ["chat", "-"],
        "description": "Antigravity - Local AI IDE/runtime",
        "template_env": "ANTIGRAVITY_CMD_TEMPLATE",
        "template_required": True,
    },
}


def provider_names() -> List[str]:
    return list(PROVIDERS.keys())


def provider_config(provider: str) -> Optional[Dict[str, Any]]:
    return PROVIDERS.get(provider)


def find_executable(provider: str) -> Optional[str]:
    config = provider_config(provider)
    if not config:
        return None

    env_var = config.get("env_var")
    if env_var:
        env_path = os.environ.get(env_var)
        if env_path and os.path.exists(env_path):
            return env_path

    for binary_name in config.get("binary_names", []):
        which_path = shutil.which(binary_name)
        if which_path:
            return which_path

    for alt in config.get("alt_paths", []):
        if os.path.exists(alt):
            return alt

    return None


def check_provider_status() -> Dict[str, Dict[str, Any]]:
    status: Dict[str, Dict[str, Any]] = {}
    for provider, config in PROVIDERS.items():
        executable = find_executable(provider)
        status[provider] = {
            "available": executable is not None,
            "path": executable,
            "description": config["description"],
        }
    return status


def check_token_usage() -> Dict[str, Dict[str, Any]]:
    token_info: Dict[str, Dict[str, Any]] = {}

    openai_key = os.environ.get("OPENAI_API_KEY")
    token_info["codex"] = {
        "provider": "OpenAI (Codex)",
        "api_key_set": bool(openai_key),
        "note": "Check usage at https://platform.openai.com/usage"
        if openai_key
        else "OPENAI_API_KEY not found",
        "check_method": "API dashboard" if openai_key else None,
    }

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    token_info["claude"] = {
        "provider": "Anthropic (Claude)",
        "api_key_set": bool(anthropic_key),
        "note": "Check usage at https://console.anthropic.com/settings/usage"
        if anthropic_key
        else "ANTHROPIC_API_KEY not found",
        "check_method": "API dashboard" if anthropic_key else None,
    }

    google_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    token_info["gemini"] = {
        "provider": "Google (Gemini)",
        "api_key_set": bool(google_key),
        "note": "Check usage at https://aistudio.google.com/apikey"
        if google_key
        else "GOOGLE_API_KEY or GEMINI_API_KEY not found",
        "check_method": "Google AI Studio" if google_key else None,
    }

    antigravity_template = os.environ.get("ANTIGRAVITY_CMD_TEMPLATE")
    token_info["antigravity"] = {
        "provider": "Antigravity",
        "api_key_set": bool(antigravity_template),
        "note": "Execution requires ANTIGRAVITY_CMD_TEMPLATE",
        "check_method": "Environment template" if antigravity_template else None,
    }

    return token_info


def template_env_var(provider: str) -> Optional[str]:
    config = provider_config(provider)
    if not config:
        return None
    return config.get("template_env")


def is_template_required(provider: str) -> bool:
    config = provider_config(provider)
    if not config:
        return False
    return bool(config.get("template_required", False))


def provider_command(provider: str, executable: str, use_stdin: bool = True) -> List[str]:
    config = provider_config(provider)
    if not config:
        raise ValueError(f"Unknown provider: {provider}")

    if use_stdin:
        cmd_args = config.get("stdin_cmd", config.get("cmd", []))
    else:
        cmd_args = config.get("cmd", [])

    return [executable] + list(cmd_args)
