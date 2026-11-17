#!/usr/bin/env python3
"""wm_migrate_store.py — 큐레이션 JSONL 기록을 N-Triples(.nt) 정본으로 옮긴다 (MSO v0.16.0, schema v1.4.0).

대상: track-record / insight-record / release-record 의 `<type>.jsonl` (auditlog·worklog 런타임 로그는 JSONL 로 남는다).
한 번에 세 가지를 한다:
  1. 필드 이행   title/text → description/content            (wm_migrate_fields.migrate_entry — 결정적, LLM 없음)
  2. metadata 이행 module → component, 자유 서술 scope → scope_note (옛 기록만)
  3. 저장 형식   JSONL → N-Triples (wm_store.py)

안전 장치:
  - 기본은 dry-run(변경 없음). --apply 일 때만 쓴다.
  - 쓰기 전에 모든 기록이 손실 없이 왕복되는지 검증한다(기록 → triple → 기록 이 고정점이어야 함). 하나라도 어긋나면 중단한다.
  - 같은 타입에 `.nt` 가 이미 있으면(승격 후 새 기록이 먼저 생긴 경우) id 가 겹치지 않을 때 옛 기록을 앞에 두고 합친다. id 가 겹치면 그 타입은 건너뛰고 오류로 보고한다.
  - 원본 `.jsonl` 은 <root>/.migration-archive/store-<시각>/ 로 옮긴다(dot-dir 은 reader 가 건너뛴다 → DUP-ID 없음).
  - 멱등: 이행 뒤에는 대상 `.jsonl` 이 없으므로 다시 실행해도 할 일이 없다.
  - iCloud 충돌 복제본(`* 2.jsonl`)은 건너뛴다. id 가 중복이면 처음 본 것을 쓰고 경고한다.
  - `.nt` 는 임시 파일에 쓴 뒤 os.replace 한다.

주의: 글로벌 스킬 링크가 v0.15.x 를 가리키는 동안에는 이행하지 말 것 — 그 버전은 `.nt` 를 못 읽는다(기록이 보이지 않는다).
승격(v0.16 배포) 뒤, 각 프로젝트의 훅 사본을 갱신(`init.py --hook`)한 다음 이행한다.

사용법:
  wm_migrate_store.py [--root DIR ...]            # dry-run
  wm_migrate_store.py --apply [--root DIR ...]    # 실제 이행
  wm_migrate_store.py --json                      # 요약을 JSON 으로
종료 코드: 0 정상, 1 건너뛴 타입·왕복 불일치 등 문제 있음.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wm_store  # noqa: E402
import wm_migrate_fields  # noqa: E402

ICLOUD_DUP_RE = re.compile(r"\s\d+(\.[^.]+)?$")


def workmem_root() -> Path:
    return Path(os.environ.get("WORKMEM_DIR", "./agent-context/work-memory")).resolve()


def iter_targets(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirname in wm_store.CURATED_DIRS:
        base = root / dirname
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.jsonl")):
            rel = path.relative_to(root)
            if any(part.startswith(".") for part in rel.parts[:-1]) or ICLOUD_DUP_RE.search(path.name):
                continue
            files.append(path)
    return files


def _normalize(entry: dict[str, Any], spec) -> dict[str, Any]:
    """기록의 저장 형식 정규형(왕복 결과). 이것이 고정점이어야 한다."""
    return wm_store.triples_to_entries(wm_store.entry_to_triples(entry, spec), spec)[0]


def plan_file(path: Path, spec) -> dict[str, Any]:
    """파일 하나의 이행 계획. 기록을 변환하고 왕복을 검증한다."""
    result: dict[str, Any] = {"path": str(path), "entries": [], "skipped": [], "warnings": [], "problems": [],
                              "needs_review": [], "unmapped": 0}
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            result["problems"].append(f"{path.name}:{number}: JSON 파싱 불가 ({exc}) — 이행하지 않음")
            continue
        if not isinstance(obj, dict) or not obj.get("id") or not obj.get("type"):
            result["problems"].append(f"{path.name}:{number}: id/type 없는 줄 — 이행하지 않음")
            continue
        if obj["id"] in seen:
            result["warnings"].append(f"{path.name}:{number}: 중복 id {obj['id']} — 처음 본 것만 이행")
            continue
        seen.add(obj["id"])
        migrated, reasons = wm_migrate_fields.migrate_entry({k: v for k, v in obj.items() if k != "source_path"})
        try:
            normalized = _normalize(migrated, spec)
            again = _normalize(normalized, spec)
        except Exception as exc:  # noqa: BLE001
            result["problems"].append(f"{path.name}:{number}: {obj['id']} 변환 실패 ({exc})")
            continue
        if again != normalized:
            result["problems"].append(f"{path.name}:{number}: {obj['id']} 왕복이 고정점이 아님 — 이행하지 않음")
            continue
        if (migrated.get("metadata") or {}).get("needs_review") is True and not (obj.get("metadata") or {}).get("needs_review"):
            result["needs_review"].append(obj["id"])
        if any(p == wm_store.WM + "unmapped" for _s, p, _o in wm_store.entry_to_triples(migrated, spec)):
            result["unmapped"] += 1
        result["entries"].append(migrated)
        result["reasons"] = result.get("reasons", []) + reasons
    return result


def run(roots: list[Path], apply: bool) -> dict[str, Any]:
    spec = wm_store.load_spec()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary: dict[str, Any] = {"apply": apply, "roots": [str(r) for r in roots], "files": [], "errors": [],
                               "totals": {"files": 0, "entries": 0, "needs_review": 0, "unmapped": 0}}
    for root in roots:
        archive = root / ".migration-archive" / f"store-{stamp}"
        for path in iter_targets(root):
            plan = plan_file(path, spec)
            nt_path = path.with_suffix(".nt")
            item = {"path": str(path), "target": str(nt_path), "entries": len(plan["entries"]),
                    "needs_review": plan["needs_review"], "unmapped": plan["unmapped"],
                    "warnings": plan["warnings"], "problems": plan["problems"], "status": "planned"}
            existing_ids = wm_store.nt_entry_ids(nt_path) if nt_path.exists() else set()
            overlap = sorted(existing_ids & {e["id"] for e in plan["entries"]})
            if overlap:
                item["status"] = "skipped"
                summary["errors"].append(f"{nt_path.name} 와 id 가 겹침: {', '.join(overlap)} — {path.name} 은 이행하지 않음 (중복 정리 후 다시)")
            elif plan["problems"]:
                item["status"] = "blocked"
                summary["errors"].extend(plan["problems"])
            elif apply:
                lines: list[str] = []
                external_seen: set[str] = set()
                for entry in plan["entries"]:
                    for s, p, o in wm_store.entry_to_triples(entry, spec):
                        if s.startswith(wm_store.ID_NS + "external/") and (s in external_seen):
                            continue
                        if s.startswith(wm_store.ID_NS + "external/"):
                            if p == wm_store.WM + "externalValue":
                                external_seen.add(s)
                        lines.append(wm_store.serialize_triple(s, p, o))
                # 승격 후 새 기록이 이미 `.nt` 를 만들었다면 옛 기록을 앞에 두고 합친다(id 가 겹치지 않을 때만 여기까지 온다).
                previous = nt_path.read_text(encoding="utf-8") if nt_path.exists() else ""
                expected_ids = [e["id"] for e in plan["entries"]] + [e["id"] for e in wm_store.load_nt_entries(nt_path, spec)[0]] if previous else [e["id"] for e in plan["entries"]]
                wm_store._atomic_write(nt_path, "\n".join(lines) + "\n" + previous)
                # 쓴 결과를 다시 읽어 검증한 뒤에만 원본을 치운다
                written, bad = wm_store.load_nt_entries(nt_path, spec)
                if bad or [e["id"] for e in written] != expected_ids:
                    if previous:
                        wm_store._atomic_write(nt_path, previous)         # 이전 내용으로 되돌린다
                    else:
                        nt_path.unlink()
                    item["status"] = "blocked"
                    summary["errors"].append(f"{nt_path.name} 검증 실패 — 되돌림, 원본 유지")
                else:
                    dest = archive / path.relative_to(root)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(dest))
                    item["status"] = "migrated"
            summary["files"].append(item)
            if item["status"] in ("planned", "migrated"):
                summary["totals"]["files"] += 1
                summary["totals"]["entries"] += item["entries"]
                summary["totals"]["needs_review"] += len(item["needs_review"])
                summary["totals"]["unmapped"] += item["unmapped"]
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="실제 이행 (기본은 dry-run)")
    ap.add_argument("--root", action="append", default=[], help="work-memory 루트 (반복 가능, 기본 WORKMEM_DIR)")
    ap.add_argument("--json", action="store_true", help="요약을 JSON 으로 출력")
    args = ap.parse_args(argv)
    roots = [Path(r).resolve() for r in args.root] or [workmem_root()]
    missing = [r for r in roots if not r.exists()]
    if missing:
        print(f"[ERROR] 경로 없음: {', '.join(str(m) for m in missing)}", file=sys.stderr)
        return 2
    summary = run(roots, args.apply)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"{'[APPLY]' if args.apply else '[DRY-RUN]'} 큐레이션 JSONL → N-Triples(.nt)")
        for item in summary["files"]:
            extra = f", needs_review={item['needs_review']}" if item["needs_review"] else ""
            print(f"  [{item['status']}] {item['path']} → {Path(item['target']).name}: {item['entries']}건{extra}")
            for w in item["warnings"]:
                print(f"      ⚠ {w}")
        for e in summary["errors"]:
            print(f"  ✗ {e}")
        t = summary["totals"]
        print(f"  합계: 파일 {t['files']}, 기록 {t['entries']}, needs_review {t['needs_review']}, "
              f"wm:unmapped 를 쓰는 기록 {t['unmapped']}")
        if not args.apply:
            print("\n  변경 없음. 실제 이행은 --apply (원본은 .migration-archive/store-<시각>/ 로 이동).")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
