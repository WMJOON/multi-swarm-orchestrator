#!/usr/bin/env python3
"""
wm_node.py — Work Memory CLI

사용법:
  wm_node.py new <type> --title "..." [--tags a,b] [--related ID:rel-type] [--module M]
  wm_node.py validate <path>                # 단일 파일 또는 디렉토리 트리
  wm_node.py search "<query>" [--type T] [--tag X] [--limit 10]
  wm_node.py graph <id> [--depth 3] [--direction in|out|both]
  wm_node.py stats
  wm_node.py reindex                        # zvec 인덱스 재빌드
  wm_node.py show <id>                      # 단일 entry 출력

type ∈ {issue-note, agent-decision, user-decision, trouble-shooting,
        episode, pattern, principle, auditlog, worklog}

환경변수:
  WORKMEM_DIR — work-memory 루트 (기본: ./agent-context/work-memory)
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import yaml

# ─── 타입·relation 어휘 (schema-driven, 하위호환) ────────────────────────
# 기본값 = work-memory 표준(7 entry + auditlog/worklog). WORKMEM_DIR/schema.yaml 에
# 머신리더블 `types:` / `relation_types:` 가 있으면 그것으로 override → 같은 엔진을
# 다른 스코프(예: user-memory UC/UP/UF)로 재사용. 없으면 이 기본값(기존 동작 보존).
_DEFAULT_TYPE_PREFIX = {
    "issue-note": "IN",
    "agent-decision": "AD",
    "user-decision": "UD",
    "alternatives-record": "AR",
    "trouble-shooting": "TS",
    "release-note": "RN",
    "episode": "EP",
    "pattern": "PT",
    "principle": "PR",
    "auditlog": "AU",
    "worklog": "WL",
}

# dir = entry 가 담길 **부모 디렉토리** (schema v1.2.0). 실제 저장 파일은:
#   track/insight    : <dir>/<type>.jsonl  (aggregate append — entry_file() 참조)
#   auditlog/worklog : <dir>/<id>.jsonl    (일별/시각별 — 기존 유지)
_DEFAULT_TYPE_DIR = {
    "issue-note": "track-record",
    "agent-decision": "track-record",
    "user-decision": "track-record",
    "alternatives-record": "track-record",
    "trouble-shooting": "track-record",
    "release-note": "release-record",
    "episode": "insight-record",
    "pattern": "insight-record",
    "principle": "insight-record",
    "auditlog": "auditlog",
    "worklog": "worklog",
}

# 시각 기반 id 를 쓰는 타입(자동 로그) — 파일명 = <id>.jsonl, 그 외는 aggregate <type>.jsonl
_TIME_SERIES_TYPES = ("auditlog", "worklog")

REQUIRED_FIELDS = ["id", "type", "title", "text", "tags", "created_at"]  # 스코프 불변

_DEFAULT_ALLOWED_RELATIONS = {
    "raised", "followed-by", "resolved-by", "caused-by",
    "released-in", "verified-in", "invalidated-by", "rolls-back",
    "analyzed-in", "shows-pattern", "generalized-in", "crystallized-in",
    "references", "supersedes", "refines", "depends-on",
}


def _load_vocab():
    """WORKMEM_DIR/schema.yaml 의 `types:`/`relation_types:` 로 어휘 결정.
    없거나 파싱 실패 시 work-memory 기본값(하위호환). `types:` 항목은
    {<type>: {prefix, dir}} 형태. relation_types 는 dict(설명)/list 허용 → 키만 사용."""
    tp, td = dict(_DEFAULT_TYPE_PREFIX), dict(_DEFAULT_TYPE_DIR)
    ar = set(_DEFAULT_ALLOWED_RELATIONS)
    sp = Path(os.environ.get("WORKMEM_DIR", "./agent-context/work-memory")).resolve() / "schema.yaml"
    try:
        s = yaml.safe_load(open(sp, encoding="utf-8")) or {}
    except Exception:
        return tp, td, ar
    types = s.get("types")
    if isinstance(types, dict) and types:
        try:
            tp = {k: v["prefix"] for k, v in types.items()}
            td = {k: v["dir"] for k, v in types.items()}
        except (KeyError, TypeError):
            tp, td = dict(_DEFAULT_TYPE_PREFIX), dict(_DEFAULT_TYPE_DIR)
    rtv = s.get("relation_types")
    if isinstance(rtv, dict) and rtv:
        ar = set(rtv.keys())
    elif isinstance(rtv, list) and rtv:
        ar = set(rtv)
    return tp, td, ar


TYPE_PREFIX, TYPE_DIR, ALLOWED_RELATIONS = _load_vocab()


def workmem_root() -> Path:
    return Path(os.environ.get("WORKMEM_DIR", "./agent-context/work-memory")).resolve()


# ─── id allocation ────────────────────────────────────────

def entry_file(entry_type: str, entry_id: str) -> Path:
    """entry 가 저장될 파일 경로.
    track/insight  = <dir>/<type>.jsonl  (aggregate append-only),
    auditlog/worklog = <dir>/<id>.jsonl  (일별/시각별 — 기존 유지)."""
    parent = workmem_root() / TYPE_DIR[entry_type]
    if entry_type in _TIME_SERIES_TYPES:
        return parent / f"{entry_id}.jsonl"
    return parent / f"{entry_type}.jsonl"


def _scan_max_seq(entry_type: str) -> int:
    """해당 prefix 의 최대 시퀀스 번호.
    신규 aggregate 파일의 record.id 와 구버전 per-entry 파일명(<dir>/**/<PREFIX>-NNNN.jsonl)을
    모두 스캔한다 — 마이그레이션 전/후 또는 두 포맷 공존 시 id 재사용을 막는다."""
    prefix = TYPE_PREFIX[entry_type]
    parent = workmem_root() / TYPE_DIR[entry_type]
    max_n = 0
    id_pat = re.compile(rf"^{re.escape(prefix)}-(\d{{4}})$")
    # 1) 신규 aggregate 파일의 record id 들
    agg = entry_file(entry_type, "")
    if agg.is_file():
        for line in agg.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            m = id_pat.match(obj.get("id", "") if isinstance(obj, dict) else "")
            if m:
                max_n = max(max_n, int(m.group(1)))
    # 2) 구버전 per-entry 파일명 (하위호환)
    if parent.exists():
        f_pat = re.compile(rf"^{re.escape(prefix)}-(\d{{4}})\.jsonl$")
        for f in parent.rglob(f"{prefix}-*.jsonl"):
            m = f_pat.match(f.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return max_n


def next_id(entry_type: str) -> str:
    prefix = TYPE_PREFIX[entry_type]
    if entry_type in _TIME_SERIES_TYPES:
        # 시각 기반 id
        now = dt.datetime.now(dt.timezone.utc)
        return f"{prefix}-{now.strftime('%Y%m%d-%H%M%S')}"
    # 시퀀스 기반 (aggregate + 구버전 per-entry 모두 스캔)
    return f"{prefix}-{_scan_max_seq(entry_type) + 1:04d}"


# ─── new ─────────────────────────────────────────────────

def cmd_new(args):
    t = args.type
    if t not in TYPE_PREFIX:
        sys.exit(f"[ERROR] 알 수 없는 type: {t}")

    new_id = next_id(t)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tags = [s.strip() for s in (args.tags or "").split(",") if s.strip()]
    if args.module:
        tags.append(args.module)

    relations = []
    for rel in (args.related or []):
        if ":" not in rel:
            print(f"[WARN] --related 형식 잘못됨: {rel} (예: TS-0017:resolved-by)", file=sys.stderr)
            continue
        target, rel_type = rel.split(":", 1)
        if rel_type not in ALLOWED_RELATIONS:
            print(f"[WARN] 알 수 없는 relation: {rel_type}", file=sys.stderr)
        relations.append({"type": rel_type, "target": target})

    file_path = entry_file(t, new_id)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    source_path = str(file_path.relative_to(workmem_root().parent.parent)) if workmem_root().parent.parent in file_path.parents else str(file_path)

    entry = {
        "id": new_id,
        "type": t,
        "title": args.title or "TODO: title",
        "text": args.text or "TODO: 본문 (markdown 가능)",
        "tags": tags,
        "created_at": now,
        "source_path": source_path,
        "author": args.author or "agent",
        "relations": relations,
        "metadata": {},
    }
    if args.module:
        entry["metadata"]["module"] = args.module

    # aggregate append-only JSONL (한 줄 = 한 entry). 같은 id 가 파일 끝에 이미
    # 있으면(중복 append) skip — auditlog/worklog 의 EOF dedup 과 동일한 안전장치.
    if file_path.exists():
        existing = file_path.read_text(encoding="utf-8").splitlines()
        for ln in reversed(existing):
            ln = ln.strip()
            if not ln:
                continue
            try:
                if json.loads(ln).get("id") == new_id:
                    print(f"[WARN] {new_id} 가 이미 {file_path} 끝에 있음 — append skip")
                    return
            except (json.JSONDecodeError, AttributeError):
                pass
            break
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False))
        f.write("\n")
    print(f"✓ append: {file_path}")
    print(f"  id={new_id}")
    if args.print:
        print(json.dumps(entry, ensure_ascii=False, indent=2))


# ─── validate ────────────────────────────────────────────

def _load_entries(path: Path):
    """단일 파일 또는 디렉토리에서 모든 jsonl entry 를 yield."""
    if path.is_file():
        if path.suffix == ".jsonl":
            for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError as e:
                    yield path, line_num, {"_parse_error": str(e), "_line": line[:80]}
                    continue
                # bare string/숫자/배열 라인은 entry(dict) 가 아니므로 PARSE 이슈로 보고.
                if not isinstance(parsed, dict):
                    yield path, line_num, {
                        "_parse_error": f"non-dict 라인 ({type(parsed).__name__})",
                        "_line": line[:80],
                    }
                    continue
                yield path, line_num, parsed
        return
    for jf in path.rglob("*.jsonl"):
        # dot-디렉토리(.migration-archive, .zvec 등 메타/아카이브)는 read 대상에서 제외
        if any(p.startswith(".") for p in jf.relative_to(path).parts[:-1]):
            continue
        yield from _load_entries(jf)


def cmd_validate(args):
    target = Path(args.path).resolve()
    if not target.exists():
        sys.exit(f"[ERROR] 경로 없음: {args.path}")

    issues = []
    total = 0
    seen_ids = {}

    for src, line_num, entry in _load_entries(target):
        total += 1
        ctx = f"{src.name}:{line_num}"

        if "_parse_error" in entry:
            issues.append(f"[PARSE] {ctx}: {entry['_parse_error']}")
            continue

        for field in REQUIRED_FIELDS:
            if not entry.get(field):
                issues.append(f"[MISSING] {ctx}: {field}")

        eid = entry.get("id")
        if eid:
            if eid in seen_ids:
                issues.append(f"[DUP-ID] {eid} ({ctx} ↔ {seen_ids[eid]})")
            seen_ids[eid] = ctx

        etype = entry.get("type")
        if etype and etype not in TYPE_PREFIX:
            issues.append(f"[TYPE] {ctx}: 알 수 없는 type={etype}")
        if eid and etype and not eid.startswith(TYPE_PREFIX.get(etype, "")):
            issues.append(f"[PREFIX] {ctx}: id={eid} 가 type={etype} prefix 와 불일치")

        for rel in entry.get("relations", []) or []:
            rt = rel.get("type")
            if rt and rt not in ALLOWED_RELATIONS:
                issues.append(f"[REL] {ctx}: 알 수 없는 relation type={rt}")
            if not rel.get("target"):
                issues.append(f"[REL] {ctx}: relation target 없음")

    print(f"\n검증: {target}")
    print(f"  총 entry: {total}, 이슈: {len(issues)}\n")
    if not issues:
        print("  ✓ 모든 entry 가 스키마를 준수합니다.")
        return 0
    for i in issues:
        print(f"  ✗ {i}")
    return 1


# ─── search (zvec) ───────────────────────────────────────

def cmd_search(args):
    """zvec 인덱스를 통한 시맨틱 검색. simple-knowledge-zvec 의 simple_kb.py 호출."""
    import shutil
    import subprocess

    kb_path = workmem_root() / ".zvec"
    if not kb_path.exists():
        sys.exit(f"[ERROR] zvec 인덱스 없음. 먼저 `wm_node.py reindex` 실행.\n  expected: {kb_path}")

    # simple_kb.py 위치 탐색
    candidates = [
        Path.home() / ".claude" / "skills" / "simple-knowledge-zvec" / "scripts" / "simple_kb.py",
        Path(__file__).parent.parent.parent / "simple-knowledge-zvec" / "scripts" / "simple_kb.py",
    ]
    simple_kb = next((p for p in candidates if p.exists()), None)
    if not simple_kb:
        sys.exit("[ERROR] simple_kb.py 를 찾을 수 없음. simple-knowledge-zvec 스킬 설치 필요.")

    cmd = ["python3", str(simple_kb), "search", "--path", str(kb_path), args.query]
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    if args.tag:
        cmd += ["--tags", args.tag]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    return 0


# ─── graph traversal ─────────────────────────────────────

def _build_graph():
    """전체 entry 를 읽어 id → entry, id → outgoing, id → incoming 맵 구성."""
    root = workmem_root()
    entries_by_id = {}
    out_edges = {}  # id → [(target, type)]
    in_edges = {}   # id → [(source, type)]

    for jf in root.rglob("*.jsonl"):
        # dot-디렉토리(.migration-archive, .zvec 등)는 그래프/검색 대상에서 제외
        if any(p.startswith(".") for p in jf.relative_to(root).parts[:-1]):
            continue
        for line_num, line in enumerate(jf.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            # JSONL 불변식: 한 줄 = 한 객체. bare string/숫자/배열 라인(예: pretty-print
            # 으로 멀티라인 분해된 entry 의 잔여 줄)은 dict 가 아니므로 skip + 경고.
            if not isinstance(e, dict):
                print(f"[WARN] {jf.name}:{line_num} 비-dict jsonl 라인 skip "
                      f"({type(e).__name__}): {line[:60]}", file=sys.stderr)
                continue
            eid = e.get("id")
            if not eid:
                continue
            entries_by_id[eid] = e
            for rel in e.get("relations", []) or []:
                tgt = rel.get("target")
                rt = rel.get("type")
                if not tgt:
                    continue
                out_edges.setdefault(eid, []).append((tgt, rt))
                in_edges.setdefault(tgt, []).append((eid, rt))
    return entries_by_id, out_edges, in_edges


def cmd_graph(args):
    entries, out_e, in_e = _build_graph()
    start = args.id
    if start not in entries:
        print(f"[WARN] {start} entry 미존재 (참조만 있을 수 있음)")
    print(f"\nGraph traversal from {start} (depth={args.depth}, direction={args.direction})")
    print()

    visited = set()

    def walk(node, depth, direction, indent=0):
        if depth < 0 or node in visited:
            return
        visited.add(node)
        e = entries.get(node, {})
        title = e.get("title", "(unknown)")
        etype = e.get("type", "?")
        print(f"{'  ' * indent}- {node} [{etype}] {title[:60]}")
        if direction in ("out", "both"):
            for tgt, rt in out_e.get(node, []):
                print(f"{'  ' * (indent + 1)}─[{rt}]→")
                walk(tgt, depth - 1, direction, indent + 2)
        if direction in ("in", "both"):
            for src, rt in in_e.get(node, []):
                print(f"{'  ' * (indent + 1)}←[{rt}]─")
                walk(src, depth - 1, direction, indent + 2)

    walk(start, args.depth, args.direction)
    return 0


# ─── show ────────────────────────────────────────────────

def cmd_show(args):
    entries, _, _ = _build_graph()
    e = entries.get(args.id)
    if not e:
        sys.exit(f"[ERROR] {args.id} 없음")
    print(json.dumps(e, ensure_ascii=False, indent=2))
    return 0


# ─── stats ──────────────────────────────────────────────

def cmd_stats(args):
    entries, _, _ = _build_graph()
    by_type = {}
    for e in entries.values():
        t = e.get("type", "?")
        by_type[t] = by_type.get(t, 0) + 1
    print(f"\nWork Memory Stats — {workmem_root()}")
    print(f"  총 entry: {len(entries)}\n")
    for t in sorted(by_type):
        print(f"  {t:<22} {by_type[t]}")
    return 0


# ─── reindex (zvec) ─────────────────────────────────────

def cmd_reindex(args):
    import subprocess

    candidates = [
        Path.home() / ".claude" / "skills" / "simple-knowledge-zvec" / "scripts" / "simple_kb.py",
    ]
    simple_kb = next((p for p in candidates if p.exists()), None)
    if not simple_kb:
        sys.exit("[ERROR] simple_kb.py 를 찾을 수 없음. simple-knowledge-zvec 스킬 설치 필요.")

    kb_path = workmem_root() / ".zvec"
    print(f"▶ zvec 인덱스 위치: {kb_path}")

    # init (없을 때만)
    if not kb_path.exists():
        print("▶ init...")
        subprocess.run(
            ["python3", str(simple_kb), "init", "--path", str(kb_path), "--dimension", "384"],
            check=False,
        )

    print(f"▶ ingest: {workmem_root()}")
    result = subprocess.run(
        ["python3", str(simple_kb), "add",
         "--path", str(kb_path),
         "--input", str(workmem_root()),
         "--recursive",
         "--embedder", "hash"],
        capture_output=False,
    )
    if result.returncode != 0:
        print("[ERROR] reindex 실패", file=sys.stderr)
        return result.returncode
    print("✓ reindex 완료")
    return 0


# ─── main ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Work Memory CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="새 entry 생성")
    p_new.add_argument("type", choices=list(TYPE_PREFIX.keys()))
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--text")
    p_new.add_argument("--tags", help="comma-separated")
    p_new.add_argument("--module", help="관련 모듈 id")
    p_new.add_argument("--author", default="agent")
    p_new.add_argument("--related", action="append", help="<target_id>:<relation_type> (반복 가능)")
    p_new.add_argument("--print", action="store_true", help="생성된 entry 출력")
    p_new.set_defaults(func=cmd_new)

    p_val = sub.add_parser("validate", help="단일 파일 또는 디렉토리 검증")
    p_val.add_argument("path", help="파일 또는 디렉토리")
    p_val.set_defaults(func=cmd_validate)

    p_search = sub.add_parser("search", help="zvec 시맨틱 검색")
    p_search.add_argument("query")
    p_search.add_argument("--type", help="filter by type (현재 미구현, zvec 측 필터 사용)")
    p_search.add_argument("--tag", help="tag 필터")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.set_defaults(func=cmd_search)

    p_graph = sub.add_parser("graph", help="relations 그래프 traversal")
    p_graph.add_argument("id", help="시작 entry id")
    p_graph.add_argument("--depth", type=int, default=3)
    p_graph.add_argument("--direction", choices=["in", "out", "both"], default="both")
    p_graph.set_defaults(func=cmd_graph)

    p_show = sub.add_parser("show", help="단일 entry 조회")
    p_show.add_argument("id")
    p_show.set_defaults(func=cmd_show)

    p_stats = sub.add_parser("stats", help="통계")
    p_stats.set_defaults(func=cmd_stats)

    p_rei = sub.add_parser("reindex", help="zvec 인덱스 재빌드")
    p_rei.set_defaults(func=cmd_reindex)

    args = parser.parse_args()
    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
