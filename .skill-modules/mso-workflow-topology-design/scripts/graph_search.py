#!/usr/bin/env python3
"""
Graph Search — workflow registry intent-based search (Mode B)

글로벌 + 로컬 workflow_registry.json에서 intent 기반으로
워크플로우를 검색한다.

검색 로직:
  1. 글로벌 + 로컬 registry를 로드하여 워크플로우 목록 병합
  2. intent 기반 키워드 매칭 (단어 겹침 비율)
  3. domain_tags 필터 (지정 시)
  4. score = keyword_overlap * 0.6 + success_rate * 0.4
  5. 상위 top_k개 반환

CLI:
  python3 graph_search.py --intent "IR 덱 제작" --top-k 5
  python3 graph_search.py --intent "전략 분석" --domain-tags strategy,ir-deck --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# 기본 경로
# ---------------------------------------------------------------------------
DEFAULT_GLOBAL_REGISTRY = Path.home() / ".mso-registry" / "workflows" / "workflow_registry.json"


# ---------------------------------------------------------------------------
# 텍스트 정규화 및 토큰화
# ---------------------------------------------------------------------------
def _normalize(s: str) -> str:
    """소문자 변환, 공백 정리, 특수문자 제거."""
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9가-힣\s\-_]", "", s)
    return s.strip()


def _tokenize(s: str) -> Set[str]:
    """텍스트를 토큰 집합으로 분리."""
    tokens = re.split(r"[\s\-_]+", _normalize(s))
    return {t for t in tokens if t}


# ---------------------------------------------------------------------------
# Registry 로드
# ---------------------------------------------------------------------------
def _load_registry(path: Path) -> List[Dict[str, Any]]:
    """registry JSON 파일을 로드하여 workflows 리스트 반환."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[WARN] registry 로드 실패: {path} — {exc}", file=sys.stderr)
        return []
    if not isinstance(data, dict):
        return []
    workflows = data.get("workflows", [])
    if not isinstance(workflows, list):
        return []
    return workflows


def _merge_workflows(
    global_wfs: List[Dict[str, Any]],
    local_wfs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """글로벌 + 로컬 병합. 동일 id가 있으면 로컬 우선."""
    seen: Dict[str, Dict[str, Any]] = {}
    for wf in global_wfs:
        wid = wf.get("id", "")
        if wid:
            seen[wid] = wf
    for wf in local_wfs:
        wid = wf.get("id", "")
        if wid:
            seen[wid] = wf  # 로컬 우선 덮어쓰기
    return list(seen.values())


# ---------------------------------------------------------------------------
# 스코어링
# ---------------------------------------------------------------------------
def _keyword_overlap(query_tokens: Set[str], target_tokens: Set[str]) -> float:
    """쿼리 토큰 중 타겟에 포함된 비율 (recall 관점)."""
    if not query_tokens:
        return 0.0
    if not target_tokens:
        return 0.0
    hit = len(query_tokens & target_tokens)
    return hit / len(query_tokens)


def _score_workflow(
    wf: Dict[str, Any],
    query_tokens: Set[str],
    domain_filter: Optional[Set[str]],
) -> Tuple[float, bool]:
    """
    워크플로우 스코어 계산.
    Returns (score, passed_domain_filter).
    """
    # domain_tags 필터
    wf_tags = set(wf.get("domain_tags", []))
    if domain_filter and not (domain_filter & wf_tags):
        return 0.0, False

    # intent 토큰화
    intent_text = wf.get("intent", "")
    intent_tokens = _tokenize(intent_text)

    # 태그도 토큰에 포함
    for tag in wf_tags:
        intent_tokens |= _tokenize(tag)

    overlap = _keyword_overlap(query_tokens, intent_tokens)
    success_rate = float(wf.get("success_rate", 0.0))

    score = overlap * 0.6 + success_rate * 0.4
    return score, True


# ---------------------------------------------------------------------------
# 검색 메인
# ---------------------------------------------------------------------------
def search(
    intent: str,
    global_registry: Path,
    local_registry: Optional[Path],
    domain_tags: Optional[Set[str]],
    top_k: int,
) -> List[Dict[str, Any]]:
    """intent 기반 워크플로우 검색. 상위 top_k개 반환."""
    global_wfs = _load_registry(global_registry)
    local_wfs = _load_registry(local_registry) if local_registry else []
    all_wfs = _merge_workflows(global_wfs, local_wfs)

    if not all_wfs:
        return []

    query_tokens = _tokenize(intent)
    if not query_tokens:
        return []

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for wf in all_wfs:
        score, passed = _score_workflow(wf, query_tokens, domain_tags)
        if not passed:
            continue
        if score > 0.0:
            scored.append((score, wf))

    # 스코어 내림차순 정렬
    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, wf in scored[:top_k]:
        results.append({
            "id": wf.get("id", ""),
            "intent": wf.get("intent", ""),
            "domain_tags": wf.get("domain_tags", []),
            "topology_type": wf.get("topology_type", ""),
            "n_nodes": wf.get("n_nodes", 0),
            "success_rate": wf.get("success_rate", 0.0),
            "last_used": wf.get("last_used", ""),
            "spec_path": wf.get("spec_path", ""),
            "score": round(score, 4),
        })
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="workflow_registry.json에서 intent 기반 워크플로우 검색 (Mode B)",
    )
    ap.add_argument("--intent", required=True, help="검색 의도 (키워드 / 문장)")
    ap.add_argument(
        "--domain-tags",
        default="",
        help="콤마 구분 도메인 태그 필터 (예: strategy,ir-deck)",
    )
    ap.add_argument(
        "--registry",
        default=str(DEFAULT_GLOBAL_REGISTRY),
        help=f"글로벌 registry 경로 (기본: {DEFAULT_GLOBAL_REGISTRY})",
    )
    ap.add_argument(
        "--local-registry",
        default="",
        help="로컬(워크스페이스) registry 경로",
    )
    ap.add_argument("--top-k", type=int, default=5, help="반환할 최대 결과 수 (기본: 5)")
    ap.add_argument("--json", action="store_true", dest="json_out", help="JSON 형식으로 출력")
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    intent = args.intent.strip()
    if not intent:
        print("Error: --intent 값이 비어 있습니다.", file=sys.stderr)
        return 1

    global_reg = Path(args.registry).expanduser().resolve()
    local_reg = Path(args.local_registry).expanduser().resolve() if args.local_registry.strip() else None

    domain_tags: Optional[Set[str]] = None
    if args.domain_tags.strip():
        domain_tags = {t.strip() for t in args.domain_tags.split(",") if t.strip()}

    results = search(
        intent=intent,
        global_registry=global_reg,
        local_registry=local_reg,
        domain_tags=domain_tags,
        top_k=args.top_k,
    )

    if args.json_out:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        if not results:
            print(f"검색 결과 없음 (intent: \"{intent}\")")
            return 0
        print(f"검색 결과 ({len(results)}건, intent: \"{intent}\"):\n")
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r['id']}] {r['intent']}")
            print(f"     topology={r['topology_type']}  nodes={r['n_nodes']}  "
                  f"success_rate={r['success_rate']}  score={r['score']}")
            if r["domain_tags"]:
                print(f"     tags: {', '.join(r['domain_tags'])}")
            if r["spec_path"]:
                print(f"     spec: {r['spec_path']}")
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
