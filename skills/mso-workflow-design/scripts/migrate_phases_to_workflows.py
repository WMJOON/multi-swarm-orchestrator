#!/usr/bin/env python3
"""migrate_phases_to_workflows.py — v0.6.1 phase-less 마이그레이션.

yaml `phases:` → `workflows:` (각 phase = sub-workflow). phase 중간 계층 폐지.
- root 스타일: `phases:` 리스트 → `workflows:` 리스트
- 각 항목의 `steps`/`workflows`(nested sub-workflow ref)는 그대로 유지
- `dependencies`(구 phase 간 dependsOn 순서)는 일단 보존 — drop-old 단계에서 `next` 로 전환
  (lifecycle 순서를 잃지 않기 위해 마이그레이션 단계에서는 건드리지 않는다)

dry-run 기본. `--apply` 로 덮어쓰기. work-memory 마이그레이션과 같은 안전 패턴.
"""
import argparse
import sys
from pathlib import Path

import yaml


def migrate_doc(doc: dict) -> tuple[dict, bool]:
    """phases → workflows. 반환: (변환된 doc, 변경 여부)."""
    if not isinstance(doc, dict):
        return doc, False
    changed = False
    # root 스타일: 최상위 phases: 리스트 → workflows: 리스트 (각 phase = sub-workflow)
    if isinstance(doc.get("phases"), list) and "workflows" not in doc:
        doc["workflows"] = doc.pop("phases")
        changed = True
    return doc, changed


def main() -> int:
    ap = argparse.ArgumentParser(description="phases→workflows phase-less 마이그레이션")
    ap.add_argument("paths", nargs="+", help="yaml 파일 경로")
    ap.add_argument("--apply", action="store_true", help="실제 덮어쓰기 (기본: dry-run)")
    args = ap.parse_args()

    migrated = 0
    for p in args.paths:
        path = Path(p)
        if not path.exists():
            print(f"  [SKIP] 파일 없음: {p}")
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            print(f"  [SKIP] YAML 파싱 실패: {p}: {e}")
            continue
        _, changed = migrate_doc(doc)
        if not changed:
            print(f"  [skip] phases 없음: {p}")
            continue
        if args.apply:
            path.write_text(
                yaml.dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
            print(f"  [MIGRATED] phases→workflows: {p}")
        else:
            print(f"  [dry-run] phases→workflows 예정: {p}")
        migrated += 1

    print(f"\n{'적용' if args.apply else 'dry-run'}: {migrated}개 파일")
    return 0


if __name__ == "__main__":
    sys.exit(main())
