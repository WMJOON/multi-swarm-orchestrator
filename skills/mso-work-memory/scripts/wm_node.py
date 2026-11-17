#!/usr/bin/env python3
"""
wm_node.py — Work Memory CLI

사용법:
  wm_node.py new <type> --description "..." [--content "..."] [--node NODE] --scope S [--component C] [--tags a,b] [--related ID:rel-type]
  wm_node.py edit <id> [--description D] [--content C] [--scope S ...] [--meta k=v ...]   # 기존 기록을 제자리에서 고친다
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

대상 저장소 선택 (모든 하위 명령에서, 위치 무관):
  --repo <경로>        다른 MSO 저장소(루트 또는 work-memory 디렉토리)의 work-memory 를 대상으로 한다
  --repo-name <이름>   linked-repos.yaml(또는 .gitmodules 자동 발견)에 등록된 이름으로 지정한다
  둘 다 WORKMEM_DIR 보다 우선하며, 대상 저장소의 schema.yaml 로 어휘와 검증을 한다.
  등록부 해석은 wm_repos.py 참고.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wm_repos  # noqa: E402
import wm_metadata  # noqa: E402
import wm_store  # noqa: E402


def _consume_repo_args(argv):
    """--repo/--repo-name 을 argv 어디에 있든 꺼내 WORKMEM_DIR 로 반영한다.
    어휘(_load_vocab)가 import 시점에 WORKMEM_DIR 을 읽으므로 그보다 먼저 호출해야 한다."""
    repo = name = None
    out, i = [], 0
    while i < len(argv):
        a = argv[i]
        for flag in ("--repo", "--repo-name"):
            if a == flag and i + 1 < len(argv):
                v = argv[i + 1]; i += 1
                if flag == "--repo": repo = v
                else: name = v
                break
            if a.startswith(flag + "="):
                v = a.split("=", 1)[1]
                if flag == "--repo": repo = v
                else: name = v
                break
        else:
            out.append(a)
        i += 1
    if repo:
        p = Path(repo).expanduser().resolve()
        wm = p if (p / "schema.yaml").is_file() else p / "agent-context" / "work-memory"
        if not (wm / "schema.yaml").is_file():
            sys.exit(f"--repo: work-memory(schema.yaml)를 찾지 못했습니다: {wm}")
        os.environ["WORKMEM_DIR"] = str(wm)
    elif name:
        wm = wm_repos.find_workmem(wm_repos.project_root(), name)
        if wm is None:
            sys.exit(f"--repo-name: 등록된 연관 저장소가 없습니다: {name} (linked-repos.yaml 또는 .gitmodules 확인)")
        os.environ["WORKMEM_DIR"] = str(wm)
    return out


sys.argv[1:] = _consume_repo_args(sys.argv[1:])

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

REQUIRED_FIELDS = ["id", "type", "description", "content", "tags", "created_at"]  # 스코프 불변
# v0.16.0 (schema v1.4.0): title→description, text→content. 읽을 때는 옛 필드를 폴백으로 인정한다.
FIELD_FALLBACK = {"description": "title", "content": "text"}
DESCRIPTION_MAX = 200  # 코드포인트 기준. SHACL sh:maxLength 와 같은 값을 유지한다.
# 런타임 로그(auditlog/worklog)는 필드명을 바꾸지 않으므로 길이 상한도 적용하지 않는다.
_LENGTH_EXEMPT_TYPES = ("auditlog", "worklog")


def field_value(entry, field):
    """description/content 를 폴백(title/text)과 함께 읽는다."""
    value = entry.get(field)
    if not value and field in FIELD_FALLBACK:
        value = entry.get(FIELD_FALLBACK[field])
    return value
# list[str] 로 규정된 필드는 '비어 있음'이 아니라 '타입'으로 검사한다. 빈 tags 는
# 스키마상 유효한 list[str] 이며, truthiness 로 보면 wm_node.py new 가 만든 entry 가
# 자기 validate 를 통과하지 못한다(IN-0004).
LIST_REQUIRED_FIELDS = {"tags"}

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
    큐레이션(track/insight/release) = <dir>/<type>.nt   (N-Triples 정본, v0.16.0 — wm_store.py),
    auditlog/worklog               = <dir>/<id>.jsonl  (런타임 로그 — JSONL 유지)."""
    parent = workmem_root() / TYPE_DIR[entry_type]
    if entry_type in _TIME_SERIES_TYPES:
        return parent / f"{entry_id}.jsonl"
    return parent / f"{entry_type}.nt"


# ── ID 형식 (v0.16.0, schema v1.4.0) ─────────────────────────────────────────
# 시퀀스 id(`UD-0012`)는 두 가지 문제가 있었다: (1) 최대 번호 스캔이라 두 머신·세션이 동기화 전에 기록하면 같은 번호가
# 생기고, (2) 정규식이 4자리만 매칭해 9999 를 넘으면 같은 id 가 다시 나온다.
# 새 id 는 `<PREFIX>-<생성 시각의 epoch 밀리초를 12자리 소문자 hex>` 다 (예: UD-019a3c5e4f21).
#   - 무작위가 없다: id 자체가 "언제 발생했는지"를 담는다(id_time 으로 복원).
#   - 12자리 hex 는 서기 10889년까지 표현한다.
#   - 같은 밀리초 충돌은 기존 id 와 겹치면 +1ms 로 비켜 간다(같은 파일 안에서는 반드시 유일).
#   - 옛 십진 4자리 id(`UD-0012`)는 hex 문자열의 부분집합이라 그대로 유효하다. 섞여도 읽힌다.
ID_HEX_WIDTH = 12


def id_time(entry_id: str):
    """hex 밀리초 id 에서 생성 시각(UTC datetime)을 복원한다. 옛 십진 id 나 형식이 다르면 None."""
    m = re.match(r"^[A-Z]{2,}-([0-9a-f]{12})$", entry_id or "")
    if not m:
        return None
    return dt.datetime.fromtimestamp(int(m.group(1), 16) / 1000, tz=dt.timezone.utc)


def _existing_ids(entry_type: str) -> set:
    """해당 타입의 id 들 (밀리초 충돌 회피용). 이행 전 `.jsonl` 과 새 `.nt` 를 모두 본다."""
    ids = set(wm_store.nt_entry_ids(entry_file(entry_type, "")))
    legacy = entry_file(entry_type, "").with_suffix(".jsonl")
    if legacy.is_file():
        for line in legacy.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("id"):
                ids.add(obj["id"])
    return ids


def next_id(entry_type: str) -> str:
    prefix = TYPE_PREFIX[entry_type]
    now = dt.datetime.now(dt.timezone.utc)
    if entry_type in _TIME_SERIES_TYPES:
        # 시각 기반 id (런타임 로그 — 형식 유지)
        return f"{prefix}-{now.strftime('%Y%m%d-%H%M%S')}"
    ms = int(now.timestamp() * 1000)
    taken = _existing_ids(entry_type)
    while f"{prefix}-{ms:0{ID_HEX_WIDTH}x}" in taken:
        ms += 1
    return f"{prefix}-{ms:0{ID_HEX_WIDTH}x}"


# ─── new ─────────────────────────────────────────────────

# --meta 는 semver("0.10.0")·식별자를 문자열로 보존해야 하므로 값을 JSON 파싱하지
# 않는다. bool/null 만 예외로 변환한다 (schema 의 structural 등이 bool 이라서).
_META_LITERALS = {"true": True, "false": False, "null": None}


def _build_metadata(args) -> dict:
    """metadata 조립 — module(단축) → --metadata(JSON) → --meta(개별) 순으로 덮어쓴다."""
    metadata: dict = {}
    # v0.16.0: module → component(구성요소 이름, 문자열). `--module` 은 deprecated 별칭이다.
    # `module` metadata 는 이제 스캐폴드 index 의 module id 를 뜻하며 --in-module 로 지정한다.
    component = getattr(args, "component", None) or args.module
    if component:
        metadata["component"] = component
    if getattr(args, "in_module", None):
        metadata["module"] = args.in_module
    if getattr(args, "scope", None):
        metadata["scope"] = list(dict.fromkeys(args.scope))  # 대상이 여러 개일 수 있다(최소 1개). 중복 제거, 순서 유지
    if getattr(args, "scope_note", None):
        metadata["scope_note"] = args.scope_note
    if getattr(args, "metadata", None):
        try:
            loaded = json.loads(args.metadata)
        except json.JSONDecodeError as e:
            sys.exit(f"[ERROR] --metadata 가 유효한 JSON 이 아님: {e}")
        if not isinstance(loaded, dict):
            sys.exit('[ERROR] --metadata 는 JSON 객체여야 함 (예: \'{"kind":"release"}\')')
        metadata.update(loaded)
    for pair in (getattr(args, "meta", None) or []):
        if "=" not in pair:
            sys.exit(f"[ERROR] --meta 형식 잘못됨: {pair} (예: kind=release)")
        key, value = pair.split("=", 1)
        metadata[key] = _META_LITERALS[value] if value in _META_LITERALS else value
    return metadata


def cmd_new(args):
    t = args.type
    if t not in TYPE_PREFIX:
        sys.exit(f"[ERROR] 알 수 없는 type: {t}")

    description = args.description
    if args.title:
        print("[WARN] --title 은 deprecated — --description 을 쓰세요 (v0.16.0)", file=sys.stderr)
        description = description or args.title
    content = args.content
    if args.text:
        print("[WARN] --text 는 deprecated — --content 를 쓰세요 (v0.16.0)", file=sys.stderr)
        content = content or args.text
    description = description or "TODO: description"
    if len(description) > DESCRIPTION_MAX and t not in _LENGTH_EXEMPT_TYPES:
        sys.exit(f"[ERROR] description 은 {DESCRIPTION_MAX}자 이하여야 함 (현재 {len(description)}자)")

    new_id = next_id(t)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tags = [s.strip() for s in (args.tags or "").split(",") if s.strip()]
    if args.module:
        print("[WARN] --module 은 deprecated — --component(구성요소 이름) 또는 --in-module(index module id)을 쓰세요 (v0.16.0)", file=sys.stderr)
    for tag_source in (getattr(args, "component", None), args.module):
        if tag_source and tag_source not in tags:
            tags.append(tag_source)

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
    source_path = str(file_path.relative_to(workmem_root().parent.parent)) if workmem_root().parent.parent in file_path.parents else str(file_path)
    runtime = t in _TIME_SERIES_TYPES

    entry = {
        "id": new_id,
        "type": t,
        "description": description,
        "content": content or "TODO: 본문 (markdown 가능)",
        "tags": tags,
        "created_at": now,
        **({"source_path": source_path} if runtime else {}),   # 큐레이션(.nt)은 source_path 를 저장하지 않는다(읽을 때 계산)
        "author": args.author or "agent",
        "relations": relations,
        "metadata": _build_metadata(args),
    }
    if args.node:
        entry["node"] = list(dict.fromkeys(args.node))

    # v0.16.0: 타입별 metadata 명세(references/metadata-spec.yaml). 유도 가능한 값은 기본으로 채운다:
    # reporter/provided_by = author, 새 issue-note 의 status = open. severity 등은 기본값을 만들지 않는다.
    meta = entry["metadata"]
    if t == "issue-note":
        meta.setdefault("reporter", entry["author"])
        meta.setdefault("status", "open")
    elif t == "alternatives-record":
        meta.setdefault("provided_by", entry["author"])
    spec = wm_metadata.load_spec()
    registry = wm_metadata.load_agents(workmem_root(), spec)
    if entry["author"] not in registry:
        print(f"[WARN] 주체 '{entry['author']}' 가 등록되지 않음 — 소속(onBehalfOf) 미상의 SoftwareAgent 로 기록된다. "
              f"<work-memory>/agents.yaml 에 등록하세요(User·SoftwareAgent·BackgroundAgent, onBehalfOf=계정 주인).", file=sys.stderr)
    findings = wm_metadata.check_entry(entry, spec, registry)
    errors = [m for lvl, m in findings if lvl == "error"]
    if errors:
        if not args.allow_incomplete:
            sys.exit("[ERROR] 필수 metadata 가 빠졌거나 값이 올바르지 않음:\n  - " + "\n  - ".join(errors)
                     + "\n  --meta key=value 로 채우거나, 나중에 채울 거면 --allow-incomplete (metadata.needs_review=true 로 표시)")
        meta["needs_review"] = True
        print("[WARN] --allow-incomplete: metadata.needs_review=true 로 기록 — " + "; ".join(errors), file=sys.stderr)

    _warn_stale_hook_copy()
    file_path.parent.mkdir(parents=True, exist_ok=True)  # 검증을 통과한 뒤에만 디렉터리를 만든다
    if not runtime:
        # 큐레이션 기록: N-Triples 블록을 한 번의 write 로 append. 같은 id 가 이미 있으면 skip(중복 append 안전장치).
        if new_id in wm_store.nt_entry_ids(file_path):
            print(f"[WARN] {new_id} 가 이미 {file_path} 에 있음 — append skip")
            return
        wm_store.append_entry(file_path, entry, wm_store.load_spec())
    else:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False))
            f.write("\n")
    print(f"✓ append: {file_path}")
    print(f"  id={new_id}")
    if not tags:
        print("  · tags 없음 — context pack 검색의 태그 교집합 가중치(18×)를 못 받아 "
              "회수되기 어렵다. --tags 로 node id·모듈을 넣어두는 편이 좋다.", file=sys.stderr)
    if args.print:
        print(json.dumps(entry, ensure_ascii=False, indent=2))


# ─── validate ────────────────────────────────────────────

def _load_entries(path: Path):
    """단일 파일 또는 디렉토리에서 모든 entry 를 yield: (src, line_num, entry).
    jsonl 은 줄 번호, `.nt`(큐레이션 정본)는 entry id 가 line_num 자리에 온다."""
    if path.is_file():
        if path.suffix == ".nt":
            entries, problems = wm_store.load_nt_entries(path, wm_store.load_spec())
            for number, message in problems:
                yield path, number, {"_parse_error": message, "_line": ""}
            for entry in entries:
                yield path, entry.get("id"), entry
            return
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
    for jf in wm_store.order_paths([*path.rglob("*.jsonl"), *path.rglob("*.nt")]):
        # dot-디렉토리(.migration-archive, .zvec 등 메타/아카이브)는 read 대상에서 제외
        if any(p.startswith(".") for p in jf.relative_to(path).parts[:-1]):
            continue
        yield from _load_entries(jf)


def _warn_stale_hook_copy() -> None:
    """프로젝트에 복사된 훅이 구버전(wm_context.py 는 있는데 wm_store.py 가 없음)이면 알린다.
    그 훅은 새로 쓴 `.nt` 기록을 읽지 못해 주입이 조용히 비게 된다."""
    root = workmem_root()
    if root.name != "work-memory" or root.parent.name != "agent-context":
        return
    project = root.parent.parent
    for rel in (".claude/scripts", ".codex/scripts"):
        scripts = project / rel
        if (scripts / "wm_context.py").is_file() and not (scripts / "wm_store.py").is_file():
            print(f"[WARN] {rel} 의 훅 사본이 구버전이다(wm_store.py 없음) — 새로 쓴 .nt 기록이 훅에 보이지 않는다. "
                  f"`init.py --hook {project}` 로 훅 사본을 갱신하세요.", file=sys.stderr)


def _locate_for_write(entry_id: str, label: str = "entry"):
    """쓰기 명령(relate/map-node/edit)이 고칠 기록의 위치를 하나로 확정한다.
    같은 id 가 둘 이상의 파일에 있거나(iCloud 충돌 복제본·병합 흔적) `.nt` 에 단일값 필드가 충돌하면 거부한다 —
    어느 쪽을 고칠지 모호하고, 고쳐 쓰면 충돌한 값 하나가 조용히 사라진다."""
    hits = [(src, line, entry) for src, line, entry in _load_entries(workmem_root())
            if "_parse_error" not in entry and entry.get("id") == entry_id]
    if not hits:
        sys.exit(f"[ERROR] {label} 를 찾지 못함: {entry_id}")
    files = sorted({str(h[0]) for h in hits})
    if len(files) > 1:
        sys.exit(f"[ERROR] {entry_id} 가 여러 파일에 있음 — 어느 쪽을 고칠지 알 수 없다(iCloud 충돌 복제본이면 정리 후 다시):\n  - "
                 + "\n  - ".join(files))
    src, line, entry = hits[0]
    if src.suffix == ".nt" and any(eid == entry_id for eid, _field in wm_store.duplicate_single_valued(src)):
        sys.exit(f"[ERROR] [DUP-FIELD] {entry_id} 에 단일값 필드가 둘 이상 있음({src.name}) — 병합·충돌 흔적을 먼저 정리해야 한다. "
                 "고쳐 쓰면 충돌한 값이 사라진다.")
    _warn_stale_hook_copy()
    return src, line, entry


def _save_entry(src: Path, line_num, entry: dict) -> None:
    """찾은 위치(src, line_num)의 기록을 제자리에서 갱신한다. jsonl 은 줄 교체, `.nt` 는 블록 교체(원자적)."""
    if src.suffix == ".nt":
        if not wm_store.replace_entry(src, entry, wm_store.load_spec()):
            sys.exit(f"[ERROR] {src.name} 에서 {entry.get('id')} 를 찾지 못함")
        return
    lines = src.read_text(encoding="utf-8").splitlines()
    lines[line_num - 1] = json.dumps(entry, ensure_ascii=False)
    src.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─── relate ──────────────────────────────────────────────


def cmd_relate(args):
    """기존 entry 에 relation 을 추가한다 (라이프사이클 엣지 확정).

    AR→UD(followed-by), IN→TS(resolved-by), *→RN(released-in/verified-in/
    invalidated-by) 처럼 target 이 나중에 생기는 엣지는 사후에만 달 수 있다.
    append-only 는 '일어난 일(entry)을 지우거나 고쳐 쓰지 않는다'는 뜻이고,
    relations 는 그 entry 의 현재 그래프 상태다 — 그래서 줄을 갱신한다.
    (중복 entry 를 append 하면 reader 의 first-seen-wins dedup 이 옛 줄을
    돌려주므로 애초에 동작하지 않는다.)
    """
    if args.type not in ALLOWED_RELATIONS:
        print(f"[WARN] 알 수 없는 relation: {args.type}", file=sys.stderr)

    known_ids = {entry.get("id") for _s, _l, entry in _load_entries(workmem_root()) if "_parse_error" not in entry}
    src, line_num, entry = _locate_for_write(args.source, "source entry")
    if args.target not in known_ids:
        print(f"[WARN] target entry 를 찾지 못함: {args.target} (dangling edge)", file=sys.stderr)

    relations = entry.setdefault("relations", [])
    if any(r.get("type") == args.type and r.get("target") == args.target for r in relations):
        print(f"이미 존재: {args.source} ──{args.type}──> {args.target}")
        return 0
    relations.append({"type": args.type, "target": args.target})

    _save_entry(src, line_num, entry)
    print(f"✓ {args.source} ──{args.type}──> {args.target}  ({src.name}:{line_num})")
    return 0


def cmd_map_node(args):
    """기존 entry 에 연관 workflow node(related 매핑)를 붙이거나 뗀다.

    `relate` 와 같은 이유로 줄을 제자리에서 갱신한다: node 는 그 entry 의 현재 매핑 상태이고,
    매핑은 기록 이후에 알게 되는 경우가 많다. 이행 스크립트는 매핑을 만들지 않으므로 기존 기록은 이 명령으로 붙인다.
    """
    src, line_num, entry = _locate_for_write(args.id)
    current = entry.get("node") if isinstance(entry.get("node"), list) else []
    if args.remove:
        updated = [n for n in current if n not in set(args.node)]
    else:
        updated = list(dict.fromkeys([*current, *args.node]))
    if updated == current:
        print(f"변경 없음: {args.id} node={current}")
        return 0
    if updated:
        entry["node"] = updated
    else:
        entry.pop("node", None)
    _save_entry(src, line_num, entry)
    print(f"✓ {args.id} node={updated}  ({src.name}:{line_num})")
    return 0


def cmd_edit(args):
    """기존 기록의 내용 필드를 제자리에서 고친다 (description, content, tags, scope, 기타 metadata).

    N-Triples 는 손으로 고치기 어려우므로 편집도 스크립트로 한다. id·type·created_at·relations 는 바꾸지 않는다
    (relations 는 `relate`, node 는 `map-node`). 편집 뒤 명세로 다시 검사해 오류가 없으면 needs_review 표시를 지운다 —
    이행이 붙인 needs_review 기록을 보정하는 경로다.
    """
    src, line_num, entry = _locate_for_write(args.id)
    # append-only 보호: description/content(이력)는 needs_review 기록(보정 경로)에서만 고친다. 확정된 기록의 이력을 고쳐 쓰려면
    # 명시적으로 --allow-rewrite 를 준다. scope·scope_note·component·module·tags·metadata(상태성 필드)는 제한이 없다.
    rewrites_history = args.description is not None or args.content is not None
    reviewing = isinstance(entry.get("metadata"), dict) and entry["metadata"].get("needs_review") is True
    if rewrites_history and not reviewing:
        if not args.allow_rewrite:
            sys.exit(f"[ERROR] {args.id} 는 확정된 기록이라 description/content 를 고칠 수 없다(append-only). "
                     "needs_review 기록만 보정할 수 있다 — 꼭 고쳐 써야 하면 --allow-rewrite (git 이력에 남는다).")
        print(f"[WARN] --allow-rewrite: 확정된 기록 {args.id} 의 description/content(이력)를 고쳐 쓴다 — 이전 값은 git 이력에만 남는다", file=sys.stderr)
    before = json.dumps(entry, ensure_ascii=False, sort_keys=True)

    if args.description is not None:
        if len(args.description) > DESCRIPTION_MAX and entry.get("type") not in _LENGTH_EXEMPT_TYPES:
            sys.exit(f"[ERROR] description 은 {DESCRIPTION_MAX}자 이하여야 함 (현재 {len(args.description)}자)")
        entry.pop("title", None)
        entry["description"] = args.description
    if args.content is not None:
        entry.pop("text", None)
        entry["content"] = args.content
    if args.tags is not None:
        entry["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    metadata = dict(entry["metadata"]) if isinstance(entry.get("metadata"), dict) else {}
    if args.scope:
        metadata["scope"] = list(dict.fromkeys(args.scope))
    if args.scope_note is not None:
        metadata["scope_note"] = args.scope_note
    if args.component is not None:
        metadata["component"] = args.component
    if args.in_module is not None:
        metadata["module"] = args.in_module
    if args.metadata:
        try:
            loaded = json.loads(args.metadata)
        except json.JSONDecodeError as e:
            sys.exit(f"[ERROR] --metadata 가 유효한 JSON 이 아님: {e}")
        if not isinstance(loaded, dict):
            sys.exit("[ERROR] --metadata 는 JSON 객체여야 함")
        metadata.update(loaded)
    for pair in (args.meta or []):
        if "=" not in pair:
            sys.exit(f"[ERROR] --meta 형식 잘못됨: {pair} (예: severity=minor)")
        key, value = pair.split("=", 1)
        metadata[key] = _META_LITERALS[value] if value in _META_LITERALS else value
    for key in (args.unset_meta or []):
        metadata.pop(key, None)
    entry["metadata"] = metadata

    spec = wm_metadata.load_spec()
    agents = wm_metadata.load_agents(workmem_root(), spec)
    was_marked = metadata.get("needs_review") is True
    metadata_probe = dict(entry, metadata={k: v for k, v in metadata.items() if k != "needs_review"})
    errors = [m for lvl, m in wm_metadata.check_entry(metadata_probe, spec, agents) if lvl == "error"]
    if was_marked and not errors:
        metadata.pop("needs_review", None)
        print("  · 필수 metadata 가 모두 채워져 needs_review 표시를 지웠다")
    elif errors and not was_marked and wm_metadata.is_new_record(entry, spec):
        sys.exit("[ERROR] 편집 결과가 명세에 맞지 않음:\n  - " + "\n  - ".join(errors))

    if json.dumps(entry, ensure_ascii=False, sort_keys=True) == before:
        print(f"변경 없음: {args.id}")
        return 0
    _save_entry(src, line_num, entry)
    print(f"✓ edit {args.id}  ({src.name})")
    return 0


def cmd_validate(args):
    target = Path(args.path).resolve()
    if not target.exists():
        sys.exit(f"[ERROR] 경로 없음: {args.path}")

    issues = []
    warnings = []
    total = 0
    seen_ids = {}
    spec = wm_metadata.load_spec()
    agents = wm_metadata.load_agents(workmem_root(), spec)

    for src, line_num, entry in _load_entries(target):
        total += 1
        ctx = f"{src.name}:{line_num}"

        if "_parse_error" in entry:
            issues.append(f"[PARSE] {ctx}: {entry['_parse_error']}")
            continue

        for field in REQUIRED_FIELDS:
            value = field_value(entry, field)
            if field in LIST_REQUIRED_FIELDS:
                if not isinstance(value, list):
                    issues.append(f"[TYPE] {ctx}: {field} 는 list 여야 함")
            elif not value:
                issues.append(f"[MISSING] {ctx}: {field}")

        desc = entry.get("description")
        if isinstance(desc, str) and entry.get("type") not in _LENGTH_EXEMPT_TYPES and len(desc) > DESCRIPTION_MAX:
            issues.append(f"[LEN] {ctx}: description {len(desc)}자 > {DESCRIPTION_MAX}자")
        nodes = entry.get("node")
        if nodes is not None and not (isinstance(nodes, list) and all(isinstance(n, str) and n for n in nodes)):
            issues.append(f"[TYPE] {ctx}: node 는 list[str] 여야 함")

        eid = entry.get("id")
        if eid:
            if eid in seen_ids:
                issues.append(f"[DUP-ID] {eid} ({ctx} ↔ {seen_ids[eid]})")
            seen_ids[eid] = ctx

        for level, message in wm_metadata.check_entry(entry, spec, agents):
            (issues if level == "error" else warnings).append(f"[META] {ctx}: {message}")

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

    # `.nt` 정본: 같은 subject 에 단일값 필드가 둘 이상이면(병합·iCloud 충돌 복제본의 흔적) 조용히 합치지 않고 오류로 보고한다.
    nt_files = [target] if (target.is_file() and target.suffix == ".nt") else (
        [p for p in sorted(target.rglob("*.nt")) if not any(part.startswith(".") for part in p.relative_to(target).parts[:-1])]
        if target.is_dir() else [])
    for nt in nt_files:
        for entry_id, field in wm_store.duplicate_single_valued(nt):
            issues.append(f"[DUP-FIELD] {nt.name}: {entry_id} 의 {field} 가 둘 이상 (병합·충돌 복제본 확인)")

    print(f"\n검증: {target}")
    print(f"  총 entry: {total}, 이슈: {len(issues)}" + (f", 경고: {len(warnings)}" if warnings else "") + "\n")
    for w in warnings:
        print(f"  ⚠ {w}")
    if warnings:
        print()
    if not issues:
        print("  ✓ 모든 entry 가 스키마를 준수합니다." + (" (경고는 옛 기록·needs_review 기록의 metadata 누락)" if warnings else ""))
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

    # simple_kb.py 위치 탐색 — mso-work-memory 에 colocated된 버전을 우선 사용
    # (외부 simple-knowledge-zvec 스킬 의존은 폐지, IN-0002/2026-08-26 재구성)
    candidates = [
        Path(__file__).parent / "simple_kb.py",
        Path.home() / ".claude" / "skills" / "simple-knowledge-zvec" / "scripts" / "simple_kb.py",
        Path(__file__).parent.parent.parent / "simple-knowledge-zvec" / "scripts" / "simple_kb.py",
    ]
    simple_kb = next((p for p in candidates if p.exists()), None)
    if not simple_kb:
        sys.exit("[ERROR] simple_kb.py 를 찾을 수 없음 (mso-work-memory/scripts/simple_kb.py 기대).")

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
    """전체 entry 를 읽어 id → entry, id → outgoing, id → incoming 맵 구성 (jsonl + `.nt`)."""
    root = workmem_root()
    entries_by_id = {}
    out_edges = {}  # id → [(target, type)]
    in_edges = {}   # id → [(source, type)]

    for jf, line_num, e in _load_entries(root):
        if "_parse_error" in e:
            print(f"[WARN] {jf.name}:{line_num} 읽을 수 없는 줄 skip: {e['_parse_error']}", file=sys.stderr)
            continue
        eid = e.get("id")
        if not eid:
            continue
        entries_by_id[eid] = e
        rels = e.get("relations") or []
        if not isinstance(rels, list):
            print(f"[WARN] {eid}: relations 가 list[{{type,target}}] 형식이 아님"
                  f"({type(rels).__name__}) — 이 entry 의 relations 는 건너뜀", file=sys.stderr)
            continue
        for rel in rels:
            if not isinstance(rel, dict):
                print(f"[WARN] {eid}: relations 항목이 dict 가 아님"
                      f"({type(rel).__name__}) — 건너뜀", file=sys.stderr)
                continue
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
        title = field_value(e, "description") or "(unknown)"
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
    if getattr(args, "nt", False):
        print("\n".join(wm_store.block_lines(e, wm_store.load_spec())))
        return 0
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
        Path(__file__).parent / "simple_kb.py",
        Path.home() / ".claude" / "skills" / "simple-knowledge-zvec" / "scripts" / "simple_kb.py",
    ]
    simple_kb = next((p for p in candidates if p.exists()), None)
    if not simple_kb:
        sys.exit("[ERROR] simple_kb.py 를 찾을 수 없음 (mso-work-memory/scripts/simple_kb.py 기대).")

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
    # embedder=multilingual: 실 시맨틱 임베딩(sentence-transformers, 다국어/한국어 지원).
    # 모델 로드 실패 시 simple_kb.py 자체가 hash(문자 n-gram 해싱)로 자동 폴백함.
    result = subprocess.run(
        ["python3", str(simple_kb), "add",
         "--path", str(kb_path),
         "--input", str(workmem_root()),
         "--recursive",
         "--embedder", "multilingual"],
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
    p_new.add_argument("--description", help=f"본문을 펼칠지 판단하는 문구 (최대 {DESCRIPTION_MAX}자)")
    p_new.add_argument("--content", help="본문 (markdown 가능)")
    p_new.add_argument("--title", help="[deprecated] --description 의 별칭")
    p_new.add_argument("--text", help="[deprecated] --content 의 별칭")
    p_new.add_argument("--node", action="append", help="연결할 workflow node id (반복 가능, related 매핑)")
    p_new.add_argument("--tags", help="comma-separated")
    p_new.add_argument("--scope", action="append", choices=sorted(wm_metadata.vocab_values(wm_metadata.load_spec(), "scope")),
                       help="이 기록이 적용되는 대상의 층 (필수, 최소 1개, 여러 번 지정 가능 — 기록마다 다르다)")
    p_new.add_argument("--scope-note", dest="scope_note", help="적용 범위 보충 서술 (skos:scopeNote)")
    p_new.add_argument("--component", help="구성요소 이름 (스킬·패키지 등, 문자열). 태그에도 추가된다")
    p_new.add_argument("--in-module", dest="in_module", help="스캐폴드 index 의 module id (index 와 연결될 때만)")
    p_new.add_argument("--module", help="[deprecated] --component 의 별칭")
    p_new.add_argument("--author", default="agent")
    p_new.add_argument("--related", action="append", help="<target_id>:<relation_type> (반복 가능)")
    p_new.add_argument("--metadata", help='타입별 metadata JSON 객체 (예: \'{"kind":"release","version":"0.10.0"}\')')
    p_new.add_argument("--meta", action="append", default=[],
                       help="metadata 를 key=value 로 지정 (반복 가능). true/false/null 만 JSON 리터럴로 "
                            "해석하고 나머지는 문자열 — 리스트/숫자는 --metadata 사용")
    p_new.add_argument("--allow-incomplete", action="store_true",
                       help="필수 metadata 가 비어도 기록 (metadata.needs_review=true 로 표시, validate 에서 경고로 낮춤)")
    p_new.add_argument("--print", action="store_true", help="생성된 entry 출력")
    p_new.set_defaults(func=cmd_new)

    p_rel = sub.add_parser("relate", help="기존 entry 에 relation 추가 (AR→UD, IN→TS, *→RN 등)")
    p_rel.add_argument("source", help="relation 을 붙일 entry id")
    p_rel.add_argument("type", help=f"relation type ({', '.join(sorted(ALLOWED_RELATIONS))})")
    p_rel.add_argument("target", help="대상 entry id")
    p_rel.set_defaults(func=cmd_relate)

    p_edit = sub.add_parser("edit", help="기존 기록의 description/content/tags/scope/metadata 를 제자리에서 고친다")
    p_edit.add_argument("id")
    p_edit.add_argument("--description", help="확정된 기록은 --allow-rewrite 없이는 거부된다(needs_review 기록은 허용)")
    p_edit.add_argument("--content", help="확정된 기록은 --allow-rewrite 없이는 거부된다(needs_review 기록은 허용)")
    p_edit.add_argument("--allow-rewrite", action="store_true", help="확정된 기록의 description/content(이력)를 고쳐 쓴다")
    p_edit.add_argument("--tags", help="comma-separated (전체 교체)")
    p_edit.add_argument("--scope", action="append", choices=sorted(wm_metadata.vocab_values(wm_metadata.load_spec(), "scope")),
                        help="scope 전체 교체 (반복 가능)")
    p_edit.add_argument("--scope-note", dest="scope_note")
    p_edit.add_argument("--component")
    p_edit.add_argument("--in-module", dest="in_module")
    p_edit.add_argument("--metadata", help="metadata JSON 객체 (병합)")
    p_edit.add_argument("--meta", action="append", default=[], help="key=value (반복 가능)")
    p_edit.add_argument("--unset-meta", dest="unset_meta", action="append", help="metadata 키 제거 (반복 가능)")
    p_edit.set_defaults(func=cmd_edit)

    p_map = sub.add_parser("map-node", help="기존 entry 에 연관 workflow node 를 붙이거나 뗀다 (related 매핑)")
    p_map.add_argument("id", help="entry id")
    p_map.add_argument("--node", action="append", required=True, help="workflow node id (반복 가능)")
    p_map.add_argument("--remove", action="store_true", help="붙이는 대신 뗀다")
    p_map.set_defaults(func=cmd_map_node)

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
    p_show.add_argument("--nt", action="store_true", help="JSON 대신 N-Triples 블록을 출력")
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
