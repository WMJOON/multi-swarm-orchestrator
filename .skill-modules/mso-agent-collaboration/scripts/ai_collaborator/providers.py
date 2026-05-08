from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None

DEFAULT_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "codex": {
        "env_var": "CODEX_BIN",
        "binary_names": ["codex"],
        "alt_paths": ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"],
        "cmd": ["exec", "--skip-git-repo-check"],
        "stdin_cmd": ["exec", "--skip-git-repo-check"],
        "description": "OpenAI Codex CLI",
        "model_flag": "-m",
        "model_position": "after_subcommand",
        "model_env_vars": ["CODEX_MODEL", "OPENAI_MODEL"],
        "default_model": "gpt-5-codex",
        "models": ["gpt-5-codex", "gpt-5", "gpt-5-mini", "o4-mini", "o3"],
        "discover_models_cmd": "python3 scripts/discover_models.py codex",
        "discover_timeout": 20,
        "template_required": False,
    },
    "claude": {
        "env_var": "CLAUDE_BIN",
        "binary_names": ["claude"],
        "alt_paths": ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"],
        "cmd": ["-p"],
        "stdin_cmd": [],
        "description": "Anthropic Claude Code CLI",
        "model_flag": "--model",
        "model_position": "append",
        "model_env_vars": ["CLAUDE_MODEL", "ANTHROPIC_MODEL"],
        "default_model": "sonnet",
        "models": ["sonnet", "opus", "claude-sonnet-4-5-20250929", "claude-opus-4-1-20250805"],
        "discover_models_cmd": "python3 scripts/discover_models.py claude",
        "discover_timeout": 20,
        "template_required": False,
    },
    "gemini": {
        "env_var": "GEMINI_BIN",
        "binary_names": ["gemini"],
        "alt_paths": ["/opt/homebrew/bin/gemini", "/usr/local/bin/gemini"],
        "cmd": [],
        "stdin_cmd": [],
        "description": "Google Gemini CLI",
        "model_flag": "-m",
        "model_position": "append",
        "model_env_vars": ["GEMINI_MODEL", "GOOGLE_MODEL"],
        "default_model": "gemini-2.5-pro",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"],
        "discover_models_cmd": "python3 scripts/discover_models.py gemini",
        "discover_timeout": 20,
        "template_required": False,
    },
}

_REGISTRY_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_CACHE_SOURCE: Optional[Path] = None


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_config_path() -> Path:
    return _skill_root() / "config" / "providers.yaml"


def config_path() -> Path:
    raw = os.environ.get("AI_COLLABORATOR_CONFIG")
    if raw:
        return Path(raw).expanduser()
    return _default_config_path()


def _env_name(provider: str, suffix: str) -> str:
    return f"AI_COLLABORATOR_{provider.upper()}_{suffix}"


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(value).strip()]


def _as_cmd_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [token for token in shlex.split(value) if token.strip()]
    return []


def _first_env(var_names: Sequence[str]) -> Tuple[Optional[str], Optional[str]]:
    for var_name in var_names:
        value = os.environ.get(var_name)
        if value:
            return var_name, value
    return None, None


def _normalize_provider(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    base = dict(DEFAULT_PROVIDERS.get(name, {}))
    merged = {**base, **payload}

    merged["name"] = name
    merged["enabled"] = bool(merged.get("enabled", True))
    merged["env_var"] = str(merged.get("env_var") or f"{name.upper()}_BIN")
    merged["binary_names"] = _as_list(merged.get("binary_names")) or [name]
    merged["alt_paths"] = _as_list(merged.get("alt_paths"))
    merged["cmd"] = _as_cmd_list(merged.get("cmd"))
    merged["stdin_cmd"] = _as_cmd_list(merged.get("stdin_cmd")) if merged.get("stdin_cmd") is not None else list(merged["cmd"])
    merged["description"] = str(merged.get("description") or name)
    merged["model_flag"] = str(merged.get("model_flag")).strip() if merged.get("model_flag") else None
    merged["model_position"] = str(merged.get("model_position") or "append").strip()
    merged["model_env_vars"] = _as_list(merged.get("model_env_vars"))
    merged["default_model"] = str(merged.get("default_model")).strip() if merged.get("default_model") else None
    merged["models"] = _as_list(merged.get("models"))
    merged["discover_models_cmd"] = merged.get("discover_models_cmd") or ""
    merged["discover_timeout"] = int(merged.get("discover_timeout") or 20)
    merged["template_env"] = str(merged.get("template_env")).strip() if merged.get("template_env") else None
    merged["template_required"] = bool(merged.get("template_required", False))

    return merged


def _load_registry_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    if yaml is None:
        raise RuntimeError("PyYAML is required to load providers.yaml. Install with: pip install pyyaml")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not data:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Provider config must be an object: {path}")
    return data


def _provider_entries(data: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    providers = data.get("providers")
    entries: List[Tuple[str, Dict[str, Any]]] = []

    if isinstance(providers, list):
        for row in providers:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("id") or "").strip()
            if not name:
                continue
            row_copy = dict(row)
            row_copy.pop("name", None)
            row_copy.pop("id", None)
            entries.append((name, row_copy))
        return entries

    if isinstance(providers, dict):
        for key, row in providers.items():
            if isinstance(row, dict):
                entries.append((str(key).strip(), dict(row)))
        return entries

    if not providers:
        for key, row in DEFAULT_PROVIDERS.items():
            entries.append((key, dict(row)))
    return entries


def load_provider_registry(force: bool = False) -> Dict[str, Dict[str, Any]]:
    global _REGISTRY_CACHE, _CACHE_SOURCE

    path = config_path()
    if not force and _REGISTRY_CACHE is not None and _CACHE_SOURCE == path:
        return _REGISTRY_CACHE

    file_data = _load_registry_file(path)
    entries = _provider_entries(file_data)
    by_name: Dict[str, Dict[str, Any]] = {}
    ordered_names: List[str] = []

    for name, payload in entries:
        name = name.strip()
        if not name:
            continue
        by_name[name] = _normalize_provider(name, payload)
        ordered_names.append(name)

    # Keep defaults as fallback providers when config omits them.
    for name, payload in DEFAULT_PROVIDERS.items():
        if name not in by_name:
            by_name[name] = _normalize_provider(name, payload)
            ordered_names.append(name)

    registry: Dict[str, Dict[str, Any]] = {}
    for name in ordered_names:
        item = by_name[name]
        if item.get("enabled", True):
            registry[name] = item

    _REGISTRY_CACHE = registry
    _CACHE_SOURCE = path
    return registry


def provider_names() -> List[str]:
    return list(load_provider_registry().keys())


def provider_config(provider: str) -> Optional[Dict[str, Any]]:
    return load_provider_registry().get(provider)


def template_env_candidates(provider: str) -> List[str]:
    config = provider_config(provider)
    if not config:
        return []

    names = [_env_name(provider, "CMD_TEMPLATE")]
    if config.get("template_env"):
        names.append(str(config["template_env"]))
    names.append(f"{provider.upper()}_CMD_TEMPLATE")

    seen: List[str] = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return seen


def template_env_var(provider: str) -> Optional[str]:
    candidates = template_env_candidates(provider)
    return candidates[0] if candidates else None


def resolve_template(provider: str) -> Tuple[Optional[str], Optional[str]]:
    return _first_env(template_env_candidates(provider))


def is_template_required(provider: str) -> bool:
    config = provider_config(provider)
    if not config:
        return False
    return bool(config.get("template_required", False))


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


def _cli_version(executable: Optional[str]) -> Optional[str]:
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None

    text = (completed.stdout or "").strip() or (completed.stderr or "").strip()
    return text or None


def _dedupe(values: Sequence[str]) -> List[str]:
    out: List[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in out:
            out.append(item)
    return out


def resolve_default_model(provider: str) -> Optional[str]:
    config = provider_config(provider)
    if not config:
        return None

    env_candidates = [_env_name(provider, "DEFAULT_MODEL")]
    env_candidates.extend(config.get("model_env_vars", []))
    _name, value = _first_env(env_candidates)
    if value:
        return value

    default_model = config.get("default_model")
    if isinstance(default_model, str) and default_model.strip():
        return default_model.strip()
    return None


def configured_models(provider: str) -> List[str]:
    config = provider_config(provider)
    if not config:
        return []

    models = list(config.get("models", []))
    default = resolve_default_model(provider)
    if default:
        models.append(default)
    return _dedupe(models)


def provider_command(provider: str, executable: str, *, use_stdin: bool = True, model: Optional[str] = None) -> List[str]:
    config = provider_config(provider)
    if not config:
        raise ValueError(f"Unknown provider: {provider}")

    if use_stdin:
        cmd_args = list(config.get("stdin_cmd", config.get("cmd", [])))
    else:
        cmd_args = list(config.get("cmd", []))

    cmd_args = [str(token).strip() for token in cmd_args if str(token).strip()]
    model_flag = config.get("model_flag")

    if model and model_flag:
        position = config.get("model_position", "append")
        if position == "after_subcommand" and cmd_args:
            cmd_args = [cmd_args[0], model_flag, model] + cmd_args[1:]
        else:
            cmd_args = cmd_args + [model_flag, model]

    return [executable] + cmd_args


def _parse_model_text(text: str) -> List[str]:
    value = (text or "").strip()
    if not value:
        return []

    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return _dedupe([str(item) for item in parsed if str(item).strip()])
        if isinstance(parsed, dict):
            for key in ("models", "items", "data"):
                items = parsed.get(key)
                if isinstance(items, list):
                    extracted: List[str] = []
                    for item in items:
                        if isinstance(item, str):
                            extracted.append(item)
                        elif isinstance(item, dict):
                            candidate = item.get("id") or item.get("name") or item.get("model")
                            if candidate:
                                extracted.append(str(candidate))
                    models = _dedupe(extracted)
                    if models:
                        return models
    except Exception:
        pass

    lines: List[str] = []
    for raw in value.splitlines():
        line = raw.strip().lstrip("-").strip()
        if not line:
            continue
        lines.append(line)
    return _dedupe(lines)


def discover_provider_models(provider: str, timeout: Optional[int] = None) -> Tuple[List[str], Optional[str]]:
    config = provider_config(provider)
    if not config:
        return [], f"Unknown provider: {provider}"

    discover_cmd = os.environ.get(_env_name(provider, "DISCOVER_MODELS_CMD")) or config.get("discover_models_cmd")
    if not discover_cmd:
        return [], None

    timeout_seconds = int(timeout or config.get("discover_timeout") or 20)

    try:
        if isinstance(discover_cmd, list):
            completed = subprocess.run(
                [str(item) for item in discover_cmd],
                capture_output=True,
                text=True,
                cwd=str(_skill_root()),
                timeout=timeout_seconds,
                check=False,
            )
        else:
            completed = subprocess.run(
                ["bash", "-lc", str(discover_cmd)],
                capture_output=True,
                text=True,
                cwd=str(_skill_root()),
                timeout=timeout_seconds,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return [], f"model discovery timed out after {timeout_seconds}s"
    except Exception as exc:
        return [], str(exc)

    raw = (completed.stdout or "").strip()
    err = (completed.stderr or "").strip()
    if completed.returncode != 0:
        return [], err or f"model discovery failed (exit={completed.returncode})"

    models = _parse_model_text(raw)
    if not models and err:
        return [], err
    return models, None


def check_provider_status() -> Dict[str, Dict[str, Any]]:
    status: Dict[str, Dict[str, Any]] = {}
    for provider, config in load_provider_registry().items():
        executable = find_executable(provider)
        _template_name, _template = resolve_template(provider)
        status[provider] = {
            "available": executable is not None,
            "path": executable,
            "version": _cli_version(executable),
            "description": config["description"],
            "model_flag": config.get("model_flag"),
            "configured_default_model": resolve_default_model(provider),
            "config_path": str(config_path()),
        }
    return status


def get_model_catalog(provider_filter: Optional[str] = None, include_discovery: bool = False) -> Dict[str, Dict[str, Any]]:
    providers = [provider_filter] if provider_filter else provider_names()
    catalog: Dict[str, Dict[str, Any]] = {}

    for provider in providers:
        config = provider_config(provider)
        if not config:
            continue

        executable = find_executable(provider)
        configured = configured_models(provider)
        discovered: List[str] = []
        discover_error: Optional[str] = None

        if include_discovery:
            discovered, discover_error = discover_provider_models(provider)

        available = _dedupe(configured + discovered)
        catalog[provider] = {
            "provider": config["description"],
            "available": executable is not None,
            "path": executable,
            "version": _cli_version(executable),
            "model_flag": config.get("model_flag"),
            "default_model": resolve_default_model(provider),
            "configured_models": configured,
            "discovered_models": discovered,
            "available_models": available,
            "discover_error": discover_error,
            "config_path": str(config_path()),
        }

    return catalog


def _default_model_cache_path() -> Path:
    return _skill_root() / "history" / "models" / "catalog.json"


def refresh_model_cache(
    provider_filter: Optional[str] = None,
    *,
    cache_path: Optional[str] = None,
) -> Dict[str, Any]:
    providers = [provider_filter] if provider_filter else provider_names()
    results: Dict[str, Any] = {}
    for provider in providers:
        discovered, error = discover_provider_models(provider)
        results[provider] = {
            "discovered_models": discovered,
            "discover_error": error,
            "configured_models": configured_models(provider),
        }

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "config_path": str(config_path()),
        "providers": results,
    }

    if cache_path:
        cache = Path(cache_path).expanduser()
    else:
        cache = _default_model_cache_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload["cache_path"] = str(cache)
    return payload


def write_discovered_models_to_config(provider_models: Dict[str, List[str]]) -> Dict[str, List[str]]:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if yaml is None:
        raise RuntimeError("PyYAML is required to update providers.yaml. Install with: pip install pyyaml")

    data = _load_registry_file(path) if path.exists() else {}
    providers = data.get("providers")

    if not isinstance(providers, list):
        providers = []
        for name in provider_names():
            config = provider_config(name) or {}
            providers.append(
                {
                    "name": name,
                    "description": config.get("description"),
                    "env_var": config.get("env_var"),
                    "binary_names": config.get("binary_names", []),
                    "alt_paths": config.get("alt_paths", []),
                    "cmd": config.get("cmd", []),
                    "stdin_cmd": config.get("stdin_cmd", []),
                    "model_flag": config.get("model_flag"),
                    "model_position": config.get("model_position"),
                    "model_env_vars": config.get("model_env_vars", []),
                    "default_model": config.get("default_model"),
                    "models": config.get("models", []),
                    "discover_models_cmd": config.get("discover_models_cmd", ""),
                }
            )
        data["providers"] = providers

    changed: Dict[str, List[str]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    for row in providers:
        if isinstance(row, dict):
            name = str(row.get("name") or row.get("id") or "").strip()
            if name:
                by_name[name] = row

    for provider, models in provider_models.items():
        if not models:
            continue
        row = by_name.get(provider)
        if row is None:
            row = {"name": provider}
            providers.append(row)
            by_name[provider] = row

        merged = _dedupe(list(row.get("models", [])) + list(models))
        row["models"] = merged
        changed[provider] = merged

    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    load_provider_registry(force=True)
    return changed
