#!/usr/bin/env python3
"""wm_migrate.py — per-entry TYPE-NNNN.jsonl → 타입별 aggregate <type>.jsonl 전환.

schema v1.1.x ("entry 1개 = 파일 1개") → v1.2.0 (타입별 append-only JSONL).
auditlog/worklog 는 이미 append 포맷이므로 건드리지 않는다.

왜 archive 가 필수인가:
  reader(validate/show/graph/stats/ttl)는 rglob 로 트리의 모든 .jsonl 을 읽는다.
  per-entry 원본을 트리에 남긴 채 aggregate 를 만들면 같은 entry 가 두 번 보여
  validate 가 전부 DUP-ID 로 오탐한다. 따라서 마이그레이션은 old per-entry 를
  반드시 트리 밖(<root>/.migration-archive/)으로 옮긴다.

사용법:
  wm_migrate.py            # dry-run (변경 없음 — 계획만 출력)
  wm_migrate.py --apply    # 실제 전환 (aggregate 작성 + old → .migration-archive/)

환경변수: WORKMEM_DIR (기본 ./agent-context/work-memory)
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wm_node as wm  # TYPE_PREFIX / TYPE_DIR / entry_file / workmem_root 재사용

# per-entry 파일명 = <PREFIX>-<4자리>.jsonl. 시각 id(auditlog AU-YYYYMMDD-..., worklog
# WL-YYYY-MM-DD)는 4자리+.jsonl 로 끝나지 않으므로 매치되지 않는다(자동 제외).
PER_ENTRY_RE = re.compile(r"^([A-Z]+)-(\d{4})\.jsonl$")


def collect(root: Path):
    """per-entry 파일을 타입별로 수집. (groups: type→[(entry, path)], files: 원본 경로 목록)"""
    prefix_to_type = {v: k for k, v in wm.TYPE_PREFIX.items()}
    groups: dict[str, list] = {}
    files: list[Path] = []
    for f in sorted(root.rglob("*.jsonl")):
        m = PER_ENTRY_RE.match(f.name)
        if not m:
            continue  # aggregate <type>.jsonl 이나 날짜 파일은 매치 안 됨
        t = prefix_to_type.get(m.group(1))
        if not t or t in wm._TIME_SERIES_TYPES:
            continue
        lines = [l for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not lines:
            continue
        try:
            obj = json.loads(lines[0])
        except json.JSONDecodeError:
            print(f"[WARN] 파싱 실패 skip: {f}", file=sys.stderr)
            continue
        if not isinstance(obj, dict):
            continue
        groups.setdefault(t, []).append((obj, f))
        files.append(f)
    return groups, files


def _sort_key(item):
    obj, _ = item
    return (obj.get("created_at", ""), obj.get("id", ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="실제 전환 (기본은 dry-run)")
    args = ap.parse_args()

    root = wm.workmem_root()
    groups, files = collect(root)
    mode = "[APPLY]" if args.apply else "[DRY-RUN]"
    print(f"{mode} WORKMEM_DIR={root}")

    if not files:
        print("  마이그레이션 대상 per-entry 파일 없음 (이미 aggregate 이거나 비어 있음).")
        return 0

    for t in sorted(groups):
        entries = sorted(groups[t], key=_sort_key)
        agg = wm.entry_file(t, "")
        ids = ", ".join(o.get("id", "?") for o, _ in entries[:6]) + (" …" if len(entries) > 6 else "")
        print(f"  {t:<20} {len(entries):>3} entry → {agg.relative_to(root)}   [{ids}]")

    if not args.apply:
        print("\n  변경 없음. 실제 전환은 `wm_migrate.py --apply`.")
        return 0

    archive = root / ".migration-archive"
    written = 0
    for t, items in groups.items():
        entries = sorted(items, key=_sort_key)
        agg = wm.entry_file(t, "")
        agg.parent.mkdir(parents=True, exist_ok=True)
        existing_ids = set()
        if agg.exists():
            for ln in agg.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    existing_ids.add(json.loads(ln).get("id"))
                except json.JSONDecodeError:
                    pass
        with open(agg, "a", encoding="utf-8") as out:
            for obj, _ in entries:
                if obj.get("id") in existing_ids:
                    continue  # 멱등: 이미 aggregate 에 있으면 skip
                out.write(json.dumps(obj, ensure_ascii=False) + "\n")
                existing_ids.add(obj.get("id"))
                written += 1

    # old per-entry → archive (트리 밖으로 — DUP-ID 오탐 방지). 디렉토리 구조 보존.
    for f in files:
        dst = archive / f.relative_to(root)
        dst.parent.mkdir(parents=True, exist_ok=True)
        f.rename(dst)
    # 비게 된 구버전 타입 디렉토리 정리 (best-effort)
    for f in files:
        d = f.parent
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass

    print(f"\n  ✓ {written} entry 를 aggregate 로 전환, old {len(files)} 파일 → {archive.relative_to(root)}/")
    print(f"  검증: WORKMEM_DIR={root} python3 wm_node.py validate {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
