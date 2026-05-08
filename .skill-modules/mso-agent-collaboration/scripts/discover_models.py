#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_TIMEOUT = 5


def _http_get_json(url: str, headers: Dict[str, str], timeout: int = 20) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _unique(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return sorted(out)


def _extract_json_array(text: str) -> List[str]:
    value = (text or "").strip()
    if not value:
        return []

    def _from_obj(obj: Any) -> List[str]:
        if isinstance(obj, list):
            if all(isinstance(x, str) for x in obj):
                return _unique([str(x) for x in obj])
            models: List[str] = []
            for item in obj:
                if isinstance(item, dict):
                    candidate = item.get("id") or item.get("name") or item.get("model")
                    if candidate:
                        models.append(str(candidate))
            return _unique(models)
        if isinstance(obj, dict):
            for key in ("models", "items", "data", "result", "content", "message", "text"):
                if key in obj:
                    maybe = _from_obj(obj[key])
                    if maybe:
                        return maybe
        return []

    try:
        parsed = json.loads(value)
        models = _from_obj(parsed)
        if models:
            return models
    except Exception:
        pass

    # Common LLM formatting fallback: fenced JSON block.
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", value, flags=re.IGNORECASE)
    for block in fenced:
        try:
            parsed = json.loads(block.strip())
            models = _from_obj(parsed)
            if models:
                return models
        except Exception:
            continue

    # Generic fallback: pull first JSON array-ish segment.
    start = value.find("[")
    end = value.rfind("]")
    if start != -1 and end != -1 and end > start:
        snippet = value[start : end + 1]
        try:
            parsed = json.loads(snippet)
            models = _from_obj(parsed)
            if models:
                return models
        except Exception:
            pass

    # Last fallback: bullet/line parsing with model-like token filter.
    token_like = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")
    lines = []
    for raw in value.splitlines():
        line = raw.strip().lstrip("-").strip()
        if not line:
            continue
        if token_like.match(line):
            lines.append(line)
    return _unique(lines)


def _resolve_bin(provider: str) -> str:
    env_map = {
        "codex": "CODEX_BIN",
        "claude": "CLAUDE_BIN",
        "gemini": "GEMINI_BIN",
    }
    env_name = env_map.get(provider, "")
    if env_name:
        env_path = os.getenv(env_name)
        if env_path and os.path.exists(env_path):
            return env_path
    path = shutil.which(provider)
    if path:
        return path
    raise RuntimeError(f"{provider} CLI not found")


def _compact_error(text: str, *, limit: int = 240) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return "unknown error"
    first = lines[0]
    if len(first) <= limit:
        return first
    return first[: limit - 3] + "..."


def _cli_prompt(provider: str) -> str:
    return (
        f"You are running inside {provider} CLI. "
        "Return ONLY a JSON array of model IDs currently available for this account/session. "
        'Example: ["model-a","model-b"]. No markdown, no prose.'
    )


def _discover_via_cli(provider: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[List[str], Optional[str]]:
    try:
        bin_path = _resolve_bin(provider)
    except Exception as exc:
        return [], str(exc)

    prompt = _cli_prompt(provider)

    if provider == "codex":
        cmd = [bin_path, "exec", "--skip-git-repo-check", prompt]
    elif provider == "claude":
        cmd = [bin_path, "-p", "--output-format", "json", prompt]
    elif provider == "gemini":
        cmd = [bin_path, "-o", "json", "-p", prompt]
    else:
        return [], f"Unsupported provider: {provider}"

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [], f"cli discovery timed out after {timeout}s"
    except Exception as exc:
        return [], str(exc)

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        detail = _compact_error(stderr) if stderr else f"exit={completed.returncode}"
        return [], f"cli discovery failed ({detail})"

    models = _extract_json_array(stdout)
    if models:
        return models, None

    return [], "cli discovery returned no parseable model list"


def _discover_openai_models() -> List[str]:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required")

    data = _http_get_json(
        "https://api.openai.com/v1/models",
        {"Authorization": f"Bearer {key}"},
    )
    rows = data.get("data", [])
    model_ids: List[str] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = str(row.get("id") or "").strip()
            if not model_id:
                continue
            if model_id.startswith("gpt-") or model_id.startswith("o"):
                model_ids.append(model_id)
    return _unique(model_ids)


def _discover_anthropic_models() -> List[str]:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is required")

    data = _http_get_json(
        "https://api.anthropic.com/v1/models",
        {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    rows = data.get("data", [])
    model_ids: List[str] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = str(row.get("id") or "").strip()
            if model_id:
                model_ids.append(model_id)
    return _unique(model_ids)


def _discover_gemini_models() -> List[str]:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is required")

    base = "https://generativelanguage.googleapis.com/v1beta/models"
    page_token = ""
    model_ids: List[str] = []

    while True:
        params = {"key": key, "pageSize": "1000"}
        if page_token:
            params["pageToken"] = page_token
        url = f"{base}?{urllib.parse.urlencode(params)}"
        data = _http_get_json(url, {})

        rows = data.get("models", [])
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "").strip()
                if not name:
                    continue
                if name.startswith("models/"):
                    name = name[len("models/") :]
                if "gemini" in name:
                    model_ids.append(name)

        next_token = str(data.get("nextPageToken") or "").strip()
        if not next_token:
            break
        page_token = next_token

    return _unique(model_ids)


def _discover_via_api(provider: str) -> Tuple[List[str], Optional[str]]:
    try:
        if provider == "codex":
            return _discover_openai_models(), None
        if provider == "claude":
            return _discover_anthropic_models(), None
        if provider == "gemini":
            return _discover_gemini_models(), None
        return [], f"Unsupported provider: {provider}"
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        message = f"HTTP {exc.code} during API discovery"
        if detail:
            message += f": {detail[:600]}"
        return [], message
    except urllib.error.URLError as exc:
        return [], f"Network error during API discovery: {exc}"
    except Exception as exc:
        return [], str(exc)


def discover(provider: str) -> Tuple[List[str], Optional[str]]:
    provider = provider.strip().lower()

    api_models, api_err = _discover_via_api(provider)
    if api_models:
        return api_models, None

    cli_models, cli_err = _discover_via_cli(provider)
    if cli_models:
        return cli_models, None

    if cli_err and api_err:
        return [], f"api: {api_err}; cli: {cli_err}"
    return [], api_err or cli_err or "model discovery failed"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: discover_models.py <codex|claude|gemini>", file=sys.stderr)
        return 2

    provider = sys.argv[1]
    models, err = discover(provider)

    # Best-effort mode (default): never block normal workflow.
    # If discovery is unavailable in current environment/session,
    # return an empty list instead of failing.
    strict = os.getenv("AI_COLLABORATOR_DISCOVERY_STRICT", "").strip() in {"1", "true", "TRUE", "yes", "YES"}
    if err and strict:
        print(err, file=sys.stderr)
        return 1

    print(json.dumps(models or [], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
