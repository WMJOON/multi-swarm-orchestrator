#!/usr/bin/env python3
"""Mode D Step 8: chart.json → ontology.json 생성 + lazy composition 쿼리.

사용법:
  # 1) chart.json에서 ontology.json 골격 생성
  python3 build_ontology.py --chart chart.json --output ontology.json

  # 2) morphisms를 JSON으로 주입하여 생성
  python3 build_ontology.py --chart chart.json --output ontology.json \
      --morphisms '[{"id":"m1","from":"ax1","to":"ax2","type":"informs","confidence":0.8}]'

  # 3) 기존 ontology.json에서 lazy composition 쿼리
  python3 build_ontology.py --ontology ontology.json --query "technology_analysis→?"
  python3 build_ontology.py --ontology ontology.json --query "?→customer_analysis"
  python3 build_ontology.py --ontology ontology.json --query "all"

  # 4) ontology.json 스키마 검증
  python3 build_ontology.py --ontology ontology.json --validate
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from itertools import product
from pathlib import Path

# ── 합성 테이블 (기본값) ──────────────────────────────────
DEFAULT_COMPOSITION_TABLE: dict[str, str] = {
    "causes+causes": "causes",
    "causes+requires": "causes",
    "causes+constrains": "causes",
    "causes+informs": "informs",
    "requires+causes": "requires",
    "requires+requires": "requires",
    "requires+constrains": "constrains",
    "requires+informs": "requires",
    "constrains+causes": "constrains",
    "constrains+requires": "constrains",
    "constrains+constrains": "constrains",
    "constrains+informs": "constrains",
    "informs+causes": "informs",
    "informs+requires": "informs",
    "informs+constrains": "informs",
    "informs+informs": "informs",
    "contrasts_with+*": "warning:contrasts_with chain",
    "*+contrasts_with": "warning:contrasts_with chain",
}

MORPHISM_TYPES = {"causes", "requires", "constrains", "informs", "contrasts_with"}


# ── CLI ─────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Mode D Step 8: ontology.json 생성 + lazy composition 쿼리"
    )
    # 생성 모드
    p.add_argument("--chart", help="입력 chart.json 경로")
    p.add_argument("--output", "-o", help="출력 ontology.json 경로")
    p.add_argument(
        "--morphisms",
        help='explicit morphisms JSON 배열 (예: \'[{"id":"m1","from":"ax1","to":"ax2","type":"informs","confidence":0.8}]\')',
    )
    p.add_argument("--force", action="store_true", help="기존 ontology.json 덮어쓰기")

    # 쿼리/검증 모드
    p.add_argument("--ontology", help="기존 ontology.json 경로 (쿼리/검증용)")
    p.add_argument(
        "--query",
        help='lazy composition 쿼리 ("A→?", "?→B", "all")',
    )
    p.add_argument("--validate", action="store_true", help="ontology.json 스키마 검증")
    p.add_argument("--max-depth", type=int, default=3, help="합성 최대 깊이 (기본: 3)")

    return p.parse_args()


# ── 검증 ────────────────────────────────────────────────
def validate_morphism(m: dict, objects: set[str]) -> str | None:
    """단일 morphism dict 검증. 에러 메시지 또는 None."""
    required = {"id", "from", "to", "type"}
    missing = required - set(m.keys())
    if missing:
        return f"morphism에 필수 필드 누락: {missing}"

    if m["type"] not in MORPHISM_TYPES:
        return f"잘못된 morphism type: {m['type']} (허용: {MORPHISM_TYPES})"

    if m["from"] not in objects:
        return f"morphism '{m['id']}': from '{m['from']}'이 objects에 없음"

    if m["to"] not in objects:
        return f"morphism '{m['id']}': to '{m['to']}'이 objects에 없음"

    if m["from"] == m["to"]:
        return f"morphism '{m['id']}': self-loop (from == to) — identity는 암묵적으로 존재"

    conf = m.get("confidence")
    if conf is not None and not (0.0 <= conf <= 1.0):
        return f"morphism '{m['id']}': confidence {conf} 범위 초과 (0.0~1.0)"

    return None


def validate_ontology(onto: dict) -> list[str]:
    """ontology.json 구조 검증. 에러 목록 반환."""
    errors: list[str] = []
    required_top = {"category", "domain", "source_chart", "objects", "morphisms", "composition_table"}
    missing = required_top - set(onto.keys())
    if missing:
        errors.append(f"최상위 필수 필드 누락: {missing}")
        return errors

    if onto.get("category") != "C":
        errors.append(f"category는 'C'여야 합니다 (현재: {onto.get('category')})")

    objects = set(onto.get("objects", []))
    if not objects:
        errors.append("objects가 비어 있습니다")

    for i, m in enumerate(onto.get("morphisms", [])):
        err = validate_morphism(m, objects)
        if err:
            errors.append(f"morphisms[{i}]: {err}")

        if m.get("derived") and not m.get("via"):
            errors.append(f"morphisms[{i}]: derived=true이면 via 필수")

    # composition_table 키 형식 검증
    for key in onto.get("composition_table", {}):
        if "+" not in key:
            errors.append(f"composition_table 키 형식 오류: '{key}' ('type_a+type_b' 형식 필요)")

    return errors


# ── 생성 ────────────────────────────────────────────────
def build_ontology(chart_path: str, morphisms_raw: str | None) -> dict:
    """chart.json → ontology.json dict 생성."""
    chart_p = Path(chart_path)
    if not chart_p.exists():
        print(f"ERROR: chart.json 파일 없음: {chart_p}", file=sys.stderr)
        sys.exit(1)

    with open(chart_p, "r", encoding="utf-8") as f:
        chart = json.load(f)

    # objects = axes[].id
    objects = [ax["id"] for ax in chart.get("axes", [])]
    if not objects:
        print("ERROR: chart.json에 axes가 없습니다", file=sys.stderr)
        sys.exit(1)

    # morphisms 파싱
    morphisms: list[dict] = []
    if morphisms_raw:
        try:
            parsed = json.loads(morphisms_raw)
        except json.JSONDecodeError as e:
            print(f"ERROR: morphisms JSON 파싱 실패: {e}", file=sys.stderr)
            sys.exit(1)

        if not isinstance(parsed, list):
            print("ERROR: morphisms는 배열이어야 합니다", file=sys.stderr)
            sys.exit(1)

        obj_set = set(objects)
        for i, m in enumerate(parsed):
            m.setdefault("derived", False)
            err = validate_morphism(m, obj_set)
            if err:
                print(f"ERROR: morphisms[{i}]: {err}", file=sys.stderr)
                sys.exit(1)
            morphisms.append(m)

    ontology = {
        "category": "C",
        "domain": chart.get("domain", "unknown"),
        "source_chart": chart_p.name,
        "objects": objects,
        "morphisms": morphisms,
        "composition_table": deepcopy(DEFAULT_COMPOSITION_TABLE),
    }

    return ontology


# ── Lazy Composition 쿼리 ───────────────────────────────
def lookup_composition(type_a: str, type_b: str, table: dict[str, str]) -> str:
    """합성 테이블에서 결과 유형 조회."""
    key = f"{type_a}+{type_b}"
    if key in table:
        return table[key]
    # wildcard 매칭
    wild_a = f"*+{type_b}"
    if wild_a in table:
        return table[wild_a]
    wild_b = f"{type_a}+*"
    if wild_b in table:
        return table[wild_b]
    return f"unknown({type_a}+{type_b})"


def compute_derived_morphisms(onto: dict, max_depth: int = 3) -> list[dict]:
    """explicit morphisms에서 합성 가능한 derived morphisms를 동적 계산."""
    explicit = [m for m in onto["morphisms"] if not m.get("derived")]
    table = onto.get("composition_table", DEFAULT_COMPOSITION_TABLE)

    # 인접 리스트 구축
    adj: dict[str, list[dict]] = {}
    for m in explicit:
        adj.setdefault(m["from"], []).append(m)

    derived: list[dict] = []
    seen_pairs: set[tuple[str, str]] = {(m["from"], m["to"]) for m in explicit}
    counter = len(onto["morphisms"])

    # BFS 방식 합성 (depth 제한)
    # depth 2: f∘g, depth 3: f∘g∘h, ...
    paths: list[tuple[list[str], list[dict]]] = []
    # 초기 경로: 각 explicit morphism
    for m in explicit:
        paths.append(([m["from"], m["to"]], [m]))

    for _depth in range(max_depth - 1):
        new_paths: list[tuple[list[str], list[dict]]] = []
        for nodes, morphs in paths:
            last_node = nodes[-1]
            for next_m in adj.get(last_node, []):
                next_node = next_m["to"]
                if next_node in nodes:
                    continue  # cycle 방지

                new_nodes = nodes + [next_node]
                new_morphs = morphs + [next_m]

                pair = (nodes[0], next_node)
                if pair in seen_pairs:
                    continue

                # 합성 결과 계산
                result_type = new_morphs[0]["type"]
                for step in new_morphs[1:]:
                    result_type = lookup_composition(result_type, step["type"], table)

                counter += 1
                warning = None
                if result_type.startswith("warning:"):
                    warning = result_type.replace("warning:", "")
                    # contrasts_with chain인 경우, 마지막 non-warning 결과를 기본값으로
                    result_type = new_morphs[-1]["type"]

                derived_m: dict = {
                    "id": f"m{counter}",
                    "from": nodes[0],
                    "to": next_node,
                    "type": result_type,
                    "derived": True,
                    "via": [m["id"] for m in new_morphs],
                    "rule": "∘".join(m["type"] for m in new_morphs) + f"→{result_type}",
                }
                if warning:
                    derived_m["warning"] = warning

                derived.append(derived_m)
                seen_pairs.add(pair)

                new_paths.append((new_nodes, new_morphs))

        paths = new_paths

    return derived


def run_query(onto: dict, query: str, max_depth: int) -> None:
    """쿼리 실행 및 결과 출력."""
    derived = compute_derived_morphisms(onto, max_depth)
    all_morphisms = onto["morphisms"] + derived

    if query == "all":
        results = all_morphisms
    elif query.endswith("→?"):
        source = query[:-2]
        results = [m for m in all_morphisms if m["from"] == source]
    elif query.startswith("?→"):
        target = query[2:]
        results = [m for m in all_morphisms if m["to"] == target]
    else:
        # "A→B" 직접 쿼리
        parts = query.split("→")
        if len(parts) == 2:
            results = [m for m in all_morphisms if m["from"] == parts[0] and m["to"] == parts[1]]
        else:
            print(f'ERROR: 쿼리 형식 오류: "{query}" ("A→?", "?→B", "A→B", "all" 중 하나)', file=sys.stderr)
            sys.exit(1)

    if not results:
        print(f'쿼리 "{query}": 결과 없음')
        return

    print(f'쿼리 "{query}": {len(results)}건')
    print(json.dumps(results, ensure_ascii=False, indent=2))


# ── 메인 ────────────────────────────────────────────────
def main() -> int:
    args = parse_args()

    # 모드 1: 검증
    if args.validate:
        if not args.ontology:
            print("ERROR: --validate에는 --ontology가 필요합니다", file=sys.stderr)
            return 1
        with open(args.ontology, "r", encoding="utf-8") as f:
            onto = json.load(f)
        errors = validate_ontology(onto)
        if errors:
            print(f"VALIDATION FAILED ({len(errors)}건):")
            for e in errors:
                print(f"  - {e}")
            return 1
        print(f"VALID: {args.ontology}")
        return 0

    # 모드 2: 쿼리
    if args.query:
        if not args.ontology:
            print("ERROR: --query에는 --ontology가 필요합니다", file=sys.stderr)
            return 1
        onto_p = Path(args.ontology)
        if not onto_p.exists():
            print(f"ERROR: ontology.json 파일 없음: {onto_p}", file=sys.stderr)
            return 1
        with open(onto_p, "r", encoding="utf-8") as f:
            onto = json.load(f)
        run_query(onto, args.query, args.max_depth)
        return 0

    # 모드 3: 생성
    if not args.chart:
        print("ERROR: --chart 또는 --ontology가 필요합니다", file=sys.stderr)
        return 1

    if not args.output:
        # 기본 출력: chart.json과 같은 디렉토리에 ontology.json
        chart_dir = Path(args.chart).parent
        args.output = str(chart_dir / "ontology.json")

    output_p = Path(args.output)
    if output_p.exists() and not args.force:
        print(
            f"ERROR: 이미 존재: {output_p}\n  덮어쓰려면 --force 옵션을 사용하세요",
            file=sys.stderr,
        )
        return 1

    ontology = build_ontology(args.chart, args.morphisms)

    # 검증
    errors = validate_ontology(ontology)
    if errors:
        print(f"WARNING: 생성된 ontology에 {len(errors)}건의 검증 이슈:")
        for e in errors:
            print(f"  - {e}")

    # 저장
    output_p.parent.mkdir(parents=True, exist_ok=True)
    with open(output_p, "w", encoding="utf-8") as f:
        json.dump(ontology, f, ensure_ascii=False, indent=2)
        f.write("\n")

    n_explicit = len([m for m in ontology["morphisms"] if not m.get("derived")])
    print(f"CREATED {output_p}")
    print(f"  domain: {ontology['domain']}")
    print(f"  objects: {len(ontology['objects'])}")
    print(f"  explicit morphisms: {n_explicit}")
    print(f"  composition_table entries: {len(ontology['composition_table'])}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
