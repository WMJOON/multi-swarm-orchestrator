#!/usr/bin/env python3
"""wm_release.py — release-note(RN) derived view CLI (schema v1.3.0).

상태(current/rollback 캐스케이드)는 저장하지 않는다 — 이 스크립트가 JSONL 에서
매번 도출한다 (UD-0012: "상태는 이벤트+엣지에서 도출한다").

  current   현재 릴리스 RN 도출 (rollback 이 아니고 rolls-back 대상도 아닌 RN 중 최신)
  validity  entry 의 verified-in / invalidated-by 상태 (--id 로 단일 조회)
  context   session hook 주입용 컴팩트 블록 (RN 이 없으면 무출력·exit 0)

의존성 없음 (stdlib only) — copy-form hook 배포를 위해 wm_node.py 와 독립.
WORKMEM_DIR 환경변수(기본 ./agent-context/work-memory)를 루트로 읽는다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

RECORD_DIRS = ("track-record", "release-record", "insight-record")


def workmem_root() -> Path:
    return Path(os.environ.get("WORKMEM_DIR", "./agent-context/work-memory")).resolve()


def load_entries(root: Path) -> dict[str, dict[str, Any]]:
    """curated 영역의 모든 entry 를 {id: entry} 로 로드 (선착 우선)."""
    entries: dict[str, dict[str, Any]] = {}
    for d in RECORD_DIRS:
        base = root / d
        if not base.exists():
            continue
        for f in sorted(base.rglob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(e, dict) and e.get("id") and e["id"] not in entries:
                    entries[e["id"]] = e
    return entries


def _relations(e: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (e.get("relations") or []) if isinstance(r, dict)]


def _release_ts(e: dict[str, Any]) -> str:
    md = e.get("metadata") or {}
    return str(md.get("released_at") or e.get("created_at") or "")


def rolled_back_ids(entries: dict[str, dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for e in entries.values():
        if e.get("type") != "release-note":
            continue
        for r in _relations(e):
            if r.get("type") == "rolls-back" and r.get("target"):
                out.add(str(r["target"]))
    return out


def current_release(entries: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """derived current: kind!=rollback 이고 rolls-back 대상이 아닌 RN 중 released_at 최신."""
    rolled = rolled_back_ids(entries)
    candidates = [
        e for e in entries.values()
        if e.get("type") == "release-note"
        and (e.get("metadata") or {}).get("kind", "release") != "rollback"
        and e["id"] not in rolled
    ]
    if not candidates:
        return None
    return max(candidates, key=_release_ts)


def validity_edges(entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """verified-in / invalidated-by 엣지 전수 + 파생 상태.

    status: active      — target RN 이 롤백되지 않음 (무효화/검증 유효)
            suspended   — target RN 이 롤백됨 (invalidated-by 는 '재유효 후보',
                          verified-in 은 '검증 근거 상실')
    """
    rolled = rolled_back_ids(entries)
    edges = []
    for e in entries.values():
        for r in _relations(e):
            rt = r.get("type")
            if rt not in ("verified-in", "invalidated-by"):
                continue
            target = str(r.get("target") or "")
            edges.append({
                "source": e["id"],
                "source_type": e.get("type"),
                "title": e.get("title", ""),
                "relation": rt,
                "target": target,
                "status": "suspended" if target in rolled else "active",
            })
    return edges


def cmd_current(entries: dict[str, dict[str, Any]], as_json: bool) -> int:
    cur = current_release(entries)
    if cur is None:
        if as_json:
            print("null")
        else:
            print("(release-note 없음 — current 미정의)")
        return 0
    if as_json:
        print(json.dumps(cur, ensure_ascii=False, indent=2))
    else:
        md = cur.get("metadata") or {}
        print(f"{md.get('version', '?')}  ({cur['id']}, released_at={_release_ts(cur)}, scope={md.get('scope', '?')})")
    return 0


def cmd_validity(entries: dict[str, dict[str, Any]], entry_id: str | None, as_json: bool) -> int:
    edges = validity_edges(entries)
    if entry_id:
        edges = [x for x in edges if x["source"] == entry_id]
    if as_json:
        print(json.dumps(edges, ensure_ascii=False, indent=2))
        return 0
    if not edges:
        print("(verified-in/invalidated-by 엣지 없음 — 전부 '유효 추정')")
        return 0
    for x in edges:
        mark = "✗" if x["relation"] == "invalidated-by" else "✓"
        note = "" if x["status"] == "active" else "  [suspended — target RN 롤백됨]"
        print(f"{mark} {x['source']} ──{x['relation']}──> {x['target']}{note}  {x['title']}")
    return 0


def cmd_context(entries: dict[str, dict[str, Any]]) -> int:
    """hook 주입용 컴팩트 블록. RN 이 하나도 없으면 무출력 (프로젝트가 RN 미사용)."""
    if not any(e.get("type") == "release-note" for e in entries.values()):
        return 0
    cur = current_release(entries)
    lines = ["[work-memory release]"]
    if cur is None:
        lines.append("  current: 미정의 (모든 release RN 이 롤백됨 — 상태 확인 필요)")
    else:
        md = cur.get("metadata") or {}
        label = md.get("version") or cur.get("title") or "?"
        lines.append(f"  current: {label} ({cur['id']}, {_release_ts(cur)})")
    edges = validity_edges(entries)
    inv_active = [x for x in edges if x["relation"] == "invalidated-by" and x["status"] == "active"]
    revalid = [x for x in edges if x["relation"] == "invalidated-by" and x["status"] == "suspended"]
    if inv_active:
        lines.append("  더 이상 유효하지 않은 기록 (invalidated, active):")
        for x in inv_active[:10]:
            lines.append(f"    ✗ {x['source']} ← {x['target']}  {x['title']}")
        if len(inv_active) > 10:
            lines.append(f"    … 외 {len(inv_active) - 10}건 (wm_release.py validity 로 전체 조회)")
    if revalid:
        lines.append("  재유효 후보 (target RN 롤백됨 — 재검토 필요):")
        for x in revalid[:5]:
            lines.append(f"    ? {x['source']} ← {x['target']}  {x['title']}")
    print("\n".join(lines))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="release-note derived view (current/validity/context)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_cur = sub.add_parser("current", help="현재 릴리스 RN 도출")
    p_cur.add_argument("--json", action="store_true")
    p_val = sub.add_parser("validity", help="verified-in/invalidated-by 상태 조회")
    p_val.add_argument("--id", help="단일 entry id 로 필터")
    p_val.add_argument("--json", action="store_true")
    sub.add_parser("context", help="session hook 주입용 블록 (RN 없으면 무출력)")
    args = ap.parse_args()

    root = workmem_root()
    if not root.exists():
        # hook 경유 호출을 고려해 조용히 성공 종료
        return 0
    entries = load_entries(root)
    if args.cmd == "current":
        return cmd_current(entries, args.json)
    if args.cmd == "validity":
        return cmd_validity(entries, args.id, args.json)
    if args.cmd == "context":
        return cmd_context(entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
