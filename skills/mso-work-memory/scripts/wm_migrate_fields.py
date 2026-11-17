#!/usr/bin/env python3
"""wm_migrate_fields.py — title/text → description/content 필드 이행 (schema v1.3.x → v1.4.0, MSO v0.16.0).

변환 규칙 (결정적, LLM 없음 — SPEC D3):
  description = title            (200자 초과분은 잘라 `…` 로 끝내고 metadata.needs_review=true)
  content     = text
  title, text 키는 제거한다. 그 외 키(id, relations, created_at, metadata, ...)는 값과 순서를 보존한다.
  content 가 `TODO` 로 시작하면(본문이 비어 있는 기록) metadata.needs_review=true 를 단다.

metadata 이행 (옛 기록 created_at < enforce_from 에만 — 멱등):
  metadata.module → metadata.component      옛 module 은 구성요소(스킬·패키지) 이름이었다. 새 module 은 index module id.
  metadata.scope(통제 어휘 밖 자유 서술) → metadata.scope_note, scope 는 비우고 needs_review=true
                                             (통제 어휘 scope 는 사람이 골라야 하므로 채우지 않는다)

안전 장치:
  - 기본은 dry-run(변경 없음). --apply 일 때만 쓴다.
  - --apply 시 원본 파일을 <root>/.migration-archive/fields-<timestamp>/ 로 복사해 둔 뒤 제자리에서 바꾼다.
    (dot-dir 은 reader 가 건너뛰므로 DUP-ID 오탐이 없다 — wm_migrate.py 와 같은 이유)
  - 멱등: 이미 description 이 있는 entry 는 건드리지 않는다. 두 번 실행해도 diff 가 없다.
  - iCloud 충돌 복제본(`* 2.jsonl` 등 공백+숫자로 끝나는 파일명)은 건너뛴다 — 처리하면 DUP-ID 가 생긴다.
  - 대상: track-record, insight-record, release-record. auditlog/worklog 는 런타임 로그라 제외한다.
  - 파싱 불가 줄과 dict 가 아닌 줄은 원문 그대로 보존한다.

사용법:
  wm_migrate_fields.py                       # dry-run (WORKMEM_DIR 또는 ./agent-context/work-memory)
  wm_migrate_fields.py --apply               # 실제 전환
  wm_migrate_fields.py --root DIR [--root DIR2 ...]   # 연관 저장소 등 여러 루트
  wm_migrate_fields.py --json                # 요약을 JSON 으로

종료 코드: 0 정상, 1 파싱 불가 줄 존재(원문은 보존됨).
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

TARGET_DIRS = ("track-record", "insight-record", "release-record")
DESCRIPTION_MAX = 200  # wm_node.DESCRIPTION_MAX 와 같은 값 (독립 실행을 위해 복제)
ICLOUD_DUP_RE = re.compile(r"\s\d+(\.[^.]+)?$")  # "foo 2.jsonl", "foo 2"
NEEDS_REVIEW_PREFIXES = ("TODO",)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wm_metadata  # noqa: E402

SPEC = wm_metadata.load_spec()


def workmem_root() -> Path:
    return Path(os.environ.get("WORKMEM_DIR", "./agent-context/work-memory")).resolve()


def is_icloud_duplicate(path: Path) -> bool:
    return bool(ICLOUD_DUP_RE.search(path.name))


def iter_target_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirname in TARGET_DIRS:
        base = root / dirname
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.jsonl")):
            rel = path.relative_to(root)
            if any(part.startswith(".") for part in rel.parts[:-1]):
                continue  # .migration-archive 등
            if is_icloud_duplicate(path):
                continue
            files.append(path)
    return files


def migrate_entry(entry: dict[str, Any], metadata_step: bool = True) -> tuple[dict[str, Any], list[str]]:
    """entry 하나를 v1.4.0 으로 바꾼다. (새 entry, 사유 목록). 이미 이행된 entry 는 그대로(사유 없음).
    필드 이행(title/text → description/content) 뒤에 metadata 이행(module→component, 자유 서술 scope→scope_note)을 이어서 한다."""
    new_entry, reasons = _migrate_fields(entry)
    if metadata_step:
        new_entry, more = _migrate_metadata(new_entry)
        reasons = reasons + more
    return new_entry, reasons


def _migrate_metadata(entry: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """옛 metadata 를 새 명세(references/metadata-spec.yaml)에 맞춘다. 옛 기록(created_at < enforce_from)에만 적용한다.

      module → component   옛 `module` 은 구성요소(스킬·패키지) 이름이었다. 새 `module` 은 스캐폴드 index 의 module id 라
                           의미가 달라졌다. 새 기록의 `module` 을 건드리지 않도록 옛 기록에만 한다(멱등).
      scope(자유 서술) → scope_note   옛 `scope` 가 통제 어휘(repository/workflow/task/…) 밖의 값이면 scope_note 로 옮긴다.
                           통제 어휘의 `scope` 는 사람이 골라야 하므로 채우지 않고 needs_review 로 표시한다.
    """
    metadata = entry.get("metadata")
    if not isinstance(metadata, dict) or wm_metadata.is_new_record(entry, SPEC):
        return entry, []
    new_md = dict(metadata)
    reasons: list[str] = []
    if "module" in new_md:
        value = new_md.pop("module")
        if "component" not in new_md:
            new_md["component"] = value
        reasons.append("module-to-component")
    scope = new_md.get("scope")
    if scope is not None:
        allowed = wm_metadata.vocab_values(SPEC, "scope")
        items = scope if isinstance(scope, list) else [scope]
        invalid = [str(i) for i in items if str(i) not in allowed]
        if invalid and "scope_note" not in new_md:
            valid = [i for i in items if str(i) in allowed]
            new_md["scope_note"] = ", ".join(invalid)
            if valid:
                new_md["scope"] = valid          # 통제 어휘에 맞는 값은 남긴다
            else:
                new_md.pop("scope")              # 사람이 골라야 하므로 비운다
            new_md["needs_review"] = True
            reasons.append("scope-to-scope-note")
    if not reasons:
        return entry, []
    out = dict(entry)
    out["metadata"] = new_md
    return out, reasons


def _migrate_fields(entry: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    if "description" in entry and "content" in entry and "title" not in entry and "text" not in entry:
        return entry, []
    if "description" in entry and "title" not in entry and "text" not in entry:
        return entry, []

    reasons: list[str] = []
    title = entry.get("title")
    text = entry.get("text")
    description = entry.get("description")
    content = entry.get("content")
    if description is None:
        description = str(title) if title is not None else ""
    if content is None:
        content = str(text) if text is not None else ""

    needs_review = False
    if len(description) > DESCRIPTION_MAX:
        description = description[: DESCRIPTION_MAX - 1].rstrip() + "…"
        reasons.append("description-truncated")
        needs_review = True
    if not description:
        reasons.append("description-empty")
        needs_review = True
    if content.lstrip().startswith(NEEDS_REVIEW_PREFIXES) or not content.strip():
        reasons.append("content-todo")
        needs_review = True

    new_entry: dict[str, Any] = {}
    placed = False
    for key, value in entry.items():
        if key in ("title", "text"):
            if not placed:
                new_entry["description"] = description
                new_entry["content"] = content
                placed = True
            continue
        if key in ("description", "content"):
            if not placed:
                new_entry["description"] = description
                new_entry["content"] = content
                placed = True
            continue
        new_entry[key] = value
    if not placed:
        new_entry["description"] = description
        new_entry["content"] = content

    if needs_review:
        metadata = new_entry.get("metadata")
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        metadata["needs_review"] = True
        new_entry["metadata"] = metadata
    return new_entry, reasons


def migrate_file(path: Path) -> tuple[str, dict[str, Any]]:
    """파일 전체를 이행한 새 본문과 통계를 돌려준다. 파싱 불가 줄은 원문 보존."""
    original = path.read_text(encoding="utf-8")
    out_lines: list[str] = []
    stats = {"entries": 0, "migrated": 0, "unchanged": 0, "unparsable": 0, "needs_review": [], "reasons": {}}
    for raw in original.splitlines():
        if not raw.strip():
            out_lines.append(raw)
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            stats["unparsable"] += 1
            out_lines.append(raw)
            continue
        if not isinstance(obj, dict):
            stats["unparsable"] += 1
            out_lines.append(raw)
            continue
        stats["entries"] += 1
        new_obj, reasons = migrate_entry(obj)
        if new_obj == obj and list(new_obj.keys()) == list(obj.keys()):
            stats["unchanged"] += 1
            out_lines.append(raw)
            continue
        stats["migrated"] += 1
        for reason in reasons:
            stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1
        marked = (new_obj.get("metadata") or {}).get("needs_review") is True
        was_marked = isinstance(obj.get("metadata"), dict) and obj["metadata"].get("needs_review") is True
        if marked and not was_marked:
            stats["needs_review"].append(obj.get("id"))
        out_lines.append(json.dumps(new_obj, ensure_ascii=False))
    body = "\n".join(out_lines)
    if original.endswith("\n"):
        body += "\n"
    return body, stats


def run(roots: list[Path], apply: bool) -> dict[str, Any]:
    summary: dict[str, Any] = {"apply": apply, "roots": [], "files": [], "totals": {
        "entries": 0, "migrated": 0, "unchanged": 0, "unparsable": 0, "needs_review": 0}}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for root in roots:
        summary["roots"].append(str(root))
        archive = root / ".migration-archive" / f"fields-{stamp}"
        for path in iter_target_files(root):
            body, stats = migrate_file(path)
            summary["files"].append({"path": str(path), **{k: stats[k] for k in ("entries", "migrated", "unchanged", "unparsable")},
                                     "needs_review": stats["needs_review"], "reasons": stats["reasons"]})
            for key in ("entries", "migrated", "unchanged", "unparsable"):
                summary["totals"][key] += stats[key]
            summary["totals"]["needs_review"] += len(stats["needs_review"])
            if apply and stats["migrated"]:
                dest = archive / path.relative_to(root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
                path.write_text(body, encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="실제 전환 (기본은 dry-run)")
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
        mode = "[APPLY]" if args.apply else "[DRY-RUN]"
        print(f"{mode} title/text → description/content")
        for item in summary["files"]:
            if item["migrated"] or item["unparsable"]:
                review = f"  needs_review={item['needs_review']}" if item["needs_review"] else ""
                print(f"  {item['path']}: 이행 {item['migrated']}/{item['entries']}"
                      + (f", 파싱불가 {item['unparsable']}" if item["unparsable"] else "") + review)
        t = summary["totals"]
        print(f"  합계: entry {t['entries']}, 이행 {t['migrated']}, 변경없음 {t['unchanged']}, "
              f"needs_review {t['needs_review']}, 파싱불가 {t['unparsable']}")
        if not args.apply:
            print("\n  변경 없음. 실제 전환은 --apply (원본은 .migration-archive/ 에 백업).")
        elif t["migrated"]:
            print("\n  ✓ 완료. 원본은 각 루트의 .migration-archive/fields-<시각>/ 에 있다.")
    return 1 if summary["totals"]["unparsable"] else 0


if __name__ == "__main__":
    sys.exit(main())
