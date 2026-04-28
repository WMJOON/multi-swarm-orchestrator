#!/usr/bin/env python3
"""Mode D: Chart Bootstrap — 새 도메인의 chart.json 골격을 생성한다."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── CLI ─────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Mode D: Chart Bootstrap — 새 도메인 chart.json 골격 생성"
    )
    p.add_argument("--domain", required=True, help="도메인 이름")
    p.add_argument("--purpose", required=True, help="차트 목적 설명")
    p.add_argument(
        "--axes", required=True,
        help='축 정의 JSON 배열 (예: \'[{"id":"ax1","label":"L","semantic":"S"}]\')'
    )
    p.add_argument(
        "--registry", default="~/.mso-registry",
        help="레지스트리 루트 경로 (기본: ~/.mso-registry)"
    )
    p.add_argument("--force", action="store_true", help="기존 chart.json 덮어쓰기")
    return p.parse_args()


# ── 검증 ────────────────────────────────────────────────
def validate_axes(axes_raw: str) -> tuple[list[dict] | None, str | None]:
    """axes JSON 파싱 및 필수 필드 검증. (파싱결과, 에러메시지) 반환."""
    try:
        axes = json.loads(axes_raw)
    except json.JSONDecodeError as e:
        return None, f"axes JSON 파싱 실패: {e}"

    if not isinstance(axes, list) or len(axes) == 0:
        return None, "axes는 비어 있지 않은 배열이어야 합니다"

    required = {"id", "label", "semantic"}
    for i, ax in enumerate(axes):
        if not isinstance(ax, dict):
            return None, f"axes[{i}]가 객체가 아닙니다"
        missing = required - set(ax.keys())
        if missing:
            return None, f"axes[{i}]에 필수 필드 누락: {missing}"

    # 중복 id 검사
    ids = [a["id"] for a in axes]
    if len(ids) != len(set(ids)):
        return None, f"axes에 중복 id 존재: {ids}"

    return axes, None


# ── 메인 ────────────────────────────────────────────────
def main() -> int:
    args = parse_args()
    registry = Path(args.registry).expanduser().resolve()
    domain_dir = registry / args.domain
    chart_path = domain_dir / "chart.json"

    # 1. axes 파싱/검증
    axes, err = validate_axes(args.axes)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    # 2. 기존 chart.json 존재 시 처리
    if chart_path.exists() and not args.force:
        print(
            f"ERROR: chart.json 이미 존재: {chart_path}\n"
            f"  덮어쓰려면 --force 옵션을 사용하세요",
            file=sys.stderr,
        )
        return 1

    # 3. 디렉토리 생성
    domain_dir.mkdir(parents=True, exist_ok=True)

    # 4. chart.json 구성
    indexed_axes = [
        {
            "index": i,
            "id": ax["id"],
            "label": ax["label"],
            "semantic": ax["semantic"],
        }
        for i, ax in enumerate(axes)
    ]

    chart = {
        "chart_id": f"{args.domain}-chart",
        "domain": args.domain,
        "version": "v1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": args.purpose,
        "axes": indexed_axes,
        "vertices": {},
        "metrics": {
            "n_axes": len(axes),
            "n_vertices": 0,
            "avg_similarity": 0.0,
            "max_similarity": 0.0,
        },
    }

    # 5. chart.json 저장
    with open(chart_path, "w", encoding="utf-8") as f:
        json.dump(chart, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"CREATED {chart_path}")
    print(f"  domain: {args.domain}")
    print(f"  axes: {len(axes)}")

    # 6. registry_config.json에 도메인 등록
    meta_dir = registry / "_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    config_path = meta_dir / "registry_config.json"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {"domains": []}

    domains = config.get("domains", [])
    if args.domain not in domains:
        domains.append(args.domain)
        config["domains"] = domains
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"  registry_config: domain '{args.domain}' 추가됨")
    else:
        print(f"  registry_config: domain '{args.domain}' 이미 등록됨")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
