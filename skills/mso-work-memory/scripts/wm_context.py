#!/usr/bin/env python3
"""wm_context.py — 런타임 context-pack 검색 (lexical ranking, stdlib-only core).

ContextPack 스코어링/선택 로직의 정본(canonical home). (과거 mso-workflow-optimizer 의 compile_workflow.py 가
컴파일 타임에 재사용했으나 optimizer 는 v1.0.0 에서 컴파일을 그만뒀다)
(단일 정본). zvec 의존 없음 — 랭킹은 lexical 전용:
타입 우선순위 + 18×태그 교집합 + 토큰 매치 + 12 module 보너스.

  node   workflow node id 기준 검색. --ttl 로 ABox 에서 label/instruction/phase
         등을 selector 재료로 해석 (rdflib 필요). --ttl 없으면 node id 만
         tag+query seed 로 쓰는 저비용 경로 (rdflib 불필요).
  query  자유 질의 검색 (workflow 레일 밖 execution 단위용).
  show   entry 한 건의 description + content 전문 (요약 우선 주입의 '펼치기').
  standing  노드와 무관하게 항상 적용되는 교훈(기본: scope 가 repository/global 인 accepted principle)의 요약 목록.
            SessionStart 훅(standing-context-hook.py)이 세션 시작·압축·재개 때 한 번 주입한다.

v0.16.0 (schema v1.4.0) — 점진적 주입:
  - 기본 출력은 `id [type] description` 요약 목록이다. content 는 `show <id>` 또는 --full 로만 펼친다.
  - entry 의 `node` 필드(workflow node id 목록)가 related 매핑이다. --fallback none 이면
    매핑된 entry 만 고르고 없으면 침묵한다(훅 기본). 기본값 score 는 기존 CLI 동작을 유지한다.
  - superseded/invalidated entry 는 제외한다(validity 는 JSONL 에 저장하지 않고 relations 에서 도출, UD-0012).
  - top_k·예산(--max-chars)은 관계 확장 *후* 에 적용한다(확장 이웃이 상한을 우회하던 문제 수정).
  - --seen-file: 이미 주입한 id 를 건너뛰고 이번에 낸 id 를 기록한다(세션 내 중복 방지).
  - title/text 는 description/content 의 폴백으로만 읽는다.

스코핑 (mono/umbrella-repo):
  --filter-tag / --filter-module  하드 필터 — 스코어링·확장 이전에 적용되어
                                  스코프 밖 entry 가 재진입할 수 없다.
  --tags / --module               소프트 부스트 — selector tags 에 추가만 한다.
  --extra-root                    umbrella-repo 의 추가 work-memory 루트 병합
                                  (id 는 first-seen-wins, 메인 루트 우선).

core 는 stdlib only — copy-form 배포를 위해 wm_node.py 와 독립. rdflib 는
--ttl 경로에서만 lazy import. top-level 은 side-effect free (optimizer 가
exec_module 로 로드한다).
WORKMEM_DIR 환경변수(기본 ./agent-context/work-memory)를 루트로 읽는다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# v0.16.0: 큐레이션 기록은 N-Triples(.nt)다. wm_store.py(stdlib)가 스크립트 옆에 있을 때만 .nt 를 읽는다 —
# 없으면(복사되는 훅 배포 누락) .nt 는 건너뛰고 .jsonl 만 읽는다. 훅은 이 때문에 죽으면 안 된다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import wm_store
except Exception:  # noqa: BLE001
    wm_store = None

# ── 상수 (구 compile_workflow.py 에서 이관 — 여기가 정본) ──

TYPE_PRIORITIES: dict[str, int] = {
    "principle": 30,
    "pattern": 26,
    "user-decision": 24,
    "episode": 20,
    "trouble-shooting": 16,
    "issue-note": 14,
    "agent-decision": 12,
    "alternatives-record": 12,
}

DEFAULT_INCLUDE_TYPES: list[str] = [
    "principle",
    "pattern",
    "episode",
    "user-decision",
    "agent-decision",
    "alternatives-record",
    "issue-note",
    "trouble-shooting",
]

DEFAULT_TOP_K = 5
DEFAULT_RELATION_DEPTH = 1
DEFAULT_MAX_ENTRY_CHARS = 1200
DEFAULT_MAX_CHARS = 1200  # 요약 목록 총량 예산(글자). 훅은 MSO_WORKFLOW_CONTEXT_MAX_CHARS 로 덮는다.
DEFAULT_SEEN_TTL = 900.0  # 초. 이 시간이 지나면 이미 낸 id 도 다시 낸다(압축 등으로 사라졌을 수 있음)
INACTIVE_VALIDITY = ("superseded", "invalidated", "deprecated")  # 주입에서 제외하는 파생 상태


# ── 로딩 ──

def workmem_root() -> Path:
    return Path(os.environ.get("WORKMEM_DIR", "./agent-context/work-memory")).resolve()


def normalize_entry(obj: Any, source_path: Path | str) -> dict[str, Any] | None:
    """JSONL 1줄을 공통 dict 형태로 강제. id/type 없으면 None."""
    if not isinstance(obj, dict) or not obj.get("id") or not obj.get("type"):
        return None
    return {
        "id": str(obj.get("id")),
        "type": str(obj.get("type")),
        # v0.16.0: description/content 우선, 옛 title/text 는 폴백 (wm_node.FIELD_FALLBACK 과 같은 규칙)
        "description": str(obj.get("description") or obj.get("title") or ""),
        "content": str(obj.get("content") or obj.get("text") or ""),
        "node": [str(n) for n in (obj.get("node") or []) if n] if isinstance(obj.get("node"), list) else [],
        "tags": [str(t) for t in (obj.get("tags") or [])],
        "created_at": str(obj.get("created_at")) if obj.get("created_at") else None,
        "source_path": str(obj.get("source_path") or source_path),
        "relations": [
            {"type": str(rel.get("type")), "target": str(rel.get("target"))}
            for rel in (obj.get("relations") or [])
            if isinstance(rel, dict) and rel.get("type") and rel.get("target")
        ],
        "metadata": obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {},
    }


def _read_records(path: Path):
    """파일 하나의 기록 dict 들. `.nt`(큐레이션 정본)는 wm_store 로, `.jsonl`(런타임 로그·이행 전 기록)은 줄 단위로."""
    if path.suffix == ".nt":
        if wm_store is None:
            return
        try:
            yield from wm_store.load_nt_entries(path)[0]
        except Exception:  # noqa: BLE001 — 읽을 수 없는 파일 하나가 주입 전체를 막지 않는다
            return
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        yield obj


def load_entries(root: Path, extra_roots: tuple[Path, ...] = ()) -> list[dict[str, Any]]:
    """루트(들)의 모든 *.nt(큐레이션 정본)·*.jsonl(런타임 로그·이행 전 기록)을 entry dict 리스트로 로드.

    dot-dir(.zvec, .migration-archive 등)는 스킵. id 는 전체 루트를 가로질러
    first-seen-wins dedup — 메인 루트가 extra 루트보다 우선한다.
    """
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for base in (root, *extra_roots):
        if not base or not base.exists():
            continue
        # 원본을 iCloud 충돌 복제본("x 2.jsonl")보다 앞에 둔다 — 단순 정렬하면 복제본이 먼저 와서 first-seen-wins 에서 이긴다
        for path in sorted([*base.rglob("*.jsonl"), *base.rglob("*.nt")],
                           key=lambda p: (bool(re.search(r"\s\d+$", p.stem)), str(p))):
            rel = path.relative_to(base)
            if any(part.startswith(".") for part in rel.parts[:-1]):
                continue
            for obj in _read_records(path):
                entry = normalize_entry(obj, path)
                if entry and entry["id"] not in seen:
                    seen.add(entry["id"])
                    entries.append(entry)
    return entries


# ── 스코어링 코어 (구 compile_workflow.py 와 수식 동일 — 변경 시 컴파일 타임 parity 깨짐) ──

# ASCII 토큰은 3자 이상(the/and 류 잡음 배제), 한글은 2자 이상 — 한국어 내용어가
# 2음절인 경우가 흔하기 때문(결정·검색·회수). 한글이 빠져 있으면 한국어 질의는
# 토큰 기여가 0 이 되어 랭킹이 타입 우선순위로 퇴화한다(IN-0002).
# 남는 한계: 교착어라 조사가 붙으면 다른 토큰이 된다("결정" ≠ "결정을").
# 형태소 분석 없이 정확히 풀 수 없으므로, 한국어 스코핑은 --tags/--filter-tag
# (ASCII id 태그)를 함께 쓰는 것이 여전히 안정적이다.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]{3,}|[가-힣]{2,}")


def tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def entry_score(entry: dict[str, Any], selector: dict[str, Any]) -> int:
    allowed = set(selector.get("include_types") or [])
    if allowed and entry.get("type") not in allowed:
        return -1
    score = TYPE_PRIORITIES.get(entry.get("type", ""), 0)
    selector_tags = {str(t).lower() for t in selector.get("tags") or []}
    entry_tags = {str(t).lower() for t in entry.get("tags") or []}
    score += 18 * len(selector_tags & entry_tags)
    haystack = tokenize(" ".join([
        entry.get("id", ""),
        entry.get("type", ""),
        entry.get("description", ""),
        entry.get("content", ""),
        " ".join(entry.get("tags") or []),
    ]))
    score += len(tokenize(selector.get("query", "")) & haystack)
    metadata = entry.get("metadata") or {}
    component = metadata.get("component") or metadata.get("module")  # v0.16.0: component 우선, 옛 module 폴백
    if component and str(component).lower() in selector_tags:
        score += 12
    return score


def derive_validity(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """entry 별 파생 validity — relations 에서만 도출한다(저장하지 않는다, UD-0012).

    wm_release.derive_validity 와 같은 규칙이다(copy-form 이라 import 하지 않고 복제 — 동일성은 테스트로 고정).
      invalidated — invalidated-by 대상 RN 이 롤백되지 않음
      superseded  — 다른 entry 가 supersedes 로 가리킴
      deprecated  — principle 의 status 가 deprecated (사용자가 폐기를 선언한 원칙)
      suspended   — invalidated-by 대상 RN 이 모두 롤백됨(재유효 후보). 주입에서는 제외하지 않는다.
      우선순위: invalidated > superseded > deprecated > suspended > active
      active      — 그 외
    """
    rolled: set[str] = set()
    superseded_by: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        for rel in entry.get("relations") or []:
            if not isinstance(rel, dict):
                continue
            if entry.get("type") == "release-note" and rel.get("type") == "rolls-back" and rel.get("target"):
                rolled.add(str(rel["target"]))
            if rel.get("type") == "supersedes" and rel.get("target"):
                superseded_by[str(rel["target"])].append(entry["id"])
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        targets = [
            str(rel.get("target"))
            for rel in entry.get("relations") or []
            if isinstance(rel, dict) and rel.get("type") == "invalidated-by" and rel.get("target")
        ]
        live = [t for t in targets if t not in rolled]
        if live:
            status = "invalidated"
        elif entry["id"] in superseded_by:
            status = "superseded"
        elif entry.get("type") == "principle" and (entry.get("metadata") or {}).get("status") == "deprecated":
            status = "deprecated"
        elif targets:
            status = "suspended"
        else:
            status = "active"
        result[entry["id"]] = {"validity": status, "superseded_by": superseded_by.get(entry["id"], [])}
    return result


_SCOPE_ALIAS = {"project": "repository", "module": "directory"}   # 옛 어휘(metadata-spec 의 aliases 와 같다)
DEFAULT_STANDING_TYPES = ("principle",)
DEFAULT_STANDING_SCOPES = ("repository", "global")


def entry_scopes(entry: dict[str, Any]) -> set[str]:
    """기록의 scope(리스트 또는 스칼라, 옛 어휘 별칭 포함)를 정본 값 집합으로."""
    raw = (entry.get("metadata") or {}).get("scope")
    values = raw if isinstance(raw, list) else ([raw] if raw else [])
    return {_SCOPE_ALIAS.get(str(v), str(v)) for v in values}


def standing_entries(entries: list[dict[str, Any]], types: tuple[str, ...] = DEFAULT_STANDING_TYPES,
                     scopes: tuple[str, ...] = DEFAULT_STANDING_SCOPES) -> list[dict[str, Any]]:
    """노드 매핑과 무관하게 항상 적용되는 기록: 활성(폐기되지 않은) + 지정한 타입 + scope 가 지정한 층에 걸침.
    principle 은 status 가 accepted 인 것만(draft 는 아직 합의 전이라 제외)."""
    wanted = set(scopes)
    chosen = []
    for entry in filter_active(entries):
        if entry["type"] not in types or not (entry_scopes(entry) & wanted):
            continue
        if entry["type"] == "principle" and (entry.get("metadata") or {}).get("status") != "accepted":
            continue
        chosen.append(entry)
    chosen.sort(key=lambda e: (-TYPE_PRIORITIES.get(e["type"], 0), e.get("created_at") or "", e["id"]), reverse=False)
    return chosen


def filter_active(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """superseded/invalidated/deprecated 를 제외한 풀. 관계 확장도 이 풀 위에서만 돌아 폐기된 entry 가 재진입하지 못한다."""
    validity = derive_validity(entries)
    return [e for e in entries if validity[e["id"]]["validity"] not in INACTIVE_VALIDITY]


def expand_related(
    selected: list[dict[str, Any]],
    all_entries: list[dict[str, Any]],
    depth: int,
) -> list[dict[str, Any]]:
    if depth <= 0:
        return selected
    by_id = {entry["id"]: entry for entry in all_entries}
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in all_entries:
        for rel in entry.get("relations") or []:
            incoming[rel["target"]].append(entry)
    result: dict[str, dict[str, Any]] = {entry["id"]: entry for entry in selected}
    frontier = list(selected)
    for _ in range(depth):
        next_frontier: list[dict[str, Any]] = []
        for entry in frontier:
            neighbors = [
                by_id[rel["target"]]
                for rel in entry.get("relations") or []
                if rel["target"] in by_id
            ]
            neighbors.extend(incoming.get(entry["id"], []))
            for neighbor in neighbors:
                if neighbor["id"] not in result:
                    result[neighbor["id"]] = neighbor
                    next_frontier.append(neighbor)
        frontier = next_frontier
        if not frontier:
            break
    return list(result.values())


def build_context_pack(
    node_id: str | None,
    entries: list[dict[str, Any]],
    selector: dict[str, Any],
) -> dict[str, Any]:
    """context pack 선택.

    selector.mapped_only 가 참이고 node_id 가 있으면 entry.node 에 node_id 가 있는 entry 만 후보다
    (related 매핑 — 점수 폴백 없음, 없으면 빈 pack). 상한은 관계 확장 *후* 에 적용한다:
    직접 선택(top) 뒤에 이웃을 붙이고 전체를 top_k 로 자른다.
    """
    validity = derive_validity(entries)
    pool = [e for e in entries if validity[e["id"]]["validity"] not in INACTIVE_VALIDITY]
    if selector.get("include_inactive"):
        pool = list(entries)
    mapped_only = bool(selector.get("mapped_only")) and node_id is not None
    if mapped_only:
        candidates = [e for e in pool if node_id in (e.get("node") or [])]
    else:
        candidates = pool
    scored = [
        (score, entry)
        for entry in candidates
        if (score := entry_score(entry, selector)) >= 0
    ]
    scored.sort(key=lambda item: (-item[0], item[1].get("created_at") or "", item[1]["id"]))
    top_k = int(selector.get("top_k", DEFAULT_TOP_K))
    top = [entry for _, entry in scored[:top_k]]
    expanded = expand_related(top, pool, int(selector.get("relation_depth", DEFAULT_RELATION_DEPTH)))
    top_ids = {e["id"] for e in top}
    selected = (top + [e for e in expanded if e["id"] not in top_ids])[:top_k]
    scores = {entry["id"]: score for score, entry in scored}
    max_chars = int(selector.get("max_entry_chars", DEFAULT_MAX_ENTRY_CHARS))
    return {
        "node_id": node_id,
        "selector": selector,
        "entries": [
            {
                "id": entry["id"],
                "type": entry["type"],
                "description": entry["description"],
                "content": entry["content"][:max_chars],
                "node": entry.get("node") or [],
                "validity": validity[entry["id"]]["validity"],
                "tags": entry["tags"],
                "metadata": entry["metadata"],
                "relations": entry["relations"],
                "source_path": entry["source_path"],
                "score": scores.get(entry["id"], 0),
            }
            for entry in selected
        ],
    }


# ── selector 생성 (단일 생성자 — 컴파일 타임 IR 의 selector 와 byte-parity) ──

def selector_from_node_fields(
    node_id: str,
    node_type: str | None = None,
    phase_id: str | None = None,
    label: str | None = None,
    instruction: str | None = None,
    judge: str | None = None,
    harness: str | None = None,
    *,
    include_types: list[str] | None = None,
    top_k: int = DEFAULT_TOP_K,
    relation_depth: int = DEFAULT_RELATION_DEPTH,
    max_entry_chars: int = DEFAULT_MAX_ENTRY_CHARS,
    extra_tags: tuple[str, ...] = (),
    extra_query: str = "",
    mapped_only: bool = False,
    include_inactive: bool = False,
) -> dict[str, Any]:
    parts = [
        node_id,
        node_type or "",
        phase_id or "",
        label or "",
        instruction or "",
        judge or "",
        harness or "",
    ]
    if extra_query:
        parts.append(extra_query)
    query = " ".join(part for part in parts if part)
    tags = [node_id]
    if node_type:
        tags.append(node_type)
    for value in (phase_id, judge, harness):
        if value:
            tags.append(value)
    tags.extend(extra_tags)
    return {
        "query": query,
        "tags": sorted(set(tags)),
        "include_types": list(DEFAULT_INCLUDE_TYPES) if include_types is None else list(include_types),
        "top_k": int(top_k),
        "relation_depth": int(relation_depth),
        "max_entry_chars": int(max_entry_chars),
        "mapped_only": bool(mapped_only),
        "include_inactive": bool(include_inactive),
    }


def selector_from_query(
    query: str,
    tags: tuple[str, ...] = (),
    *,
    include_types: list[str] | None = None,
    top_k: int = DEFAULT_TOP_K,
    relation_depth: int = DEFAULT_RELATION_DEPTH,
    max_entry_chars: int = DEFAULT_MAX_ENTRY_CHARS,
    include_inactive: bool = False,
) -> dict[str, Any]:
    return {
        "query": query,
        "tags": sorted(set(tags)),
        "include_types": list(DEFAULT_INCLUDE_TYPES) if include_types is None else list(include_types),
        "top_k": int(top_k),
        "relation_depth": int(relation_depth),
        "max_entry_chars": int(max_entry_chars),
        "mapped_only": False,
        "include_inactive": bool(include_inactive),
    }


# ── 하드 필터 (런타임 스코핑 전용 — optimizer 컴파일 경로에서는 미적용) ──

def apply_hard_filters(
    entries: list[dict[str, Any]],
    require_tags: tuple[str, ...] = (),
    require_module: str | None = None,
) -> list[dict[str, Any]]:
    """스코어링/확장 *이전에* 적용 — 확장도 필터된 풀 위에서만 돌아
    스코프 밖 이웃이 relation 을 타고 재진입할 수 없다."""
    required = {t.lower() for t in require_tags}
    out: list[dict[str, Any]] = []
    for entry in entries:
        entry_tags = {str(t).lower() for t in entry.get("tags") or []}
        if required and not required <= entry_tags:
            continue
        if require_module is not None:
            md = entry.get("metadata") or {}
            module = str(md.get("component") or md.get("module") or "")
            if module.lower() != require_module.lower():
                continue
        out.append(entry)
    return out


# ── TTL 노드 해석 (rdflib — --ttl 경로에서만 필요) ──

_WF_NS = "https://mso.dev/ontology/workflow#"


def _safe_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("_") or "workflow"


def _local_id(uri: Any) -> str:
    text = str(uri)
    if "#" in text:
        text = text.rsplit("#", 1)[1]
    if "/" in text:
        text = text.rsplit("/", 1)[1]
    return _safe_id(text)


def node_fields_from_ttl(ttl_path: Path, node_id: str) -> dict[str, Any]:
    """ABox TTL 에서 node_id 의 selector 재료(type/phase/label/instruction/judge/harness)를 해석."""
    try:
        from rdflib import Graph, Namespace, RDF, URIRef
    except ImportError:
        raise SystemExit(
            "[ERROR] --ttl 은 rdflib 가 필요하다 (pip install rdflib). "
            "TTL 없이 node id-seed 경로를 쓰려면 --ttl 을 빼고 실행."
        )
    wf = Namespace(_WF_NS)
    g = Graph()
    g.parse(ttl_path, format="turtle")

    type_map = {
        wf.Step: "step",
        wf.Decision: "decision",
        wf.Validation: "validation",
        wf.Group: "group",
    }

    def _literal(subj: Any, pred: Any) -> str | None:
        value = next(g.objects(subj, pred), None)
        return str(value) if value is not None else None

    available: list[str] = []
    match_subj = None
    match_type = None
    for cls, node_type in type_map.items():
        for subj in sorted((s for s in g.subjects(RDF.type, cls) if isinstance(s, URIRef)), key=str):
            local = _local_id(subj)
            available.append(local)
            if local == node_id:
                match_subj = subj
                match_type = node_type
    if match_subj is None:
        raise SystemExit(
            f"[ERROR] node '{node_id}' 를 {ttl_path} 에서 찾지 못함. "
            f"가용 node: {', '.join(sorted(set(available))) or '(없음)'}"
        )

    phase_id = None
    for phase in g.subjects(RDF.type, wf.Phase):
        if match_subj in set(g.objects(phase, wf.hasNode)):
            phase_id = _local_id(phase)
            break

    return {
        "node_type": match_type,
        "phase_id": phase_id,
        "label": _literal(match_subj, wf.label),
        "instruction": _literal(match_subj, wf.instruction),
        "judge": _literal(match_subj, wf.judge),
        "harness": _literal(match_subj, wf.harness),
    }


# ── workflow cursor (UD-0015) ──
#
# "지금 어느 workflow node 를 수행 중인가" 를 담는 가변 상태. work-memory JSONL 은
# append-only 이벤트 로그라 가변 커서를 둘 수 없으므로(RN 의 "current 는 derived
# view — 저장 금지" 와 같은 경계), provider-neutral .mso/state/ 의 gitignore 대상
# 파일에 둔다. v0.10.0의 .claude/state/ 커서는 읽기·삭제 fallback으로만 지원한다.

CURSOR_REL_PATH = Path(".mso") / "state" / "workflow-cursor.json"
LEGACY_CURSOR_REL_PATHS = (Path(".claude") / "state" / "workflow-cursor.json",)


def project_root(project_dir: Path | None = None) -> Path:
    if project_dir is not None:
        return project_dir
    return Path(
        os.environ.get("PROJECT_DIR")
        or os.environ.get("CODEX_PROJECT_DIR")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or "."
    )


def cursor_path(project_dir: Path | None = None) -> Path:
    return (project_root(project_dir) / CURSOR_REL_PATH).resolve()


def cursor_read_paths(project_dir: Path | None = None) -> tuple[Path, ...]:
    base = project_root(project_dir)
    return tuple((base / rel).resolve() for rel in (CURSOR_REL_PATH, *LEGACY_CURSOR_REL_PATHS))


def read_cursor(project_dir: Path | None = None) -> dict[str, Any] | None:
    for path in cursor_read_paths(project_dir):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and data.get("node"):
            return data
    return None


def write_cursor(node: str, ttl: str | None = None, project_dir: Path | None = None) -> Path:
    path = cursor_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"node": node}
    if ttl:
        payload["ttl"] = str(Path(ttl).resolve())
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ── 출력 ──

def render_plain(
    pack: dict[str, Any],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    full: bool = False,
    skip_ids: frozenset[str] | set[str] = frozenset(),
    show_cmd: str | None = None,
) -> tuple[str, list[str]]:
    """컨텍스트 주입용 컴팩트 블록과 이번에 낸 id 목록. 낼 entry 가 없으면 ("", []) (hook 안전).

    기본은 요약 목록(`id [type] description`)이다. content 는 --full 일 때만 붙인다.
    max_chars 는 출력 전체의 글자 예산이다. 넘치면 남은 건수를 알리고 멈춘다.
    """
    entries = [e for e in (pack.get("entries") or []) if e["id"] not in skip_ids]
    if not entries:
        return "", []
    subject = pack.get("node_id") or (pack.get("selector") or {}).get("query", "")
    if len(subject) > 60:
        subject = subject[:57] + "…"
    lines = [f"[work-memory context: {subject}]"]
    used = len(lines[0])
    emitted: list[str] = []
    for index, entry in enumerate(entries):
        block = [f"  ── {entry['id']} [{entry['type']}] {entry['description']}"]
        if full:
            for text_line in (entry.get("content") or "").strip().splitlines():
                block.append(f"     {text_line}")
        size = sum(len(line) + 1 for line in block)
        if emitted and used + size > max_chars:
            remaining = len(entries) - index
            lines.append(f"  … +{remaining} more — 펼치기: wm_context.py show <id>")
            break
        lines.extend(block)
        used += size
        emitted.append(entry["id"])
    if show_cmd and emitted:
        # 모델이 content 를 펼칠 수 있게 실제 실행 가능한 명령을 매번 알린다(예산에는 넣지 않는다).
        lines.append(f"  (본문 펼치기: {show_cmd} <id>)")
    return "\n".join(lines), emitted


def _read_seen(path: str | None, ttl: float = DEFAULT_SEEN_TTL) -> set[str]:
    """이미 낸 id. 파일은 {id: 낸 시각(epoch)} 이다(옛 list 형식도 읽는다 — 시각 없음=만료 안 함).

    ttl 초가 지난 id 는 다시 낸다 — /compact 등으로 앞서 주입한 내용이 컨텍스트에서 사라졌을 수 있기 때문이다.
    ttl<=0 이면 중복 방지를 끈다(항상 빈 집합).
    """
    if not path or ttl <= 0:
        return set()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    now = time.time()
    if isinstance(data, list):
        return {str(i) for i in data}
    if isinstance(data, dict):
        return {str(k) for k, ts in data.items() if isinstance(ts, (int, float)) and now - ts < ttl}
    return set()


def _write_seen(path: str | None, emitted: list[str], ttl: float = DEFAULT_SEEN_TTL) -> None:
    if not path or ttl <= 0:
        return
    now = time.time()
    try:
        target = Path(path)
        try:
            old = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old = {}
        kept = {str(k): ts for k, ts in old.items() if isinstance(ts, (int, float)) and now - ts < ttl} if isinstance(old, dict) else {}
        for eid in emitted:
            kept[eid] = now
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(kept, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    except OSError:
        pass  # 중복 방지 상태를 못 쓰는 것은 주입 실패가 아니다


# ── CLI ──

def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tags", default="", help="soft boost: selector tags 에 추가 (comma-separated)")
    parser.add_argument("--module", default=None, help="soft boost: 태그 + metadata.component(옛 module) 보너스 활성화")
    parser.add_argument("--filter-tag", action="append", default=[], help="hard filter (반복 가능, AND)")
    parser.add_argument("--filter-module", default=None, help="hard filter: metadata.component(옛 module) 일치")
    parser.add_argument("--include-types", default=None, help="comma-separated 타입 게이트 (기본 8종, 'all'=해제)")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--relation-depth", type=int, default=DEFAULT_RELATION_DEPTH)
    parser.add_argument("--max-entry-chars", type=int, default=DEFAULT_MAX_ENTRY_CHARS,
                        help="content 를 자르는 글자 수 (--full·--json 에만 영향)")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, help="요약 목록 총량 예산(글자)")
    parser.add_argument("--full", action="store_true", help="description 뒤에 content 도 붙인다")
    parser.add_argument("--include-inactive", action="store_true", help="superseded/invalidated entry 도 포함")
    parser.add_argument("--seen-file", default=None, help="이미 낸 id 를 건너뛰고 이번에 낸 id 를 기록 (세션 내 중복 방지)")
    parser.add_argument("--seen-ttl", type=float, default=DEFAULT_SEEN_TTL,
                        help="seen 만료(초). 지나면 다시 낸다. 0 이하면 중복 방지 끔 (기본 900)")
    parser.add_argument("--extra-root", action="append", default=[], help="추가 work-memory 루트 (반복 가능)")
    parser.add_argument("--root", default=None, help="WORKMEM_DIR 오버라이드")
    parser.add_argument("--json", action="store_true", help="JSON pack 출력 (빈 결과도 유효 pack)")


def _parse_include_types(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    if raw.strip().lower() == "all":
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def _split_tags(raw: str) -> tuple[str, ...]:
    return tuple(t.strip() for t in raw.split(",") if t.strip())


def _cmd_cursor(args) -> int:
    if args.cursor_cmd == "set":
        path = write_cursor(args.node, args.ttl)
        print(f"✓ cursor: {args.node}" + (f" (ttl={args.ttl})" if args.ttl else "") + f"  → {path}")
        return 0
    if args.cursor_cmd == "show":
        cursor = read_cursor()
        if cursor:
            print(json.dumps(cursor, ensure_ascii=False))
        return 0
    removed = []
    for path in cursor_read_paths():
        if path.exists():
            path.unlink()
            removed.append(path)
    if removed:
        print("✓ cursor 제거: " + ", ".join(str(path) for path in removed))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="런타임 work-memory context-pack 검색 (lexical)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_node = sub.add_parser("node", help="workflow node id 기준 검색")
    p_node.add_argument("--node", required=True, help="workflow node id (예: development-s-001)")
    p_node.add_argument("--ttl", default=None, help="workflow ABox TTL — node 필드로 selector 구성 (rdflib 필요)")
    p_node.add_argument("--fallback", choices=("score", "none"), default="score",
                        help="node 에 매핑된 entry 가 없을 때: score=점수로 채움(기본, 기존 동작) / none=침묵(훅 기본)")
    _add_common_flags(p_node)

    p_query = sub.add_parser("query", help="자유 질의 검색")
    p_query.add_argument("text", help="검색 질의")
    _add_common_flags(p_query)

    p_show = sub.add_parser("show", help="entry 한 건의 description + content 전문 (펼치기)")
    p_show.add_argument("id")
    p_show.add_argument("--extra-root", action="append", default=[], help="추가 work-memory 루트 (반복 가능)")
    p_show.add_argument("--root", default=None, help="WORKMEM_DIR 오버라이드")

    p_standing = sub.add_parser("standing", help="노드와 무관하게 항상 적용되는 교훈(scope 가 repository/global 인 accepted principle) 요약")
    p_standing.add_argument("--types", default=",".join(DEFAULT_STANDING_TYPES), help="comma-separated 타입 (기본 principle)")
    p_standing.add_argument("--scopes", default=",".join(DEFAULT_STANDING_SCOPES), help="comma-separated scope (기본 repository,global)")
    p_standing.add_argument("--top-k", type=int, default=5)
    p_standing.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    p_standing.add_argument("--extra-root", action="append", default=[], help="추가 work-memory 루트 (반복 가능)")
    p_standing.add_argument("--root", default=None, help="WORKMEM_DIR 오버라이드")
    p_standing.add_argument("--json", action="store_true")

    p_cursor = sub.add_parser("cursor", help="workflow 위치 커서 (UserPromptSubmit 훅이 읽는다)")
    cur_sub = p_cursor.add_subparsers(dest="cursor_cmd", required=True)
    c_set = cur_sub.add_parser("set", help="현재 수행 중인 node 기록")
    c_set.add_argument("node")
    c_set.add_argument("--ttl", default=None, help="workflow ABox TTL 경로 (선택)")
    cur_sub.add_parser("show", help="현재 커서 출력 (없으면 무출력)")
    cur_sub.add_parser("clear", help="커서 제거 — node 이탈 시")

    args = ap.parse_args(argv)

    if args.cmd == "cursor":
        return _cmd_cursor(args)

    if args.cmd == "standing":
        root = Path(args.root).resolve() if args.root else workmem_root()
        extra_roots = tuple(Path(p).resolve() for p in args.extra_root)
        entries = load_entries(root, extra_roots) if root.exists() or extra_roots else []
        types = tuple(t.strip() for t in args.types.split(",") if t.strip())
        scopes = tuple(t.strip() for t in args.scopes.split(",") if t.strip())
        chosen = standing_entries(entries, types, scopes)[: max(args.top_k, 0)]
        validity = derive_validity(entries)
        pack = {"node_id": "standing", "selector": {"query": "standing"}, "entries": [
            {"id": e["id"], "type": e["type"], "description": e["description"], "content": e["content"], "node": e.get("node") or [],
             "validity": validity[e["id"]]["validity"], "tags": e["tags"], "metadata": e["metadata"], "relations": e["relations"],
             "source_path": e["source_path"], "score": 0} for e in chosen]}
        if args.json:
            print(json.dumps(pack, ensure_ascii=False, indent=2))
        else:
            show_cmd = f'{sys.executable} "{Path(__file__).resolve()}" show --root "{root}"'
            rendered, _emitted = render_plain(pack, max_chars=args.max_chars, show_cmd=show_cmd)
            if rendered:
                print(rendered.replace("[work-memory context: standing]", "[work-memory standing — 항상 적용되는 교훈]", 1))
        return 0

    if args.cmd == "show":
        root = Path(args.root).resolve() if args.root else workmem_root()
        extra_roots = tuple(Path(p).resolve() for p in args.extra_root)
        entries = load_entries(root, extra_roots) if root.exists() or extra_roots else []
        found = next((e for e in entries if e["id"] == args.id), None)
        if found is None:
            print(f"[ERROR] entry 없음: {args.id}", file=sys.stderr)
            return 1
        status = derive_validity(entries)[found["id"]]["validity"]
        print(f"{found['id']} [{found['type']}] ({status})")
        print(f"  description: {found['description']}")
        print(found["content"])
        return 0

    extra_tags = _split_tags(args.tags)
    if args.module:
        extra_tags = (*extra_tags, args.module)
    include_types = _parse_include_types(args.include_types)
    common = {
        "include_types": include_types,
        "top_k": args.top_k,
        "relation_depth": args.relation_depth,
        "max_entry_chars": args.max_entry_chars,
        "include_inactive": args.include_inactive,
    }

    if args.cmd == "node":
        if args.ttl:
            fields = node_fields_from_ttl(Path(args.ttl), args.node)
            selector = selector_from_node_fields(
                args.node, extra_tags=extra_tags, mapped_only=args.fallback == "none", **fields, **common,
            )
        else:
            selector = selector_from_node_fields(
                args.node, extra_tags=extra_tags, mapped_only=args.fallback == "none", **common,
            )
        node_id: str | None = args.node
    else:
        selector = selector_from_query(args.text, tags=extra_tags, **common)
        node_id = None

    root = Path(args.root).resolve() if args.root else workmem_root()
    extra_roots = tuple(Path(p).resolve() for p in args.extra_root)
    entries = load_entries(root, extra_roots) if root.exists() or extra_roots else []
    entries = apply_hard_filters(
        entries,
        require_tags=tuple(args.filter_tag),
        require_module=args.filter_module,
    )
    pack = build_context_pack(node_id, entries, selector)

    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
    else:
        seen = _read_seen(args.seen_file, args.seen_ttl)
        show_cmd = f'{sys.executable} "{Path(__file__).resolve()}" show --root "{root}"'
        rendered, emitted = render_plain(
            pack, max_chars=args.max_chars, full=args.full, skip_ids=frozenset(seen), show_cmd=show_cmd,
        )
        if rendered:
            print(rendered)
            _write_seen(args.seen_file, emitted, args.seen_ttl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
