#!/usr/bin/env python3
"""wm_metadata.py — 타입별 metadata 명세(references/metadata-spec.yaml) 로더와 검사기 (v0.16.0).

wm_node.py(validate/new)와 wm_to_ttl.py(투영)와 wm_gen_vocab.py(TBox/SHACL 생성)가 공유한다.
의존성: PyYAML 만(rdflib 불필요).

강제 규칙 (명세의 enforce_from 기준):
  - 새 기록(created_at >= enforce_from): 필수 누락·값 집합 위반·형식 위반이 오류다.
  - 옛 기록: 같은 문제가 경고다(옛 기록을 깨뜨리지 않는다).
  - metadata.needs_review == true 인 기록은 새 기록이어도 경고로 낮춘다(`new --allow-incomplete`, 이행 스크립트가 붙인다).
  - 명세에 없는 metadata 키는 항상 경고다.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import yaml

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = SKILL_DIR / "references" / "metadata-spec.yaml"
RUNTIME_TYPES = ("auditlog", "worklog")  # 런타임 로그는 metadata 명세 대상이 아니다

_spec_cache: dict[str, dict[str, Any]] = {}


def load_spec(path: Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_SPEC
    key = str(target)
    if key not in _spec_cache:
        _spec_cache[key] = yaml.safe_load(target.read_text(encoding="utf-8"))
    return _spec_cache[key]


def type_metadata(spec: dict[str, Any], entry_type: str) -> dict[str, dict[str, Any]]:
    """공통 + 타입별 metadata 키 정의. 타입이 명세에 없으면 빈 dict."""
    t = (spec.get("types") or {}).get(entry_type)
    if t is None:
        return {}
    merged = dict(spec.get("common") or {})
    merged.update(t.get("metadata") or {})
    return merged


def vocab_values(spec: dict[str, Any], vocab: str) -> dict[str, str]:
    """{JSONL 값: individual 로컬 이름}"""
    v = (spec.get("vocabularies") or {}).get(vocab) or {}
    out: dict[str, str] = {}
    for item in v.get("values") or []:
        out[item["value"]] = item["id"]
        for alias in item.get("aliases") or []:  # 다른 도구/옛 기록이 쓰는 동의어(값은 정본 individual 로 모인다)
            out.setdefault(alias, item["id"])
    return out


def normalize_vocab(spec: dict[str, Any], vocab: str, raw: Any) -> str | None:
    """통제 어휘 값을 individual 로컬 이름으로. 정확히 맞지 않으면 앞 토큰으로 한 번 더 시도한다
    (옛 기록의 `medium (push 전)` 처럼 값 뒤에 설명이 붙은 경우). 끝내 못 맞추면 None."""
    values = vocab_values(spec, vocab)
    text = str(raw).strip()
    if text in values:
        return values[text]
    head = re.split(r"[\s(（:,;]", text, maxsplit=1)[0].lower()
    return values.get(head)


# ── 주체(Agent) 레지스트리 ──

def load_agents(workmem_root: Path | None, spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{agent id: {kind, onBehalfOf?, trigger?}}. <work-memory>/agents.yaml 이 있으면 내장 기본에 덮어쓴다."""
    agents = {a["id"]: dict(a) for a in (spec.get("agents") or {}).get("builtin") or []}
    if workmem_root:
        reg = Path(workmem_root) / "agents.yaml"
        if reg.is_file():
            try:
                data = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                data = {}
            for item in data.get("agents") or []:
                if isinstance(item, dict) and item.get("id"):
                    agents[str(item["id"])] = dict(item)
    return agents


def agent_info(agents: dict[str, dict[str, Any]], agent_id: str) -> dict[str, Any]:
    """등록되지 않은 id 는 소속 미상의 SoftwareAgent 로 본다."""
    return agents.get(agent_id) or {"id": agent_id, "kind": "softwareAgent"}


# ── 검사 ──

def _iso_prefix(value: str) -> str:
    return str(value or "")[:19]


def is_new_record(entry: dict[str, Any], spec: dict[str, Any]) -> bool:
    return _iso_prefix(entry.get("created_at") or "") >= _iso_prefix(spec.get("enforce_from") or "")


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _check_scalar(definition: dict[str, Any], value: Any, spec: dict[str, Any], agents: dict[str, Any]) -> str | None:
    """값 하나의 형식 위반 사유. 문제 없으면 None."""
    if definition["kind"] == "object":
        if not isinstance(value, str) or not value.strip():
            return "문자열이어야 함"
        if "vocab" in definition:
            if normalize_vocab(spec, definition["vocab"], value) is None:
                allowed = ", ".join(vocab_values(spec, definition["vocab"]))
                return f"허용 값이 아님: {value!r} (허용: {allowed})"
        return None
    dtype = definition.get("datatype")
    if dtype == "string":
        return None if isinstance(value, str) and value.strip() else "비어 있지 않은 문자열이어야 함"
    if dtype == "boolean":
        return None if isinstance(value, bool) else "true/false 여야 함"
    if dtype == "integer":
        return None if isinstance(value, int) and not isinstance(value, bool) else "정수여야 함"
    if dtype == "dateTime":
        return None if _is_iso_datetime(value) else "ISO 8601 시각이어야 함"
    if dtype == "json":
        return None if isinstance(value, (list, dict)) and value else "비어 있지 않은 리스트/객체여야 함"
    return None


def check_entry(entry: dict[str, Any], spec: dict[str, Any] | None = None,
                agents: dict[str, dict[str, Any]] | None = None) -> list[tuple[str, str]]:
    """entry 의 metadata 를 명세로 검사한다. [(level, message)] — level 은 'error' | 'warn'."""
    spec = spec or load_spec()
    agents = agents if agents is not None else load_agents(None, spec)
    etype = entry.get("type")
    if etype in RUNTIME_TYPES or etype not in (spec.get("types") or {}):
        return []
    defs = type_metadata(spec, etype)
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    strict = is_new_record(entry, spec) and metadata.get("needs_review") is not True
    level = "error" if strict else "warn"
    findings: list[tuple[str, str]] = []

    for key, definition in defs.items():
        if key not in metadata:
            if definition.get("required"):
                findings.append((level, f"metadata.{key} 필수 ({etype})"))
            continue
        value = metadata[key]
        if definition.get("structured"):
            findings.extend(_check_structured(key, definition, value, spec, level))
            continue
        if definition.get("ref"):
            findings.extend(_check_ref(key, definition, value, metadata, defs, spec, level))
            continue
        # multiple 은 "여러 값 허용"이다. 값 하나를 스칼라로 쓴 기록(옛 기록의 alternatives 문자열 등)도 한 항목으로 인정한다.
        values = value if (definition.get("multiple") and isinstance(value, list)) else [value]
        if definition.get("required") and not values:
            findings.append((level, f"metadata.{key} 는 최소 1개 필요 (빈 리스트)"))
            continue
        for item in values:
            problem = _check_scalar(definition, item, spec, agents)
            if problem:
                findings.append((level, f"metadata.{key}: {problem}"))
    for key in metadata:
        if key not in defs:
            findings.append(("warn", f"metadata.{key} 는 명세에 없는 키 ({etype})"))
    # scope 가 task/workflow(실행 위치에 묶인 층)인데 node 매핑이 없으면 훅이 이 기록을 주입하지 못한다 — 오류는 아니고 안내다.
    raw_scope = metadata.get("scope")
    scopes = raw_scope if isinstance(raw_scope, list) else ([raw_scope] if raw_scope else [])
    canonical = {vocab_values(spec, "scope").get(str(s)) for s in scopes}
    if canonical & {"task", "workflow"} and not entry.get("node"):
        findings.append(("warn", "scope 에 task/workflow 가 있는데 node 매핑이 없음 — 훅이 노드별로 주입하지 못한다 (new --node / map-node)"))
    return findings


# 외부 어휘 접두어 (spec 의 property 가 "접두어:이름" 일 때)
EXTERNAL_PREFIXES = {"skos": "http://www.w3.org/2004/02/skos/core#"}


def is_external(prop: str) -> bool:
    return ":" in prop


def _check_structured(key: str, definition: dict[str, Any], value: Any, spec: dict[str, Any], level: str):
    """구조화 속성(예: options). 값은 객체의 리스트이며 각 객체의 필수 키·형식·key 유일성을 본다."""
    struct = (spec.get("structures") or {})[definition["range"]]
    items = value if isinstance(value, list) else [value]
    out: list[tuple[str, str]] = []
    if definition.get("required") and not items:
        return [(level, f"metadata.{key} 는 최소 1개 필요 (빈 리스트)")]
    seen: set[Any] = set()
    for i, item in enumerate(items):
        where = f"metadata.{key}[{i}]"
        if not isinstance(item, dict):
            out.append((level, f"{where} 는 객체여야 함"))
            continue
        for k, sd in struct["properties"].items():
            if k not in item:
                if sd.get("required"):
                    out.append((level, f"{where}.{k} 필수 ({struct['class']})"))
                continue
            problem = _check_scalar({"kind": "datatype", "datatype": sd["datatype"]}, item[k], spec, {})
            if problem:
                out.append((level, f"{where}.{k}: {problem}"))
        for k in item:
            if k not in struct["properties"]:
                out.append(("warn", f"{where}.{k} 는 명세에 없는 키 ({struct['class']})"))
        ident = item.get(struct["key"])
        if ident is not None:
            if ident in seen:
                out.append((level, f"{where}.{struct['key']}={ident!r} 가 중복됨"))
            seen.add(ident)
    return out


def _check_ref(key: str, definition: dict[str, Any], value: Any, metadata: dict[str, Any],
               defs: dict[str, dict[str, Any]], spec: dict[str, Any], level: str):
    """ref 속성(예: recommended)은 같은 구조화 속성의 key 값을 가리켜야 한다."""
    sibling = next((k for k, d in defs.items() if d.get("structured") and d.get("range") == definition["range"]), None)
    if sibling is None or sibling not in metadata:
        return [(level, f"metadata.{key} 가 가리킬 metadata.{sibling or '?'} 가 없음")]
    ident = spec["structures"][definition["range"]]["key"]
    items = metadata[sibling] if isinstance(metadata[sibling], list) else []
    keys = {it.get(ident) if isinstance(it, dict) else None for it in items}
    if value not in keys:
        return [(level, f"metadata.{key}={value!r} 에 해당하는 {sibling} 항목이 없음 (있는 값: {sorted(k for k in keys if k is not None)})")]
    return []


def required_keys(spec: dict[str, Any], entry_type: str) -> list[str]:
    return [k for k, d in type_metadata(spec, entry_type).items() if d.get("required")]
