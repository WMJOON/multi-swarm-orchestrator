#!/usr/bin/env python3
"""Mode C: Chart Projection — 기존 chart.json에 새 vertex를 추가한다."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# ── 유틸 ────────────────────────────────────────────────
def cosine_sim(a: list[float], b: list[float]) -> float:
    """numpy 없이 코사인 유사도 계산."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na * nb > 0 else 0.0


# ── 검증 ────────────────────────────────────────────────
def validate_sparsity(coords: list[float]) -> list[str]:
    """Sparsity 제약: max >= 0.7, 나머지 <= 0.3."""
    errors: list[str] = []
    if not coords:
        errors.append("coords가 비어 있습니다")
        return errors
    max_val = max(coords)
    if max_val < 0.7:
        errors.append(f"max(coords)={max_val:.2f} < 0.7 — 주축 좌표가 너무 낮습니다")
    rest = sorted(coords, reverse=True)[1:]
    over = [(i, v) for i, v in enumerate(coords) if v > 0.3 and v != max_val]
    if over:
        errors.append(
            f"비주축 좌표 > 0.3 — {', '.join(f'idx {i}={v:.2f}' for i, v in over)}"
        )
    return errors


def check_similarity(
    coords: list[float], vertices: dict, threshold: float = 0.5
) -> list[str]:
    """기존 vertices와 cosine similarity 비교 → 경고 목록 반환."""
    warnings: list[str] = []
    for vid, v in vertices.items():
        existing_coords = v.get("axis_coord")
        if not existing_coords:
            continue
        sim = cosine_sim(coords, existing_coords)
        if sim > threshold:
            warnings.append(
                f"WARNING: vertex '{vid}' 과 유사도 {sim:.3f} (>{threshold})"
            )
    return warnings


# ── CLI ─────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Mode C: Chart Projection — chart.json에 새 vertex 추가"
    )
    p.add_argument("--domain", required=True, help="도메인 이름")
    p.add_argument("--id", required=True, dest="vertex_id", help="vertex ID")
    p.add_argument("--name", required=True, help="vertex 표시명")
    p.add_argument("--concept", required=True, help="vertex 개념 설명")
    p.add_argument("--axis", required=True, help="주축 ID")
    p.add_argument(
        "--coords", required=True,
        help="좌표 JSON 배열 (예: '[0.9, 0.1, 0.2]')"
    )
    p.add_argument(
        "--assembled-from", default=None,
        help="조합 출처 vertex ID JSON 배열 (예: '[\"v1\",\"v2\"]')"
    )
    p.add_argument(
        "--registry", default="~/.mso-registry",
        help="레지스트리 루트 경로 (기본: ~/.mso-registry)"
    )
    p.add_argument("--dry-run", action="store_true", help="검증만 수행, 파일 변경 없음")
    return p.parse_args()


# ── 메인 ────────────────────────────────────────────────
def main() -> int:
    args = parse_args()
    registry = Path(args.registry).expanduser().resolve()
    chart_path = registry / args.domain / "chart.json"

    # 1. chart.json 로드
    if not chart_path.exists():
        print(f"ERROR: chart.json 없음: {chart_path}", file=sys.stderr)
        return 1

    with open(chart_path, "r", encoding="utf-8") as f:
        chart = json.load(f)

    # 2. coords 파싱
    try:
        coords = json.loads(args.coords)
    except json.JSONDecodeError as e:
        print(f"ERROR: coords JSON 파싱 실패: {e}", file=sys.stderr)
        return 1

    if not isinstance(coords, list) or not all(isinstance(c, (int, float)) for c in coords):
        print("ERROR: coords는 숫자 배열이어야 합니다", file=sys.stderr)
        return 1

    # 3. axes 수와 coords 길이 일치 검증
    n_axes = len(chart.get("axes", []))
    if len(coords) != n_axes:
        print(
            f"ERROR: coords 길이({len(coords)})가 axes 수({n_axes})와 불일치",
            file=sys.stderr,
        )
        return 1

    # 4. Sparsity 검증
    sparsity_errors = validate_sparsity(coords)
    if sparsity_errors:
        for e in sparsity_errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        return 1

    # 5. 주축 ID가 axes에 존재하는지 확인
    axis_ids = {a["id"] for a in chart.get("axes", [])}
    if args.axis not in axis_ids:
        print(f"ERROR: axis '{args.axis}'가 chart axes에 없음 (가능: {axis_ids})", file=sys.stderr)
        return 1

    # 6. 기존 vertices와 유사도 검사
    vertices = chart.get("vertices", {})
    sim_warnings = check_similarity(coords, vertices)
    for w in sim_warnings:
        print(f"  {w}")

    # 7. 중복 ID 검사
    if args.vertex_id in vertices:
        print(f"ERROR: vertex ID '{args.vertex_id}'가 이미 존재합니다", file=sys.stderr)
        return 1

    # 8. assembled_from 파싱
    assembled_from: list[str] | None = None
    if args.assembled_from:
        try:
            assembled_from = json.loads(args.assembled_from)
        except json.JSONDecodeError as e:
            print(f"ERROR: assembled-from JSON 파싱 실패: {e}", file=sys.stderr)
            return 1

    # 9. dry-run이면 여기서 종료
    if args.dry_run:
        print(f"DRY-RUN: 검증 통과 — vertex '{args.vertex_id}' 추가 가능")
        print(f"  name: {args.name}")
        print(f"  concept: {args.concept}")
        print(f"  axis: {args.axis}")
        print(f"  coords: {coords}")
        if assembled_from:
            print(f"  assembled_from: {assembled_from}")
        return 0

    # 10. vertex 추가
    new_vertex = {
        "id": args.vertex_id,
        "name": args.name,
        "concept": args.concept,
        "axis": args.axis,
        "axis_coord": coords,
        "assembled_from": assembled_from or [],
        "directive_path": None,
    }
    vertices[args.vertex_id] = new_vertex
    chart["vertices"] = vertices

    # 11. metrics 업데이트
    metrics = chart.get("metrics", {})
    metrics["n_vertices"] = len(vertices)

    # 유사도 통계 재계산
    all_coords = [v["axis_coord"] for v in vertices.values() if v.get("axis_coord")]
    if len(all_coords) >= 2:
        sims = []
        for i in range(len(all_coords)):
            for j in range(i + 1, len(all_coords)):
                sims.append(cosine_sim(all_coords[i], all_coords[j]))
        metrics["avg_similarity"] = round(sum(sims) / len(sims), 4) if sims else 0.0
        metrics["max_similarity"] = round(max(sims), 4) if sims else 0.0
    chart["metrics"] = metrics

    # 12. 저장
    with open(chart_path, "w", encoding="utf-8") as f:
        json.dump(chart, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"ADDED vertex '{args.vertex_id}' to {chart_path}")
    print(f"  n_vertices: {metrics['n_vertices']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
