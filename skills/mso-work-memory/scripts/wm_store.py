#!/usr/bin/env python3
"""wm_store.py — work-memory 큐레이션 기록의 N-Triples 저장소 (v0.16.0, stdlib only).

정본은 `<work-memory>/<dir>/<type>.nt` 이다(track-record / insight-record / release-record). 한 줄에 triple 하나(N-Triples 는
Turtle 의 부분집합이라 곧 TTL 이다). 쓰기·편집은 wm_node.py 만 한다 — 손으로 고치지 않는다.
auditlog/worklog(런타임 로그)는 JSONL 로 남는다.

이 모듈이 **기록 dict ↔ triple 변환 규칙의 유일한 정의**다. wm_to_ttl.py 는 여기서 나온 triple 을 읽고 투영 단계에서만
붙는 것(주체·통제 어휘·모듈 individual, 파생 validity)만 더한다.

stdlib 만 쓴다 — 프로젝트에 복사되는 훅(wm_context.py 등)이 MSO 의존성 없이 import 할 수 있어야 하기 때문이다.
타입별 metadata 명세는 YAML 을 못 읽으므로 `references/metadata-spec.json`(wm_gen_vocab.py 가 생성)을 읽는다.

손실 없는 왕복: 기록 → triple → 기록 이 같아야 한다(정규화 제외).
  - 명세에 있고 값이 맞는 metadata 는 타입 있는 프로퍼티로 저장하고, 통제 어휘 밖 값·명세 밖 키·알 수 없는 relation 타입·
    알 수 없는 최상위 키는 **그 항목들만** `wm:unmapped` JSON 리터럴 하나에 원문 그대로 보존한다(중복 저장 없음).
  - 정규화: `multiple` 키는 항상 리스트로, 통제 어휘의 옛 별칭(project→repository)은 정본 값으로 되돌아온다.
    options 항목의 n 이 없으면 순번이 채워진다. source_path 는 저장하지 않고 읽을 때 계산한다.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote

WM = "https://mso.dev/ontology/work-memory#"
ID_NS = "https://mso.dev/id/"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
XSD = "http://www.w3.org/2001/XMLSchema#"
EXTERNAL_PREFIXES = {"skos": "http://www.w3.org/2004/02/skos/core#"}

SKILL_DIR = Path(__file__).resolve().parents[1]
CURATED_DIRS = ("track-record", "insight-record", "release-record")
RUNTIME_TYPES = ("auditlog", "worklog")

TYPE_CLASS = {
    "issue-note": "IssueNote", "agent-decision": "AgentDecision", "user-decision": "UserDecision",
    "alternatives-record": "AlternativesRecord", "trouble-shooting": "TroubleShooting", "release-note": "ReleaseNote",
    "episode": "Episode", "pattern": "Pattern", "principle": "Principle", "auditlog": "AuditLog", "worklog": "WorkLog",
}
RELATION_PREDICATE = {
    "raised": "raised", "followed-by": "followedBy", "resolved-by": "resolvedBy", "caused-by": "causedBy",
    "released-in": "releasedIn", "verified-in": "verifiedIn", "invalidated-by": "invalidatedBy", "rolls-back": "rollsBack",
    "analyzed-in": "analyzedIn", "shows-pattern": "showsPattern", "generalized-in": "generalizedIn",
    "crystallized-in": "crystallizedIn", "references": "references", "supersedes": "supersedes", "refines": "refines",
    "depends-on": "dependsOn",
}
_REL_BY_PRED = {WM + v: k for k, v in RELATION_PREDICATE.items()}
# entry id 만 인정한다: 알려진 접두어 + (십진 4자리 이상 | 밀리초 hex 12자리), 런타임 로그의 시각형.
# `PR-123`(GitHub PR)·`ADR-7`·`GH-42` 같은 외부 참조는 entry id 가 아니다(원문은 어느 쪽이든 되돌아온다).
# 알려진 한계: `PR-1234` 처럼 4자리 이상 숫자인 외부 참조는 entry id 로 보인다.
_ENTRY_ID_RE = re.compile(
    r"^(?:(?:IN|AD|UD|AR|TS|RN|EP|PT|PR)-(?:\d{4,}|[0-9a-f]{12})"
    r"|AU-\d{8}-\d{6}(?:-[0-9a-f]+)?"
    r"|WL-(?:\d{8}-\d{6}|\d{4}-\d{2}-\d{2}(?:-\d{6})?))$")   # WL-20260601-133456(실제 기록) · WL-2026-06-01
_CONFLICT_COPY_RE = re.compile(r"\s\d+$")   # iCloud 충돌 복제본: "user-decision 2.nt"
_DATETIME_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)?$")


# ── 명세 (JSON) ──────────────────────────────────────────────────────────────

_spec_cache: dict[str, dict[str, Any]] = {}


def load_spec(path: Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else _find_spec_json()
    key = str(target)
    if key not in _spec_cache:
        _spec_cache[key] = json.loads(target.read_text(encoding="utf-8"))
    return _spec_cache[key]


def _find_spec_json() -> Path:
    """스킬 레이아웃(../references/)과 copy-form(스크립트 옆) 둘 다 찾는다."""
    here = Path(__file__).resolve().parent
    for cand in (here / "metadata-spec.json", SKILL_DIR / "references" / "metadata-spec.json"):
        if cand.is_file():
            return cand
    raise FileNotFoundError("metadata-spec.json 을 찾을 수 없음 (wm_gen_vocab.py 로 생성하고 스크립트와 함께 배포해야 한다)")


def type_metadata(spec: dict[str, Any], entry_type: str) -> dict[str, dict[str, Any]]:
    t = (spec.get("types") or {}).get(entry_type)
    if t is None:
        return {}
    merged = dict(spec.get("common") or {})
    merged.update(t.get("metadata") or {})
    return merged


def vocab_values(spec: dict[str, Any], vocab: str) -> dict[str, str]:
    """{JSONL 값(별칭 포함): individual 로컬 이름}"""
    v = (spec.get("vocabularies") or {}).get(vocab) or {}
    out: dict[str, str] = {}
    for item in v.get("values") or []:
        out[item["value"]] = item["id"]
        for alias in item.get("aliases") or []:
            out.setdefault(alias, item["id"])
    return out


def _vocab_canonical(spec: dict[str, Any], vocab: str) -> dict[str, str]:
    """{individual 로컬 이름: 정본 JSONL 값}"""
    v = (spec.get("vocabularies") or {}).get(vocab) or {}
    return {item["id"]: item["value"] for item in v.get("values") or []}


# ── IRI ──────────────────────────────────────────────────────────────────────

def _enc(value: Any) -> str:
    """IRI 구성요소 인코딩 — 되돌릴 수 있다(`a b` 와 `a_b` 가 섞이지 않는다)."""
    return quote(str(value), safe="")


def entry_iri(entry_id: str) -> str:
    return f"{ID_NS}memory/{_enc(entry_id)}"


def agent_iri(agent_id: str) -> str:
    return f"{ID_NS}agent/{_enc(agent_id) or 'unknown'}"


def module_iri(module_id: str) -> str:
    return f"{ID_NS}module/{_enc(module_id) or 'unknown'}"


def external_iri(value: str) -> str:
    return f"{ID_NS}external/{_enc(value) or 'external'}"


def vocab_iri(vocab: str, local_id: str) -> str:
    return f"{ID_NS}vocab/{vocab}/{local_id}"


def _tail(iri: str, prefix: str) -> str | None:
    return unquote(iri[len(prefix):]) if iri.startswith(prefix) else None


# ── 항(term) 과 N-Triples 직렬화 ─────────────────────────────────────────────
# IRI 항 = ("i", iri), 리터럴 항 = ("l", lexical, datatype_iri | None)

def I(iri: str) -> tuple:
    return ("i", iri)


def L(value: str, datatype: str | None = None) -> tuple:
    return ("l", value, datatype)


_ESC = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}


def _esc_literal(text: str) -> str:
    out = []
    for ch in text:
        if ch in _ESC:
            out.append(_ESC[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append("\\u%04X" % ord(ch))
        elif 0xD800 <= ord(ch) <= 0xDFFF:
            out.append("\ufffd")            # 짝 없는 surrogate 는 N-Triples 에 쓸 수 없다
        else:
            out.append(ch)
    return "".join(out)


def serialize_triple(s: str, p: str, o: tuple) -> str:
    if o[0] == "i":
        obj = f"<{o[1]}>"
    else:
        obj = f'"{_esc_literal(o[1])}"' + (f"^^<{o[2]}>" if o[2] else "")
    return f"<{s}> <{p}> {obj} ."


_LINE_RE = re.compile(
    r'^<([^<>"\s]*)>\s+<([^<>"\s]*)>\s+(?:<([^<>"\s]*)>|"((?:[^"\\]|\\.)*)"(?:\^\^<([^<>"\s]*)>|@([A-Za-z0-9-]+))?)\s*\.\s*$')
_UNESC_RE = re.compile(r"\\(?:u([0-9A-Fa-f]{4})|U([0-9A-Fa-f]{8})|(.))", re.S)
_UNESC = {"t": "\t", "b": "\b", "n": "\n", "r": "\r", "f": "\f", '"': '"', "'": "'", "\\": "\\"}


def _unesc_literal(text: str) -> str:
    def repl(m):
        if m.group(1):
            return chr(int(m.group(1), 16))
        if m.group(2):
            return chr(int(m.group(2), 16))
        return _UNESC.get(m.group(3), m.group(3))
    return _UNESC_RE.sub(repl, text) if "\\" in text else text


def parse_nt_line(line: str) -> tuple[str, str, tuple] | None:
    """한 줄을 (s, p, o) 로. 빈 줄·주석은 None. 문법이 틀리면 ValueError."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    m = _LINE_RE.match(stripped)
    if not m:
        raise ValueError(f"N-Triples 문법 오류: {stripped[:80]!r}")
    s, p, o_iri, o_lit, dtype, _lang = m.groups()
    if o_iri is not None:
        return s, p, I(o_iri)
    return s, p, L(_unesc_literal(o_lit), dtype)


def read_nt_file(path: Path) -> tuple[list[tuple[str, str, tuple]], list[tuple[int, str]]]:
    """(triples, problems). problems = [(줄 번호, 사유)] — 문법이 틀린 줄은 건너뛰고 보고한다."""
    triples: list[tuple[str, str, tuple]] = []
    problems: list[tuple[int, str]] = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        try:
            parsed = parse_nt_line(line)
        except ValueError as exc:
            problems.append((number, str(exc)))
            continue
        if parsed:
            triples.append(parsed)
    return triples, problems


# ── 기록 → triple ────────────────────────────────────────────────────────────

def _dt_lexical_ok(value: Any) -> bool:
    return isinstance(value, str) and bool(_DATETIME_RE.match(value))


def _typed_literal(dtype: str, value: Any) -> tuple | None:
    """명세 datatype 으로 리터럴을 만든다. 형식이 안 맞으면 None(unmapped 로 보존)."""
    if dtype == "string":
        return L(value) if isinstance(value, str) and value != "" else None
    if dtype == "boolean":
        return L("true" if value else "false", XSD + "boolean") if isinstance(value, bool) else None
    if dtype == "integer":
        return L(str(value), XSD + "integer") if isinstance(value, int) and not isinstance(value, bool) else None
    if dtype == "dateTime":
        return L(value, XSD + "dateTime") if _dt_lexical_ok(value) else None
    return None


def _structure_iri(entry_node: str, struct: dict[str, Any], ident: Any) -> str:
    return f"{entry_node}/{struct['class'].lower()}/{_enc(ident)}"


def _is_entry_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ENTRY_ID_RE.match(value))


def entry_to_triples(entry: dict[str, Any], spec: dict[str, Any] | None = None) -> list[tuple[str, str, tuple]]:
    """기록 dict 를 triple 목록으로. 명세로 표현할 수 없는 항목은 wm:unmapped(JSON 리터럴) 하나에 원문 보존."""
    spec = spec or load_spec()
    eid = str(entry["id"])
    etype = entry.get("type")
    subject = entry_iri(eid)
    out: list[tuple[str, str, tuple]] = []
    unmapped: dict[str, Any] = {}

    out.append((subject, RDF_TYPE, I(WM + "Entry")))
    if etype in TYPE_CLASS:
        out.append((subject, RDF_TYPE, I(WM + TYPE_CLASS[etype])))
    out.append((subject, WM + "entryId", L(eid)))
    if etype:
        out.append((subject, WM + "typeName", L(str(etype))))

    for key, fallback, pred in (("description", "title", "description"), ("content", "text", "content"),
                                ("created_at", None, "createdAt")):
        value = entry.get(key)
        if value in (None, "") and fallback:
            value = entry.get(fallback)
        if value not in (None, ""):
            out.append((subject, WM + pred, L(str(value))))

    for tag in entry.get("tags") or []:
        out.append((subject, WM + "tag", L(str(tag))))
    if entry.get("author"):
        out.append((subject, WM + "author", I(agent_iri(str(entry["author"])))))
    nodes = entry.get("node")
    if isinstance(nodes, list):
        for node_id in nodes:
            if isinstance(node_id, str) and node_id:
                out.append((subject, WM + "relatedNodeId", L(node_id)))

    external_seen: set[str] = set()
    bad_relations: list[Any] = []
    for rel in entry.get("relations") or []:
        rtype = rel.get("type") if isinstance(rel, dict) else None
        target = rel.get("target") if isinstance(rel, dict) else None
        if rtype not in RELATION_PREDICATE or not target or set(rel) - {"type", "target"}:
            bad_relations.append(rel)
            continue
        if _is_entry_id(target):
            obj = I(entry_iri(str(target)))
        else:
            ext = external_iri(str(target))
            obj = I(ext)
            if ext not in external_seen:
                external_seen.add(ext)
                out.append((ext, RDF_TYPE, I(WM + "ExternalReference")))
                out.append((ext, WM + "externalValue", L(str(target))))
        out.append((subject, WM + RELATION_PREDICATE[rtype], obj))
    if bad_relations:
        unmapped["relations"] = bad_relations

    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    if entry.get("metadata") is not None and not isinstance(entry.get("metadata"), dict):
        unmapped["metadata_raw"] = entry.get("metadata")
    defs = type_metadata(spec, str(etype))
    unmapped_md: dict[str, Any] = {}
    for key, value in metadata.items():
        triples = _metadata_triples(subject, key, value, defs.get(key), metadata, spec)
        if triples is None:
            unmapped_md[key] = value
        else:
            out.extend(triples)
    if unmapped_md:
        unmapped["metadata"] = unmapped_md

    known = {"id", "type", "description", "content", "title", "text", "tags", "created_at", "source_path", "author",
             "node", "relations", "metadata"}
    extra = {k: v for k, v in entry.items() if k not in known}
    if extra:
        unmapped["extra"] = extra
    if unmapped:
        out.append((subject, WM + "unmapped", L(json.dumps(unmapped, ensure_ascii=False, sort_keys=True))))
    return out


def _metadata_triples(subject: str, key: str, value: Any, defn: dict[str, Any] | None, metadata: dict[str, Any],
                      spec: dict[str, Any]) -> list[tuple[str, str, tuple]] | None:
    """metadata 한 키의 triple. 명세로 표현할 수 없으면 None(→ unmapped)."""
    if defn is None:
        return None
    prop = defn["property"]
    pred = (EXTERNAL_PREFIXES[prop.split(":", 1)[0]] + prop.split(":", 1)[1]) if ":" in prop else WM + prop
    if defn.get("structured"):
        return _structured_triples(subject, pred, value, defn, spec)
    if defn.get("ref"):
        struct = spec["structures"][defn["range"]]
        if not _ref_target_exists(value, defn, metadata, spec):
            return None                   # 가리킬 노드가 없으면 원문 보존
        return [(subject, pred, I(_structure_iri(subject, struct, value)))]
    items = value if (defn.get("multiple") and isinstance(value, list)) else [value]
    if defn.get("multiple") and isinstance(value, list) and not value:
        return None                       # 빈 리스트는 triple 이 없어 되돌릴 수 없다 → 원문 보존
    out: list[tuple[str, str, tuple]] = []
    for item in items:
        if defn["kind"] == "datatype":
            lit = _typed_literal(defn.get("datatype"), item)
            if lit is None:
                return None
            out.append((subject, pred, lit))
            continue
        if not isinstance(item, str) or not item.strip():
            return None
        if "vocab" in defn:
            local = vocab_values(spec, defn["vocab"]).get(item)
            if local is None:
                return None               # 통제 어휘 밖 값(옛 기록의 자유 서술 등) — 원문 보존
            out.append((subject, pred, I(vocab_iri(defn["vocab"], local))))
        elif defn["range"] == "Agent":
            out.append((subject, pred, I(agent_iri(item))))
        elif defn["range"] == "Module":
            out.append((subject, pred, I(module_iri(item))))
        elif defn["range"] == "Entry":
            out.append((subject, pred, I(entry_iri(item))))
        else:
            return None
    return out


def _ref_target_exists(value: Any, defn: dict[str, Any], metadata: dict[str, Any], spec: dict[str, Any]) -> bool:
    """ref 값이 같은 기록의 구조화 속성에 실제로 있는 key 인가(없으면 가리킬 노드가 없다)."""
    struct = spec["structures"][defn["range"]]
    for k, d in _all_defs(spec).items():
        if d.get("structured") and d.get("range") == defn["range"] and k in metadata and isinstance(metadata[k], list):
            for position, item in enumerate(metadata[k], 1):
                if isinstance(item, dict) and item.get(struct["key"], position) == value:
                    return True
    return False


def _all_defs(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for t in (spec.get("types") or {}).values():
        merged.update(t.get("metadata") or {})
    return merged


def _structured_triples(subject: str, pred: str, value: Any, defn: dict[str, Any], spec: dict[str, Any]):
    struct = spec["structures"][defn["range"]]
    items = value if isinstance(value, list) else None
    if not items:
        return None
    out: list[tuple[str, str, tuple]] = []
    for position, item in enumerate(items, 1):
        if not isinstance(item, dict) or set(item) - set(struct["properties"]):
            return None                   # 모양이 어긋난 구조화 값은 통째로 원문 보존
        ident = item.get(struct["key"], position)
        node = _structure_iri(subject, struct, ident)
        out.append((node, RDF_TYPE, I(WM + struct["class"])))
        out.append((subject, pred, I(node)))
        for field, pdef in struct["properties"].items():
            raw = ident if field == struct["key"] else item.get(field)
            if raw in (None, ""):
                continue
            lit = _typed_literal(pdef["datatype"], raw)
            if lit is None:
                return None
            out.append((node, WM + pdef["property"], lit))
    return out


# ── triple → 기록 ────────────────────────────────────────────────────────────

def triples_to_entries(triples: Iterable[tuple[str, str, tuple]], spec: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """triple 에서 기록 dict 목록을 복원한다(subject 첫 등장 순서). 같은 subject 의 triple 은 위치와 무관하게 합친다."""
    spec = spec or load_spec()
    by_subject: dict[str, list[tuple[str, tuple]]] = {}
    for s, p, o in triples:
        by_subject.setdefault(s, []).append((p, o))
    external_values = {s: next((o[1] for p, o in props if p == WM + "externalValue"), None) for s, props in by_subject.items()}
    entries: list[dict[str, Any]] = []
    for s, props in by_subject.items():
        if not any(p == WM + "entryId" for p, _ in props):
            continue
        entries.append(_decode_entry(s, props, by_subject, external_values, spec))
    return entries


def _first(props: list[tuple[str, tuple]], pred: str) -> str | None:
    for p, o in props:
        if p == WM + pred:
            return o[1]
    return None


def _decode_entry(subject: str, props, by_subject, external_values, spec) -> dict[str, Any]:
    eid = _first(props, "entryId") or ""
    etype = _first(props, "typeName")
    entry: dict[str, Any] = {"id": eid, "type": etype}
    for key, pred in (("description", "description"), ("content", "content")):
        value = _first(props, pred)
        entry[key] = value if value is not None else ""
    entry["tags"] = [o[1] for p, o in props if p == WM + "tag"]
    created = _first(props, "createdAt")
    entry["created_at"] = created if created is not None else ""
    author = next((o[1] for p, o in props if p == WM + "author" and o[0] == "i"), None)
    if author:
        entry["author"] = _tail(author, f"{ID_NS}agent/") or author

    relations = []
    for p, o in props:
        rtype = _REL_BY_PRED.get(p)
        if rtype is None or o[0] != "i":
            continue
        ext = _tail(o[1], f"{ID_NS}external/")
        if ext is not None:
            target = external_values.get(o[1]) or ext
        else:
            target = _tail(o[1], f"{ID_NS}memory/") or o[1]
        relations.append({"type": rtype, "target": target})
    unmapped = json.loads(_first(props, "unmapped") or "{}")
    relations.extend(unmapped.get("relations") or [])
    entry["relations"] = relations

    metadata = _decode_metadata(subject, props, by_subject, str(etype), spec)
    metadata.update(unmapped.get("metadata") or {})
    if "metadata_raw" in unmapped:
        entry["metadata"] = unmapped["metadata_raw"]
    else:
        entry["metadata"] = metadata
    nodes = [o[1] for p, o in props if p == WM + "relatedNodeId"]
    if nodes:
        entry["node"] = nodes
    entry.update(unmapped.get("extra") or {})
    return entry


def _decode_metadata(subject: str, props, by_subject, etype: str, spec) -> dict[str, Any]:
    defs = type_metadata(spec, etype)
    by_pred: dict[str, tuple[str, dict[str, Any]]] = {}
    for key, defn in defs.items():
        prop = defn["property"]
        pred = (EXTERNAL_PREFIXES[prop.split(":", 1)[0]] + prop.split(":", 1)[1]) if ":" in prop else WM + prop
        by_pred[pred] = (key, defn)
    out: dict[str, Any] = {}
    for p, o in props:
        hit = by_pred.get(p)
        if hit is None:
            continue
        key, defn = hit
        if defn.get("structured"):
            node_props = by_subject.get(o[1], [])
            struct = spec["structures"][defn["range"]]
            item = {}
            for field, pdef in struct["properties"].items():
                raw = next((oo for pp, oo in node_props if pp == WM + pdef["property"]), None)
                if raw is not None:
                    item[field] = _decode_literal(pdef["datatype"], raw[1])
            out.setdefault(key, []).append(item)
            continue
        if defn.get("ref"):
            struct = spec["structures"][defn["range"]]
            node_props = by_subject.get(o[1], [])
            kp = struct["properties"][struct["key"]]
            raw = next((oo for pp, oo in node_props if pp == WM + kp["property"]), None)
            out[key] = _decode_literal(kp["datatype"], raw[1]) if raw else _tail(o[1], o[1].rsplit("/", 1)[0] + "/")
            continue
        value = _decode_term(defn, o, spec)
        if defn.get("multiple"):
            out.setdefault(key, []).append(value)
        else:
            out.setdefault(key, value)
    # 명세 순서대로 정렬해 안정적인 출력을 만든다
    return {k: out[k] for k in defs if k in out}


def _decode_literal(dtype: str, lexical: str) -> Any:
    if dtype == "integer":
        return int(lexical)
    if dtype == "boolean":
        return lexical in ("true", "1")
    return lexical


def _decode_term(defn: dict[str, Any], term: tuple, spec) -> Any:
    if defn["kind"] == "datatype":
        return _decode_literal(defn.get("datatype"), term[1])
    iri = term[1]
    if "vocab" in defn:
        local = iri.rsplit("/", 1)[-1]
        return _vocab_canonical(spec, defn["vocab"]).get(local, local)
    if defn["range"] == "Agent":
        return _tail(iri, f"{ID_NS}agent/") or iri
    if defn["range"] == "Module":
        return _tail(iri, f"{ID_NS}module/") or iri
    if defn["range"] == "Entry":
        return _tail(iri, f"{ID_NS}memory/") or iri
    return iri


# ── 파일 입출력 ──────────────────────────────────────────────────────────────

def entry_nt_path(root: Path, type_dir: str, entry_type: str) -> Path:
    return Path(root) / type_dir / f"{entry_type}.nt"


def block_lines(entry: dict[str, Any], spec: dict[str, Any] | None = None) -> list[str]:
    return [serialize_triple(s, p, o) for s, p, o in entry_to_triples(entry, spec)]


def _belongs(line_subject: str, subject: str) -> bool:
    return line_subject == subject or line_subject.startswith(subject + "/")


def _line_subject(line: str) -> str | None:
    m = re.match(r"^<([^<>\s]*)>", line)
    return m.group(1) if m else None


def append_entry(path: Path, entry: dict[str, Any], spec: dict[str, Any] | None = None) -> None:
    """기록을 파일 끝에 한 번의 write 로 추가한다(블록 전체가 한 번에 들어간다)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_external: set[str] = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if f"<{WM}externalValue>" in line:
                subj = _line_subject(line)
                if subj:
                    existing_external.add(subj)
    lines = []
    for s, p, o in entry_to_triples(entry, spec):
        if s in existing_external and s.startswith(ID_NS + "external/"):
            continue                       # 같은 외부 참조 노드는 파일에 한 번만
        lines.append(serialize_triple(s, p, o))
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def replace_entry(path: Path, entry: dict[str, Any], spec: dict[str, Any] | None = None) -> bool:
    """기존 기록의 줄들을 새 블록으로 같은 위치에 바꾼다(원자적: 임시 파일 → os.replace). 없으면 False."""
    path = Path(path)
    subject = entry_iri(str(entry["id"]))
    old_lines = path.read_text(encoding="utf-8").splitlines()
    new_block = block_lines(entry, spec)
    out: list[str] = []
    inserted = False
    for line in old_lines:
        subj = _line_subject(line)
        if subj is not None and _belongs(subj, subject):
            if not inserted:
                out.extend(new_block)
                inserted = True
            continue
        out.append(line)
    if not inserted:
        return False
    _atomic_write(path, "\n".join(out) + "\n")
    return True


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def nt_entry_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not Path(path).is_file():
        return ids
    marker = f"<{WM}entryId>"
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if marker in line:
            try:
                parsed = parse_nt_line(line)
            except ValueError:
                continue
            if parsed and parsed[1] == WM + "entryId":
                ids.add(parsed[2][1])
    return ids


def load_nt_entries(path: Path, spec: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[tuple[int, str]]]:
    triples, problems = read_nt_file(path)
    return triples_to_entries(triples, spec), problems


def duplicate_single_valued(path: Path, spec: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    """같은 subject 에 단일값 필드(description/content/createdAt/typeName)가 둘 이상인 경우 — 병합·충돌 복제본의 흔적."""
    triples, _ = read_nt_file(path)
    seen: dict[tuple[str, str], int] = {}
    for s, p, o in triples:
        if p in (WM + "description", WM + "content", WM + "createdAt", WM + "typeName", WM + "entryId"):
            seen[(s, p)] = seen.get((s, p), 0) + 1
    return [(unquote(s.rsplit("/", 1)[-1]), p[len(WM):]) for (s, p), n in seen.items() if n > 1]


def is_conflict_copy(path: Path) -> bool:
    """iCloud 충돌 복제본(`foo 2.nt`, `foo 3.jsonl`) 이름인가. 모든 읽기·쓰기 경로가 이 판정 하나를 공유한다."""
    return bool(_CONFLICT_COPY_RE.search(Path(path).stem))


def order_paths(paths: Iterable[Path]) -> list[Path]:
    """원본 파일을 충돌 복제본보다 앞에 둔다 — 첫 번째로 본 id 가 이기는 규칙(first-seen-wins)에서 원본이 이긴다.
    (공백이 `.` 보다 앞이라 단순 정렬하면 `user-decision 2.jsonl` 이 원본보다 먼저 온다.)"""
    return sorted(paths, key=lambda p: (is_conflict_copy(p), str(p)))


def iter_curated_entries(root: Path, spec: dict[str, Any] | None = None, skip_conflict_copies: bool = False):
    """큐레이션 디렉터리의 `.nt` 와 (이행 전) `.jsonl` 기록을 (entry, source_path, line_or_None, fmt) 로 낸다.
    id 는 첫 번째로 본 것이 이긴다(루트 간·파일 간 first-seen-wins) — 호출자가 중복을 보고한다."""
    root = Path(root)
    for dirname in CURATED_DIRS:
        base = root / dirname
        if not base.exists():
            continue
        for path in order_paths(base.rglob("*")):
            rel = path.relative_to(root)
            if not path.is_file() or any(part.startswith(".") for part in rel.parts[:-1]) or path.name.startswith("."):
                continue
            if skip_conflict_copies and is_conflict_copy(path):
                continue
            if path.suffix == ".nt":
                entries, _problems = load_nt_entries(path, spec)
                for entry in entries:
                    yield entry, path, None, "nt"
            elif path.suffix == ".jsonl":
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict):
                        yield obj, path, number, "jsonl"
