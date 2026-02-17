#!/usr/bin/env python3
"""Runtime workspace utilities for MSO v0.0.2.

This module centralizes runtime path resolution, run lifecycle metadata,
policy scaffolding, and workspace relocation detection.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

PHASE_TO_DIR: Dict[str, str] = {
    "00": "00_collect",
    "10": "10_topology",
    "20": "20_mental-model",
    "30": "30_execution",
    "40": "40_collaboration",
    "50": "50_audit",
    "60": "60_observability",
    "70": "70_governance",
    "80": "80_delivery",
    "90": "90_meta",
}
PHASE_DIRS: List[str] = [PHASE_TO_DIR[key] for key in sorted(PHASE_TO_DIR.keys())]

SKILL_KEY_ENUM = {
    "msogov",
    "msowd",
    "msomm",
    "msoed",
    "msotcm",
    "msoac",
    "msoal",
    "msoobs",
}

RUN_ID_PATTERN = re.compile(r"^(?P<date>\d{8})-(?P<skill_key>[a-z]+)-(?P<case_slug>[a-z0-9-]{1,40})$")

DEFAULT_SKILL_KEY_MAP: Dict[str, str] = {
    "mso-skill-governance": "msogov",
    "mso-workflow-topology-design": "msowd",
    "mso-mental-model-design": "msomm",
    "mso-execution-design": "msoed",
    "mso-task-context-management": "msotcm",
    "mso-agent-collaboration": "msoac",
    "mso-agent-audit-log": "msoal",
    "mso-observability": "msoobs",
    "msogov": "msogov",
    "msowd": "msowd",
    "msomm": "msomm",
    "msoed": "msoed",
    "msotcm": "msotcm",
    "msoac": "msoac",
    "msoal": "msoal",
    "msoobs": "msoobs",
}

DEFAULT_POLICY: Dict[str, Any] = {
    "run_policy": {
        "max_active_runs": 10,
        "auto_archive_after_days": 7,
        "require_manifest_on_create": True,
    },
    "archive_policy": {
        "retention_days": 90,
        "grouping": "monthly",
    },
    "tmp_policy": {
        "ingest_ttl_hours": 0,
        "tool_cache_ttl_days": 7,
        "exports_ttl_days": None,
    },
    "observation_policy": {
        "auto_sync": True,
        "sync_phases": [10, 20, 30, 60],
    },
    "relocation_policy": {
        "verify_on_startup": True,
        "search_max_depth": 5,
        "fallback_walk_depth": 3,
        "peer_search_paths": [],
        "on_peer_missing": "warn_and_continue",
    },
}


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _iso(now: datetime | None = None) -> str:
    return _utc_now(now).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


PACK_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = PACK_ROOT.parent
DEFAULT_WORKSPACE_ROOT = "workspace"
DEFAULT_OBSERVATION_ROOT = "mso-observation-workspace"
DEFAULT_POLICY_PATH = "workspace/.mso-context/config/policy.yaml"


def _resolve_pack_root(base_hint: Path | str | None = None) -> Path:
    if base_hint is None:
        return PACK_ROOT

    candidate = Path(base_hint).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent

    if candidate.name == "skills":
        return candidate.parent
    if candidate.name == "_shared" and candidate.parent.name == "skills":
        return candidate.parent.parent
    return candidate


def _safe_dump_yaml(data: Dict[str, Any]) -> str:
    if yaml is not None:
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=False)
    return json.dumps(data, ensure_ascii=True, indent=2) + "\n"


def _json_load(path: Path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not path.exists():
        return {} if default is None else dict(default)
    raw = _read_text(path).strip()
    if not raw:
        return {} if default is None else dict(default)
    try:
        data = json.loads(raw)
    except Exception:
        return {} if default is None else dict(default)
    return data if isinstance(data, dict) else ({} if default is None else dict(default))


def _json_dump(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _deep_merge_missing(target: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in defaults.items():
        if key not in target:
            target[key] = value
            continue
        if isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge_missing(target[key], value)
    return target


def sanitize_case_slug(case_slug: str | None) -> str:
    raw = (case_slug or "").strip().lower()
    raw = re.sub(r"[^a-z0-9-]", "-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-")
    if not raw:
        raw = "default-run"
    return raw[:40]


def normalize_skill_key(skill_key: str, skill_key_map: Dict[str, str] | None = None, strict: bool = True) -> str:
    mapping = dict(DEFAULT_SKILL_KEY_MAP)
    if skill_key_map:
        for k, v in skill_key_map.items():
            mapping[str(k)] = str(v)
    key = str(skill_key).strip()
    normalized = mapping.get(key, key)
    if normalized not in SKILL_KEY_ENUM:
        if strict:
            raise ValueError(f"invalid skill_key: {skill_key}")
        return "msowd"
    return normalized


def generate_run_id(skill_key: str, case_slug: str, now: datetime | None = None) -> str:
    normalized_key = normalize_skill_key(skill_key)
    date_part = _utc_now(now).strftime("%Y%m%d")
    slug = sanitize_case_slug(case_slug)
    return f"{date_part}-{normalized_key}-{slug}"


def validate_run_id(run_id: str) -> str:
    """Validate run_id format and canonicalize to a strict v0.0.2 format."""
    candidate = str(run_id).strip()
    match = RUN_ID_PATTERN.fullmatch(candidate)
    if not match:
        raise ValueError(
            "run_id must match YYYYMMDD-<skill-key>-<case-slug> "
            "for example 20260217-msowd-sample-run"
        )
    if match.group("skill_key") not in SKILL_KEY_ENUM:
        raise ValueError(f"invalid skill_key in run_id: {match.group('skill_key')}")
    return candidate


def _to_abs(path_raw: str | Path, base: Path) -> Path:
    p = Path(path_raw).expanduser()
    if not p.is_absolute():
        p = (base / p).resolve()
    return p.resolve()


def _discover_project_root(start: Path) -> Path | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip()).resolve()
    except Exception:
        pass

    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
        if (candidate / ".mso-context").exists():
            return candidate.parent
    return None


def _bounded_walk_find(root: Path, target_dir_name: str, max_depth: int) -> List[Path]:
    candidates: List[Path] = []
    root = root.resolve()
    for current_root, dirs, _files in os.walk(root):
        current = Path(current_root)
        rel = current.relative_to(root)
        depth = 0 if str(rel) == "." else len(rel.parts)
        if depth >= max_depth:
            dirs[:] = []
        if target_dir_name in dirs:
            hit = current / target_dir_name
            candidates.append(hit.resolve())
    return candidates


def _anchor_template(anchor_type: str, canonical_path: Path) -> Dict[str, Any]:
    prefix = "ws" if anchor_type == "mso-workspace" else "obs"
    return {
        "type": anchor_type,
        "workspace_id": f"{prefix}-{uuid.uuid4()}",
        "created_at": _iso(),
        "canonical_path": str(canonical_path.resolve()),
        "peers": {},
    }


def _extract_observer_id(observer_link: str, fallback: str) -> str:
    text = observer_link.strip()
    if not text:
        return fallback

    marker = "mso-observation-workspace"
    if marker in text:
        tail = text.split(marker, 1)[1].strip("/\\")
        parts = [p for p in re.split(r"[\\/]", tail) if p]
        if parts:
            return parts[0]

    parts = [p for p in re.split(r"[\\/]", text) if p]
    if len(parts) >= 2:
        return parts[-2]
    return fallback


def _candidate_roots_from_parent_scan(start: Path, depth: int) -> List[Path]:
    out: List[Path] = []
    cursor = start.resolve()
    for _ in range(max(0, depth)):
        cursor = cursor.parent
        out.append(cursor)
    return out


def _search_peer_root(
    *,
    target_type: str,
    expected_workspace_id: str | None,
    settings: Dict[str, Any],
    policy: Dict[str, Any],
    current_workspace_root: Path,
) -> Path | None:
    search_max_depth = int(policy.get("search_max_depth", 5) or 5)
    walk_depth = int(policy.get("fallback_walk_depth", 3) or 3)
    peer_search_paths = policy.get("peer_search_paths", [])
    if not isinstance(peer_search_paths, list):
        peer_search_paths = []

    target_name = "mso-observation-workspace" if target_type == "mso-observation" else ".mso-context"

    # 1) env vars
    env_key = "MSO_OBSERVATION_ROOT" if target_type == "mso-observation" else "MSO_WORKSPACE_ROOT"
    env_value = os.environ.get(env_key)
    if env_value:
        env_root = Path(env_value).expanduser().resolve()
        if target_type == "mso-workspace" and env_root.name == ".mso-context":
            env_root = env_root.parent
        if (env_root / ".anchor.json").exists() or (env_root / ".mso-context" / ".anchor.json").exists():
            return env_root

    # 2) project root find
    project_root = _discover_project_root(current_workspace_root)
    if project_root is not None:
        for found in _bounded_walk_find(project_root, target_name, search_max_depth):
            candidate_root = found if target_type == "mso-observation" else found.parent
            anchor_path = candidate_root / ".anchor.json"
            if target_type == "mso-workspace":
                anchor_path = candidate_root / ".mso-context" / ".anchor.json"
            anchor_data = _json_load(anchor_path)
            if not anchor_data:
                continue
            if expected_workspace_id and anchor_data.get("workspace_id") != expected_workspace_id:
                continue
            return candidate_root

    # 3) parent scan
    for root in _candidate_roots_from_parent_scan(current_workspace_root, walk_depth):
        for found in _bounded_walk_find(root, target_name, 2):
            candidate_root = found if target_type == "mso-observation" else found.parent
            anchor_path = candidate_root / ".anchor.json"
            if target_type == "mso-workspace":
                anchor_path = candidate_root / ".mso-context" / ".anchor.json"
            anchor_data = _json_load(anchor_path)
            if not anchor_data:
                continue
            if expected_workspace_id and anchor_data.get("workspace_id") != expected_workspace_id:
                continue
            return candidate_root

    # 4) config peer_search_paths
    for raw in peer_search_paths:
        try:
            root = _to_abs(str(raw), settings["project_root"])
        except Exception:
            continue
        for found in _bounded_walk_find(root, target_name, search_max_depth):
            candidate_root = found if target_type == "mso-observation" else found.parent
            anchor_path = candidate_root / ".anchor.json"
            if target_type == "mso-workspace":
                anchor_path = candidate_root / ".mso-context" / ".anchor.json"
            anchor_data = _json_load(anchor_path)
            if not anchor_data:
                continue
            if expected_workspace_id and anchor_data.get("workspace_id") != expected_workspace_id:
                continue
            return candidate_root

    # 5) HITL required
    return None


def _normalize_on_peer_missing_policy(value: Any) -> str:
    normalized = str(value).strip().lower() if value is not None else "warn_and_continue"
    if normalized in {"warn", "warn_and_continue", "block", "silent"}:
        return normalized
    return "warn_and_continue"


def _append_peer_missing_event(
    events: List[Dict[str, Any]],
    base: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    mode = _normalize_on_peer_missing_policy(policy.get("on_peer_missing"))
    base = dict(base)
    base["on_peer_missing_policy"] = mode
    if mode in {"warn", "warn_and_continue", "block"}:
        base.setdefault("requires_manual_input", True)
    if mode == "block":
        base["blocked_by_policy"] = True
    events.append(base)
    return {"events": events, "blocked": mode == "block"}


def resolve_runtime_settings(base_hint: Path | str | None = None) -> Dict[str, Any]:
    pack_root = _resolve_pack_root(base_hint).resolve()
    project_root = pack_root.parent.resolve()

    workspace_root = os.environ.get("MSO_WORKSPACE_ROOT") or DEFAULT_WORKSPACE_ROOT
    observation_root = os.environ.get("MSO_OBSERVATION_ROOT") or DEFAULT_OBSERVATION_ROOT
    observer_id = os.environ.get("MSO_OBSERVER_ID") or os.environ.get("USER") or "unknown"

    workspace_root_path = _to_abs(workspace_root, project_root)
    observation_root_path = _to_abs(observation_root, project_root)
    policy_path = _to_abs(DEFAULT_POLICY_PATH, project_root)

    return {
        "pack_root": pack_root,
        "project_root": project_root,
        "workspace_root": workspace_root_path,
        "observation_root": observation_root_path,
        "observer_id": str(observer_id),
        "strict_runtime_only": True,
        "skill_key_map": dict(DEFAULT_SKILL_KEY_MAP),
        "policy_path": policy_path,
    }


def ensure_policy_yaml(paths_or_settings: Dict[str, Any]) -> Path:
    settings = paths_or_settings.get("settings", paths_or_settings)
    policy_path = Path(settings.get("policy_path") or Path(settings["workspace_root"]) / ".mso-context" / "config" / "policy.yaml").resolve()
    policy_path.parent.mkdir(parents=True, exist_ok=True)

    existing: Dict[str, Any] = {}
    if policy_path.exists() and policy_path.read_text(encoding="utf-8").strip():
        raw = policy_path.read_text(encoding="utf-8")
        try:
            loaded_json = json.loads(raw)
            if isinstance(loaded_json, dict):
                existing = loaded_json
        except Exception:
            pass
        if not existing and yaml is not None:
            try:
                loaded = yaml.safe_load(raw)
                if isinstance(loaded, dict):
                    existing = loaded
            except Exception:
                existing = {}

    merged = _deep_merge_missing(existing, json.loads(json.dumps(DEFAULT_POLICY)))
    policy_path.write_text(_safe_dump_yaml(merged), encoding="utf-8")
    return policy_path


def _load_policy(settings: Dict[str, Any]) -> Dict[str, Any]:
    policy_path = Path(settings.get("policy_path") or Path(settings["workspace_root"]) / ".mso-context" / "config" / "policy.yaml").resolve()
    if not policy_path.exists():
        ensure_policy_yaml(settings)
    if not policy_path.exists():
        return json.loads(json.dumps(DEFAULT_POLICY))

    raw = policy_path.read_text(encoding="utf-8").strip()
    if not raw:
        return json.loads(json.dumps(DEFAULT_POLICY))

    loaded: Dict[str, Any] | Any = {}
    try:
        loaded_json = json.loads(raw)
        if isinstance(loaded_json, dict):
            loaded = loaded_json
    except Exception:
        loaded = {}

    if not loaded and yaml is not None:
        try:
            loaded = yaml.safe_load(raw)
        except Exception:
            loaded = {}
    if not isinstance(loaded, dict):
        loaded = {}
    return _deep_merge_missing(loaded, json.loads(json.dumps(DEFAULT_POLICY)))


def _archive_due_runs(settings: Dict[str, Any]) -> List[str]:
    workspace_root = Path(settings["workspace_root"]).resolve()
    context_root = workspace_root / ".mso-context"
    active_root = context_root / "active"
    archive_root = context_root / "archive"
    moved: List[str] = []

    policy = _load_policy(settings)
    try:
        auto_days = int(policy.get("run_policy", {}).get("auto_archive_after_days", 7))
    except Exception:
        auto_days = 7
    if auto_days < 0:
        auto_days = 0

    now = _utc_now()
    for run_dir in sorted(active_root.glob("*")):
        if not run_dir.is_dir():
            continue
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = _json_load(manifest_path)
        status = str(manifest.get("status", "")).strip()
        if status not in {"completed", "failed"}:
            continue

        completed_at = manifest.get("completed_at") or manifest.get("updated_at") or manifest.get("created_at")
        try:
            completed_dt = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
        except Exception:
            completed_dt = now
        age_days = (now - _utc_now(completed_dt)).days
        if age_days < auto_days:
            continue

        month_bucket = _utc_now(completed_dt).strftime("%Y-%m")
        target = archive_root / month_bucket / run_dir.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            continue

        shutil.move(str(run_dir), str(target))
        moved.append(run_dir.name)

        archived_manifest_path = target / "manifest.json"
        archived_manifest = _json_load(archived_manifest_path)
        archived_manifest["status"] = "archived"
        archived_manifest["updated_at"] = _iso()
        archived_manifest.setdefault("completed_at", _iso())
        archived_manifest.setdefault("error", None)
        archived_manifest["archive_path"] = f"archive/{month_bucket}/{run_dir.name}/"
        _json_dump(archived_manifest_path, archived_manifest)

    return moved


def ensure_workspace_scaffold(base_hint_or_settings: Path | str | Dict[str, Any] | None = None) -> Dict[str, Any]:
    settings = (
        resolve_runtime_settings(base_hint_or_settings)
        if not isinstance(base_hint_or_settings, dict)
        else dict(base_hint_or_settings)
    )

    workspace_root = Path(settings["workspace_root"]).resolve()
    observation_root = Path(settings["observation_root"]).resolve()
    context_root = workspace_root / ".mso-context"

    for path in [
        context_root / "active",
        context_root / "archive",
        context_root / "registry",
        context_root / "config",
        workspace_root / "data" / "raw",
        workspace_root / "data" / "processed",
        workspace_root / "data" / "interim",
        workspace_root / "data" / "external",
        workspace_root / "reports" / "draft",
        workspace_root / "reports" / "published",
        workspace_root / "reports" / "archive",
        workspace_root / "tmp" / "ingest",
        workspace_root / "tmp" / "tool-cache",
        workspace_root / "tmp" / "exports",
        observation_root,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    policy_path = ensure_policy_yaml(settings)
    _archive_due_runs(settings)

    return {
        "settings": settings,
        "workspace_root": workspace_root,
        "observation_root": observation_root,
        "context_root": context_root,
        "active_root": context_root / "active",
        "archive_root": context_root / "archive",
        "registry_root": context_root / "registry",
        "config_root": context_root / "config",
        "manifest_index_path": context_root / "registry" / "manifest-index.jsonl",
        "policy_path": policy_path,
    }


def _phase_status_template() -> Dict[str, Dict[str, str]]:
    return {phase_dir: {"status": "pending"} for phase_dir in PHASE_DIRS}


def _resolve_pipeline_templates(run_id: str, default_paths: Dict[str, Path]) -> Dict[str, Path]:
    _ = run_id
    return {
        "workflow_output_dir": default_paths["workflow_output_dir"],
        "task_dir": default_paths["task_dir"],
        "observation_dir": default_paths["observation_dir"],
        "db_path": default_paths["db_path"],
    }


def resolve_runtime_paths(
    run_id: str | None,
    skill_key: str,
    case_slug: str,
    observer_id: str | None,
    create: bool = False,
    base_hint: Path | str | Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    settings = (
        resolve_runtime_settings(base_hint)
        if not isinstance(base_hint, dict)
        else dict(base_hint)
    )
    strict = settings["strict_runtime_only"]
    normalized_skill_key = normalize_skill_key(skill_key, settings["skill_key_map"], strict=True)
    resolved_run_id = validate_run_id(run_id or generate_run_id(normalized_skill_key, case_slug))
    resolved_observer_id = (observer_id or settings["observer_id"] or "unknown").strip() or "unknown"

    scaffold = ensure_workspace_scaffold(settings)
    context_root = scaffold["context_root"]
    active_root = scaffold["active_root"]

    run_root = active_root / resolved_run_id
    phases = {phase: run_root / phase for phase in PHASE_DIRS}

    observation_run_root = scaffold["observation_root"] / resolved_observer_id / resolved_run_id

    default_paths = {
        "project_root": settings["project_root"],
        "workflow_output_dir": phases["30_execution"],
        "task_dir": phases["40_collaboration"] / "task-context",
        "observation_dir": phases["60_observability"],
        "db_path": phases["50_audit"] / "agent_log.db",
    }
    rendered = _resolve_pipeline_templates(resolved_run_id, default_paths)

    paths: Dict[str, Any] = {
        "settings": settings,
        "strict_runtime_only": strict,
        "run_id": resolved_run_id,
        "skill_key": normalized_skill_key,
        "observer_id": resolved_observer_id,
        "workspace_root": scaffold["workspace_root"],
        "observation_root": scaffold["observation_root"],
        "context_root": context_root,
        "active_root": active_root,
        "archive_root": scaffold["archive_root"],
        "registry_root": scaffold["registry_root"],
        "config_root": scaffold["config_root"],
        "policy_path": scaffold["policy_path"],
        "manifest_index_path": scaffold["manifest_index_path"],
        "run_root": run_root,
        "phases": phases,
        "manifest_path": run_root / "manifest.json",
        "observation_run_root": observation_run_root,
        "observation_summary_dir": observation_run_root / "01_summary",
        "observation_decisions_dir": observation_run_root / "02_decisions",
        "observation_artifacts_dir": observation_run_root / "03_artifacts",
        "observation_review_dir": observation_run_root / "04_review",
        "observation_delivery_dir": observation_run_root / "05_delivery",
        "observation_readme_path": observation_run_root / "readme.md",
        "workflow_output_dir": rendered["workflow_output_dir"],
        "task_context_dir": rendered["task_dir"],
        "observability_dir": rendered["observation_dir"],
        "audit_db_path": rendered["db_path"],
        "topology_path": phases["10_topology"] / "workflow_topology_spec.json",
        "bundle_path": phases["20_mental-model"] / "mental_model_bundle.json",
        "execution_plan_path": phases["30_execution"] / "execution_plan.json",
        "governance_dir": phases["70_governance"],
    }

    if strict and not create and not run_root.exists():
        raise FileNotFoundError(f"runtime run context missing: {run_root}")

    if create:
        ensure_run_scaffold_and_manifest(paths, normalized_skill_key)
        relocation = ensure_anchors_and_detect_relocation(paths)
        if relocation.get("repaired"):
            sync_observation_artifacts(paths)

    return paths


def _validate_active_run_budget(paths: Dict[str, Any]) -> None:
    policy = _load_policy(paths["settings"])
    run_policy = policy.get("run_policy") if isinstance(policy.get("run_policy"), dict) else {}
    try:
        max_active_runs = int(run_policy.get("max_active_runs", 10))
    except Exception:
        max_active_runs = 10
    if max_active_runs < 0:
        max_active_runs = 0

    active_count = 0
    for run_dir in sorted(paths["active_root"].glob("*")):
        manifest_path = run_dir / "manifest.json"
        manifest = _json_load(manifest_path)
        if not manifest:
            continue
        status = str(manifest.get("status", "")).strip()
        if status in {"created", "active"}:
            active_count += 1

    if not paths["run_root"].exists() and active_count >= max_active_runs:
        raise RuntimeError(f"max_active_runs exceeded: {active_count}/{max_active_runs}")


def ensure_run_scaffold_and_manifest(
    paths: Dict[str, Any],
    skill_key: str | None = None,
    tags: List[str] | None = None,
    parent_run_id: str | None = None,
) -> Dict[str, Any]:
    _validate_active_run_budget(paths)

    paths["run_root"].mkdir(parents=True, exist_ok=True)
    for directory in paths["phases"].values():
        directory.mkdir(parents=True, exist_ok=True)

    # phase-specific helper directories
    (paths["task_context_dir"] / "tickets").mkdir(parents=True, exist_ok=True)
    (paths["task_context_dir"] / "archive").mkdir(parents=True, exist_ok=True)
    paths["audit_db_path"].parent.mkdir(parents=True, exist_ok=True)
    paths["observability_dir"].mkdir(parents=True, exist_ok=True)
    paths["governance_dir"].mkdir(parents=True, exist_ok=True)

    for obs_dir in [
        paths["observation_summary_dir"],
        paths["observation_decisions_dir"],
        paths["observation_artifacts_dir"],
        paths["observation_review_dir"],
        paths["observation_delivery_dir"],
    ]:
        obs_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = paths["manifest_path"]
    manifest = _json_load(manifest_path)
    now = _iso()

    if not manifest:
        manifest = {
            "run_id": paths["run_id"],
            "skill_key": normalize_skill_key(skill_key or paths["skill_key"], paths["settings"]["skill_key_map"]),
            "status": "created",
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "phases": _phase_status_template(),
            "observer_links": [str(paths["observation_run_root"].resolve())],
            "parent_run_id": parent_run_id,
            "tags": tags or [],
            "error": None,
        }
    else:
        manifest.setdefault("run_id", paths["run_id"])
        manifest.setdefault("skill_key", normalize_skill_key(skill_key or paths["skill_key"], paths["settings"]["skill_key_map"]))
        manifest.setdefault("status", "created")
        manifest.setdefault("created_at", now)
        manifest["updated_at"] = now
        manifest.setdefault("completed_at", None)
        phases = manifest.get("phases") if isinstance(manifest.get("phases"), dict) else {}
        for phase_dir in PHASE_DIRS:
            phase_payload = phases.get(phase_dir) if isinstance(phases.get(phase_dir), dict) else {}
            phase_payload.setdefault("status", "pending")
            phases[phase_dir] = phase_payload
        manifest["phases"] = phases
        links = manifest.get("observer_links") if isinstance(manifest.get("observer_links"), list) else []
        if str(paths["observation_run_root"].resolve()) not in links:
            links.append(str(paths["observation_run_root"].resolve()))
        manifest["observer_links"] = links
        manifest.setdefault("parent_run_id", parent_run_id)
        manifest.setdefault("tags", tags or [])
        manifest.setdefault("error", None)

    _json_dump(manifest_path, manifest)
    update_observation_readme(paths, manifest)
    return manifest


def load_manifest(paths: Dict[str, Any]) -> Dict[str, Any]:
    return _json_load(paths["manifest_path"])


def update_manifest_phase(paths: Dict[str, Any], phase: str, status: str) -> Dict[str, Any]:
    manifest = ensure_run_scaffold_and_manifest(paths)

    if phase in PHASE_TO_DIR:
        phase_dir = PHASE_TO_DIR[phase]
    elif phase in PHASE_DIRS:
        phase_dir = phase
    else:
        raise ValueError(f"unknown phase: {phase}")

    phases = manifest.get("phases") if isinstance(manifest.get("phases"), dict) else {}
    slot = phases.get(phase_dir) if isinstance(phases.get(phase_dir), dict) else {}
    slot["status"] = status
    phases[phase_dir] = slot
    manifest["phases"] = phases

    current_status = str(manifest.get("status", "created"))
    if current_status not in {"completed", "failed", "archived"}:
        if status == "failed":
            manifest["status"] = "failed"
            manifest.setdefault("completed_at", _iso())
        elif status in {"active", "completed", "skipped", "pending"}:
            manifest["status"] = "active"

    manifest["updated_at"] = _iso()
    _json_dump(paths["manifest_path"], manifest)

    sync_observation_artifacts(paths)
    update_observation_readme(paths, manifest)
    return manifest


def append_manifest_index(paths: Dict[str, Any], manifest: Dict[str, Any]) -> bool:
    index_path = Path(paths["manifest_index_path"])
    index_path.parent.mkdir(parents=True, exist_ok=True)

    existing_run_ids = set()
    if index_path.exists():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            run_id = payload.get("run_id")
            if isinstance(run_id, str):
                existing_run_ids.add(run_id)

    run_id = str(manifest.get("run_id", "")).strip()
    if run_id in existing_run_ids:
        return False

    archive_path = manifest.get("archive_path")
    if not isinstance(archive_path, str):
        archive_path = None

    record = {
        "run_id": run_id,
        "skill_key": manifest.get("skill_key"),
        "status": manifest.get("status"),
        "created_at": manifest.get("created_at"),
        "completed_at": manifest.get("completed_at"),
        "tags": manifest.get("tags") if isinstance(manifest.get("tags"), list) else [],
        "archive_path": archive_path,
    }

    with index_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def finalize_manifest(
    paths: Dict[str, Any],
    final_status: str,
    error: Dict[str, Any] | str | None = None,
    tags: List[str] | None = None,
) -> Dict[str, Any]:
    if final_status not in {"completed", "failed", "archived"}:
        raise ValueError("final_status must be completed|failed|archived")

    manifest = ensure_run_scaffold_and_manifest(paths)
    manifest["status"] = final_status
    manifest["updated_at"] = _iso()

    if final_status in {"completed", "failed"}:
        manifest["completed_at"] = manifest.get("completed_at") or _iso()

    if tags:
        existing = manifest.get("tags") if isinstance(manifest.get("tags"), list) else []
        merged = list(dict.fromkeys([*existing, *tags]))
        manifest["tags"] = merged

    if final_status == "failed":
        if isinstance(error, dict):
            manifest["error"] = {
                "message": str(error.get("message", "unknown")),
                "phase": str(error.get("phase", "unknown")),
                "timestamp": str(error.get("timestamp", _iso())),
            }
        else:
            manifest["error"] = {
                "message": str(error or "unknown"),
                "phase": "unknown",
                "timestamp": _iso(),
            }
    else:
        manifest["error"] = None

    _json_dump(paths["manifest_path"], manifest)
    if final_status in {"completed", "failed", "archived"}:
        append_manifest_index(paths, manifest)

    sync_observation_artifacts(paths)
    update_observation_readme(paths, manifest)
    return manifest


def _manifest_phase_progress(manifest: Dict[str, Any]) -> Tuple[int, int]:
    phases = manifest.get("phases") if isinstance(manifest.get("phases"), dict) else {}
    total = len(PHASE_DIRS)
    completed = 0
    for phase_dir in PHASE_DIRS:
        status = "pending"
        phase_payload = phases.get(phase_dir)
        if isinstance(phase_payload, dict):
            status = str(phase_payload.get("status", "pending"))
        if status in {"completed", "skipped"}:
            completed += 1
    return completed, total


def update_observation_readme(paths: Dict[str, Any], manifest: Dict[str, Any] | None = None) -> Path:
    if manifest is None:
        manifest = load_manifest(paths)

    observer_root = Path(paths["observation_run_root"])
    observer_root.mkdir(parents=True, exist_ok=True)

    completed, total = _manifest_phase_progress(manifest)
    status = manifest.get("status", "created")
    created_at = manifest.get("created_at", "")
    updated_at = manifest.get("updated_at", "")

    pending_phase_names: List[str] = []
    phases = manifest.get("phases") if isinstance(manifest.get("phases"), dict) else {}
    for phase_dir in PHASE_DIRS:
        phase_payload = phases.get(phase_dir)
        phase_status = "pending"
        if isinstance(phase_payload, dict):
            phase_status = str(phase_payload.get("status", "pending"))
        if phase_status in {"pending", "active"}:
            pending_phase_names.append(phase_dir)

    if pending_phase_names:
        next_actions = [f"- [ ] {name} phase progress" for name in pending_phase_names[:2]]
    else:
        next_actions = ["- [ ] no pending actions"]

    ticket_ids: List[str] = []
    tickets_dir = Path(paths["task_context_dir"]) / "tickets"
    if tickets_dir.exists():
        for ticket in sorted(tickets_dir.glob("TKT-*.md"))[:20]:
            ticket_ids.append(ticket.stem.split("-", 2)[0] + "-" + ticket.stem.split("-", 2)[1])
    ticket_text = ", ".join(ticket_ids) if ticket_ids else "(none)"

    summary = "Run initialized"
    if status == "active":
        summary = "Run is in progress across runtime phases."
    elif status == "completed":
        summary = "Run completed successfully."
    elif status == "failed":
        summary = "Run failed. Check 90_meta and governance outputs."
    elif status == "archived":
        summary = "Run archived for read-only retention."

    readme_text = (
        f"# {manifest.get('run_id', paths['run_id'])}\n\n"
        "## Status\n"
        f"- **상태**: {status}\n"
        f"- **시작**: {created_at}\n"
        f"- **갱신**: {updated_at}\n"
        f"- **진행률**: {completed}/{total} phases\n\n"
        "## 요약\n"
        f"{summary}\n\n"
        "## 다음 액션\n"
        + "\n".join(next_actions)
        + "\n\n"
        "## 참조\n"
        f"- 실행 컨텍스트: `{str(Path(paths['run_root']).resolve())}/`\n"
        f"- 관련 티켓: {ticket_text}\n"
    )

    readme_path = Path(paths["observation_readme_path"])
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(readme_text, encoding="utf-8")
    return readme_path


def _phase_int_to_name(value: Any) -> str | None:
    try:
        as_int = int(value)
    except Exception:
        return None
    key = f"{as_int:02d}"
    return PHASE_TO_DIR.get(key)


def _sync_peer_is_healthy(paths: Dict[str, Any]) -> bool:
    workspace_root = Path(paths["workspace_root"]).resolve()
    observation_root = Path(paths["observation_root"]).resolve()
    ws_anchor_path = workspace_root / ".mso-context" / ".anchor.json"
    obs_anchor_path = observation_root / ".anchor.json"

    if not ws_anchor_path.exists() or not obs_anchor_path.exists():
        return False

    ws_anchor = _json_load(ws_anchor_path)
    obs_anchor = _json_load(obs_anchor_path)
    if not ws_anchor or not obs_anchor:
        return False

    ws_peer = ws_anchor.get("peers", {}).get("observation", {})
    obs_peer = obs_anchor.get("peers", {}).get("workspace", {})
    ws_expected_obs_id = str(ws_peer.get("workspace_id", "")).strip()
    obs_expected_ws_id = str(obs_peer.get("workspace_id", "")).strip()
    actual_obs_id = str(obs_anchor.get("workspace_id", "")).strip()
    actual_ws_id = str(ws_anchor.get("workspace_id", "")).strip()

    if not ws_expected_obs_id or not obs_expected_ws_id or not actual_obs_id or not actual_ws_id:
        return False
    if ws_expected_obs_id != actual_obs_id or obs_expected_ws_id != actual_ws_id:
        return False
    return True


def sync_observation_artifacts(paths: Dict[str, Any]) -> None:
    policy = _load_policy(paths["settings"])
    observation_policy = policy.get("observation_policy") if isinstance(policy.get("observation_policy"), dict) else {}
    auto_sync = bool(observation_policy.get("auto_sync", True))
    if not auto_sync:
        return

    sync_phases = observation_policy.get("sync_phases", [10, 20, 30, 60])
    if not isinstance(sync_phases, list):
        sync_phases = [10, 20, 30, 60]

    if not _sync_peer_is_healthy(paths):
        return

    target_root = Path(paths["observation_artifacts_dir"]).resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    for raw_phase in sync_phases:
        phase_name = _phase_int_to_name(raw_phase)
        if phase_name is None:
            continue
        src = Path(paths["phases"][phase_name]).resolve()
        if not src.exists():
            continue
        dest = target_root / phase_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)


def _load_anchor(path: Path, anchor_type: str, canonical_path: Path) -> Dict[str, Any]:
    if path.exists():
        loaded = _json_load(path)
        if loaded:
            loaded.setdefault("type", anchor_type)
            loaded.setdefault("workspace_id", f"{'ws' if anchor_type == 'mso-workspace' else 'obs'}-{uuid.uuid4()}")
            loaded.setdefault("created_at", _iso())
            loaded.setdefault("canonical_path", str(canonical_path.resolve()))
            loaded.setdefault("peers", {})
            return loaded
    return _anchor_template(anchor_type, canonical_path)


def _peer_anchor_path(peer_type: str, peer_root: Path) -> Path:
    if peer_type == "mso-observation":
        return peer_root / ".anchor.json"
    return peer_root / ".mso-context" / ".anchor.json"


def ensure_anchors_and_detect_relocation(paths_or_settings: Dict[str, Any]) -> Dict[str, Any]:
    paths = (
        paths_or_settings
        if "settings" in paths_or_settings and "workspace_root" in paths_or_settings
        else ensure_workspace_scaffold(paths_or_settings)
    )
    settings = paths["settings"]

    workspace_root = Path(paths["workspace_root"]).resolve()
    observation_root = Path(paths["observation_root"]).resolve()

    context_root = workspace_root / ".mso-context"
    workspace_anchor_path = context_root / ".anchor.json"
    observation_anchor_path = observation_root / ".anchor.json"

    workspace_anchor = _load_anchor(workspace_anchor_path, "mso-workspace", workspace_root)
    observation_anchor = _load_anchor(observation_anchor_path, "mso-observation", observation_root)

    events: List[Dict[str, Any]] = []

    if Path(str(workspace_anchor.get("canonical_path", ""))).resolve() != workspace_root:
        workspace_anchor["canonical_path"] = str(workspace_root)
        events.append({"event": "SELF_RELOCATED", "workspace": "workspace", "path": str(workspace_root)})

    if Path(str(observation_anchor.get("canonical_path", ""))).resolve() != observation_root:
        observation_anchor["canonical_path"] = str(observation_root)
        events.append({"event": "SELF_RELOCATED", "workspace": "observation", "path": str(observation_root)})

    workspace_peers = workspace_anchor.setdefault("peers", {})
    observation_peers = observation_anchor.setdefault("peers", {})

    workspace_peers.setdefault("observation", {})
    observation_peers.setdefault("workspace", {})

    workspace_peers["observation"].setdefault("workspace_id", observation_anchor.get("workspace_id"))
    workspace_peers["observation"].setdefault("last_known_path", str(observation_root))
    workspace_peers["observation"].setdefault("last_verified_at", _iso())

    observation_peers["workspace"].setdefault("workspace_id", workspace_anchor.get("workspace_id"))
    observation_peers["workspace"].setdefault("last_known_path", str(workspace_root))
    observation_peers["workspace"].setdefault("last_verified_at", _iso())

    policy = _load_policy(settings).get("relocation_policy", {})
    repaired = False
    blocked_by_policy = False

    # Verify workspace -> observation peer
    obs_peer = workspace_peers["observation"]
    obs_peer_path = Path(str(obs_peer.get("last_known_path", ""))).expanduser()
    obs_expected_id = str(obs_peer.get("workspace_id", "")) if obs_peer.get("workspace_id") else None

    obs_ok = False
    obs_replaced = False
    if obs_peer_path.exists() and (_peer_anchor_path("mso-observation", obs_peer_path)).exists():
        peer_anchor = _json_load(_peer_anchor_path("mso-observation", obs_peer_path))
        if obs_expected_id and str(peer_anchor.get("workspace_id", "")) != obs_expected_id:
            obs_replaced = True
            events.append({
                "event": "PEER_REPLACED",
                "workspace": "workspace",
                "peer": "observation",
                "expected_workspace_id": obs_expected_id,
                "found_workspace_id": str(peer_anchor.get("workspace_id", "")),
                "path": str(obs_peer_path.resolve()),
                "sync_suspended": True,
            })
        else:
            obs_ok = True
            obs_peer["last_verified_at"] = _iso()

    if not obs_ok and not obs_replaced:
        events.append({
            "event": "PEER_MISSING",
            "workspace": "workspace",
            "peer": "observation",
            "last_known_path": str(obs_peer_path),
        })
        recovered = _search_peer_root(
            target_type="mso-observation",
            expected_workspace_id=obs_expected_id,
            settings=settings,
            policy=policy if isinstance(policy, dict) else {},
            current_workspace_root=workspace_root,
        )
        if recovered is not None:
            repaired = True
            obs_peer["last_known_path"] = str(recovered.resolve())
            obs_peer["last_verified_at"] = _iso()
            observation_root = recovered.resolve()
            paths["observation_root"] = observation_root
            events.append({
                "event": "PEER_MISSING",
                "workspace": "workspace",
                "peer": "observation",
                "recovered": True,
                "path": str(observation_root),
            })
        else:
            appended = _append_peer_missing_event(
                events,
                {
                    "event": "PEER_MISSING",
                    "workspace": "workspace",
                    "peer": "observation",
                    "recovered": False,
                },
                policy,
            )
            blocked_by_policy = blocked_by_policy or appended["blocked"]

    # Verify observation -> workspace peer
    ws_peer = observation_peers["workspace"]
    ws_peer_path = Path(str(ws_peer.get("last_known_path", ""))).expanduser()
    ws_expected_id = str(ws_peer.get("workspace_id", "")) if ws_peer.get("workspace_id") else None

    ws_ok = False
    ws_replaced = False
    if ws_peer_path.exists() and (_peer_anchor_path("mso-workspace", ws_peer_path)).exists():
        peer_anchor = _json_load(_peer_anchor_path("mso-workspace", ws_peer_path))
        if ws_expected_id and str(peer_anchor.get("workspace_id", "")) != ws_expected_id:
            ws_replaced = True
            events.append({
                "event": "PEER_REPLACED",
                "workspace": "observation",
                "peer": "workspace",
                "expected_workspace_id": ws_expected_id,
                "found_workspace_id": str(peer_anchor.get("workspace_id", "")),
                "path": str(ws_peer_path.resolve()),
                "sync_suspended": True,
            })
        else:
            ws_ok = True
            ws_peer["last_verified_at"] = _iso()

    if not ws_ok and not ws_replaced:
        events.append({
            "event": "PEER_MISSING",
            "workspace": "observation",
            "peer": "workspace",
            "last_known_path": str(ws_peer_path),
        })
        recovered = _search_peer_root(
            target_type="mso-workspace",
            expected_workspace_id=ws_expected_id,
            settings=settings,
            policy=policy if isinstance(policy, dict) else {},
            current_workspace_root=observation_root,
        )
        if recovered is not None:
            repaired = True
            ws_peer["last_known_path"] = str(recovered.resolve())
            ws_peer["last_verified_at"] = _iso()
            workspace_root = recovered.resolve()
            paths["workspace_root"] = workspace_root
            events.append({
                "event": "PEER_MISSING",
                "workspace": "observation",
                "peer": "workspace",
                "recovered": True,
                "path": str(workspace_root),
            })
        else:
            appended = _append_peer_missing_event(
                events,
                {
                    "event": "PEER_MISSING",
                    "workspace": "observation",
                    "peer": "workspace",
                    "recovered": False,
                },
                policy,
            )
            blocked_by_policy = blocked_by_policy or appended["blocked"]

    # Cross-link IDs and latest known paths
    workspace_peers["observation"]["workspace_id"] = observation_anchor.get("workspace_id")
    workspace_peers["observation"]["last_known_path"] = str(observation_root)

    observation_peers["workspace"]["workspace_id"] = workspace_anchor.get("workspace_id")
    observation_peers["workspace"]["last_known_path"] = str(workspace_root)

    _json_dump(workspace_anchor_path, workspace_anchor)
    _json_dump(observation_anchor_path, observation_anchor)

    if repaired:
        repair_peer_and_patch_observer_links(
            settings,
            workspace_root=workspace_root,
            observation_root=observation_root,
            observer_id=paths.get("observer_id") or settings.get("observer_id") or "unknown",
        )

    return {"events": events, "repaired": repaired, "blocked_by_policy": blocked_by_policy}


def repair_peer_and_patch_observer_links(
    base_hint_or_settings: Path | str | Dict[str, Any] | None = None,
    workspace_root: Path | str | None = None,
    observation_root: Path | str | None = None,
    observer_id: str | None = None,
) -> Dict[str, Any]:
    settings = (
        resolve_runtime_settings(base_hint_or_settings)
        if not isinstance(base_hint_or_settings, dict)
        else dict(base_hint_or_settings)
    )

    ws_root = _to_abs(workspace_root, settings["project_root"]) if workspace_root else Path(settings["workspace_root"]).resolve()
    obs_root = _to_abs(observation_root, settings["project_root"]) if observation_root else Path(settings["observation_root"]).resolve()
    resolved_observer_id = (observer_id or settings.get("observer_id") or os.environ.get("USER") or "unknown").strip() or "unknown"

    context_root = ws_root / ".mso-context"
    active_root = context_root / "active"

    patched = 0
    for run_dir in sorted(active_root.glob("*")):
        manifest_path = run_dir / "manifest.json"
        manifest = _json_load(manifest_path)
        if not manifest:
            continue
        run_id = str(manifest.get("run_id") or run_dir.name)
        links = manifest.get("observer_links") if isinstance(manifest.get("observer_links"), list) else []

        effective_observer = resolved_observer_id
        if links:
            effective_observer = _extract_observer_id(str(links[0]), resolved_observer_id)

        next_link = str((obs_root / effective_observer / run_id).resolve())
        if links != [next_link]:
            manifest["observer_links"] = [next_link]
            manifest["updated_at"] = _iso()
            _json_dump(manifest_path, manifest)
            patched += 1

    ws_anchor_path = context_root / ".anchor.json"
    obs_anchor_path = obs_root / ".anchor.json"
    ws_anchor = _json_load(ws_anchor_path)
    obs_anchor = _json_load(obs_anchor_path)

    if ws_anchor:
        ws_anchor.setdefault("peers", {}).setdefault("observation", {})
        ws_anchor["peers"]["observation"]["last_known_path"] = str(obs_root)
        ws_anchor["peers"]["observation"]["last_verified_at"] = _iso()
        _json_dump(ws_anchor_path, ws_anchor)

    if obs_anchor:
        obs_anchor.setdefault("peers", {}).setdefault("workspace", {})
        obs_anchor["peers"]["workspace"]["last_known_path"] = str(ws_root)
        obs_anchor["peers"]["workspace"]["last_verified_at"] = _iso()
        _json_dump(obs_anchor_path, obs_anchor)

    return {
        "patched_manifests": patched,
        "workspace_root": str(ws_root),
        "observation_root": str(obs_root),
    }


__all__ = [
    "PHASE_DIRS",
    "PHASE_TO_DIR",
    "SKILL_KEY_ENUM",
    "append_manifest_index",
    "ensure_anchors_and_detect_relocation",
    "ensure_policy_yaml",
    "ensure_run_scaffold_and_manifest",
    "ensure_workspace_scaffold",
    "finalize_manifest",
    "generate_run_id",
    "load_manifest",
    "normalize_skill_key",
    "repair_peer_and_patch_observer_links",
    "resolve_runtime_paths",
    "resolve_runtime_settings",
    "sanitize_case_slug",
    "sync_observation_artifacts",
    "update_manifest_phase",
    "update_observation_readme",
]
