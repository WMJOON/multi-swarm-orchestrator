#!/usr/bin/env python3
"""wm_context.py — 런타임 context-pack 검색 (lexical ranking, stdlib-only core).

ContextPack 스코어링/선택 로직의 정본(canonical home). mso-workflow-optimizer 의
compile_workflow.py 가 컴파일 타임에 이 모듈을 로드해 동일 로직을 재사용한다
(단일 정본). zvec 의존 없음 — 랭킹은 lexical 전용:
타입 우선순위 + 18×태그 교집합 + 토큰 매치 + 12 module 보너스.

  node   workflow node id 기준 검색. --ttl 로 ABox 에서 label/instruction/phase
         등을 selector 재료로 해석 (rdflib 필요). --ttl 없으면 node id 만
         tag+query seed 로 쓰는 저비용 경로 (rdflib 불필요).
  query  자유 질의 검색 (workflow 레일 밖 execution 단위용).

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
from collections import defaultdict
from pathlib import Path
from typing import Any

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
        "title": str(obj.get("title") or ""),
        "text": str(obj.get("text") or ""),
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


def load_entries(root: Path, extra_roots: tuple[Path, ...] = ()) -> list[dict[str, Any]]:
    """루트(들)의 모든 *.jsonl 을 entry dict 리스트로 로드.

    dot-dir(.zvec, .migration-archive 등)는 스킵. id 는 전체 루트를 가로질러
    first-seen-wins dedup — 메인 루트가 extra 루트보다 우선한다.
    """
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for base in (root, *extra_roots):
        if not base or not base.exists():
            continue
        for path in sorted(base.rglob("*.jsonl")):
            rel = path.relative_to(base)
            if any(part.startswith(".") for part in rel.parts[:-1]):
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
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
        entry.get("title", ""),
        entry.get("text", ""),
        " ".join(entry.get("tags") or []),
    ]))
    score += len(tokenize(selector.get("query", "")) & haystack)
    metadata = entry.get("metadata") or {}
    if metadata.get("module") and str(metadata["module"]).lower() in selector_tags:
        score += 12
    return score


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
    scored = [
        (score, entry)
        for entry in entries
        if (score := entry_score(entry, selector)) >= 0
    ]
    scored.sort(key=lambda item: (-item[0], item[1].get("created_at") or "", item[1]["id"]))
    top = [entry for _, entry in scored[: int(selector.get("top_k", DEFAULT_TOP_K))]]
    selected = expand_related(top, entries, int(selector.get("relation_depth", DEFAULT_RELATION_DEPTH)))
    scores = {entry["id"]: score for score, entry in scored}
    max_chars = int(selector.get("max_entry_chars", DEFAULT_MAX_ENTRY_CHARS))
    return {
        "node_id": node_id,
        "selector": selector,
        "entries": [
            {
                "id": entry["id"],
                "type": entry["type"],
                "title": entry["title"],
                "text": entry["text"][:max_chars],
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
    }


def selector_from_query(
    query: str,
    tags: tuple[str, ...] = (),
    *,
    include_types: list[str] | None = None,
    top_k: int = DEFAULT_TOP_K,
    relation_depth: int = DEFAULT_RELATION_DEPTH,
    max_entry_chars: int = DEFAULT_MAX_ENTRY_CHARS,
) -> dict[str, Any]:
    return {
        "query": query,
        "tags": sorted(set(tags)),
        "include_types": list(DEFAULT_INCLUDE_TYPES) if include_types is None else list(include_types),
        "top_k": int(top_k),
        "relation_depth": int(relation_depth),
        "max_entry_chars": int(max_entry_chars),
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
            module = str((entry.get("metadata") or {}).get("module") or "")
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
# view — 저장 금지" 와 같은 경계), stop-check.state 선례를 따라 .claude/state/ 의
# gitignore 대상 파일에 둔다.

CURSOR_REL_PATH = Path(".claude") / "state" / "workflow-cursor.json"


def cursor_path(project_dir: Path | None = None) -> Path:
    base = project_dir or Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("PROJECT_DIR") or ".")
    return (base / CURSOR_REL_PATH).resolve()


def read_cursor(project_dir: Path | None = None) -> dict[str, Any] | None:
    path = cursor_path(project_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or not data.get("node"):
        return None
    return data


def write_cursor(node: str, ttl: str | None = None, project_dir: Path | None = None) -> Path:
    path = cursor_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"node": node}
    if ttl:
        payload["ttl"] = str(Path(ttl).resolve())
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ── 출력 ──

def render_plain(pack: dict[str, Any]) -> str:
    """컨텍스트 주입용 컴팩트 블록. entry 없으면 빈 문자열 (hook 안전)."""
    entries = pack.get("entries") or []
    if not entries:
        return ""
    subject = pack.get("node_id") or (pack.get("selector") or {}).get("query", "")
    if len(subject) > 60:
        subject = subject[:57] + "…"
    lines = [f"[work-memory context: {subject}]"]
    for entry in entries:
        lines.append(f"  ── {entry['id']} [{entry['type']}] {entry['title']}  (score {entry['score']})")
        text = (entry.get("text") or "").strip()
        if text:
            for text_line in text.splitlines():
                lines.append(f"     {text_line}")
    return "\n".join(lines)


# ── CLI ──

def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tags", default="", help="soft boost: selector tags 에 추가 (comma-separated)")
    parser.add_argument("--module", default=None, help="soft boost: module 태그 + metadata.module 보너스 활성화")
    parser.add_argument("--filter-tag", action="append", default=[], help="hard filter (반복 가능, AND)")
    parser.add_argument("--filter-module", default=None, help="hard filter: metadata.module 일치")
    parser.add_argument("--include-types", default=None, help="comma-separated 타입 게이트 (기본 8종, 'all'=해제)")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--relation-depth", type=int, default=DEFAULT_RELATION_DEPTH)
    parser.add_argument("--max-entry-chars", type=int, default=DEFAULT_MAX_ENTRY_CHARS)
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
    path = cursor_path()
    if path.exists():
        path.unlink()
        print(f"✓ cursor 제거: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="런타임 work-memory context-pack 검색 (lexical)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_node = sub.add_parser("node", help="workflow node id 기준 검색")
    p_node.add_argument("--node", required=True, help="workflow node id (예: development-s-001)")
    p_node.add_argument("--ttl", default=None, help="workflow ABox TTL — node 필드로 selector 구성 (rdflib 필요)")
    _add_common_flags(p_node)

    p_query = sub.add_parser("query", help="자유 질의 검색")
    p_query.add_argument("text", help="검색 질의")
    _add_common_flags(p_query)

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

    extra_tags = _split_tags(args.tags)
    if args.module:
        extra_tags = (*extra_tags, args.module)
    include_types = _parse_include_types(args.include_types)
    common = {
        "include_types": include_types,
        "top_k": args.top_k,
        "relation_depth": args.relation_depth,
        "max_entry_chars": args.max_entry_chars,
    }

    if args.cmd == "node":
        if args.ttl:
            fields = node_fields_from_ttl(Path(args.ttl), args.node)
            selector = selector_from_node_fields(
                args.node, extra_tags=extra_tags, **fields, **common,
            )
        else:
            selector = selector_from_node_fields(args.node, extra_tags=extra_tags, **common)
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
        rendered = render_plain(pack)
        if rendered:
            print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
