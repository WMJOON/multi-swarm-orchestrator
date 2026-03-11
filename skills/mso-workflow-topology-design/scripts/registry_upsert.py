#!/usr/bin/env python3
"""
Registry Upsert — topology spec을 workflow_registry.json에 등록/갱신 (Mode B)

완료된 workflow topology spec 파일의 메타데이터를 추출하여
글로벌 또는 로컬 workflow_registry.json에 upsert 한다.

처리 흐름:
  1. spec 파일에서 메타데이터 추출 (topology_type, nodes 수, run_id)
  2. 기존 registry에서 같은 id(run_id)가 있으면 갱신, 없으면 추가
  3. 저장
  4. --local 이면 워크스페이스 로컬 registry에만 저장

CLI:
  python3 registry_upsert.py --spec path/to/spec.json --intent "IR 덱 v2 제작"
  python3 registry_upsert.py --spec spec.json --intent "전략 분석" --domain-tags strategy --local
  python3 registry_upsert.py --spec spec.json --intent "..." --success-rate 0.85
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 기본 경로
# ---------------------------------------------------------------------------
DEFAULT_GLOBAL_REGISTRY = Path.home() / ".mso-registry" / "workflows" / "workflow_registry.json"


# ---------------------------------------------------------------------------
# Spec 메타데이터 추출
# ---------------------------------------------------------------------------
def _extract_metadata(spec: Dict[str, Any], spec_path: str) -> Dict[str, Any]:
    """topology spec에서 registry 엔트리용 메타데이터 추출."""
    run_id = spec.get("run_id", "")
    if not run_id:
        raise ValueError("spec에 run_id가 없습니다.")

    topology_type = spec.get("topology_type", "linear")
    nodes = spec.get("nodes", [])
    n_nodes = len(nodes) if isinstance(nodes, list) else 0

    return {
        "id": run_id,
        "topology_type": topology_type,
        "n_nodes": n_nodes,
        "spec_path": spec_path,
    }


# ---------------------------------------------------------------------------
# Registry 로드 / 저장
# ---------------------------------------------------------------------------
def _load_registry(path: Path) -> Dict[str, Any]:
    """registry JSON 로드. 파일이 없으면 빈 구조 반환."""
    if not path.exists():
        return {"version": "0.1.0", "workflows": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[WARN] 기존 registry 로드 실패, 새로 생성합니다: {exc}", file=sys.stderr)
        return {"version": "0.1.0", "workflows": []}
    if not isinstance(data, dict):
        return {"version": "0.1.0", "workflows": []}
    if "workflows" not in data:
        data["workflows"] = []
    if "version" not in data:
        data["version"] = "0.1.0"
    return data


def _save_registry(path: Path, data: Dict[str, Any]) -> None:
    """registry JSON 저장. 디렉토리가 없으면 생성."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------
def upsert(
    registry_data: Dict[str, Any],
    entry: Dict[str, Any],
) -> bool:
    """
    registry_data의 workflows 리스트에 entry를 upsert.
    Returns True if updated (existing), False if inserted (new).
    """
    workflows: List[Dict[str, Any]] = registry_data.get("workflows", [])
    entry_id = entry["id"]

    for i, wf in enumerate(workflows):
        if wf.get("id") == entry_id:
            # 갱신: 기존 필드 유지하되 새 값으로 덮어쓰기
            workflows[i].update(entry)
            return True

    # 추가
    workflows.append(entry)
    registry_data["workflows"] = workflows
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="topology spec을 workflow_registry.json에 등록/갱신 (Mode B)",
    )
    ap.add_argument("--spec", required=True, help="workflow_topology_spec.json 경로")
    ap.add_argument("--intent", required=True, help="워크플로우 의도 설명")
    ap.add_argument(
        "--domain-tags",
        default="",
        help="콤마 구분 도메인 태그 (예: strategy,ir-deck)",
    )
    ap.add_argument(
        "--registry",
        default=str(DEFAULT_GLOBAL_REGISTRY),
        help=f"글로벌 registry 경로 (기본: {DEFAULT_GLOBAL_REGISTRY})",
    )
    ap.add_argument(
        "--local",
        action="store_true",
        help="워크스페이스 로컬 registry에만 저장 (spec 파일과 같은 디렉토리)",
    )
    ap.add_argument(
        "--success-rate",
        type=float,
        default=0.0,
        help="초기 success_rate (0.0 ~ 1.0, 기본: 0.0)",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    # spec 로드
    spec_path = Path(args.spec).expanduser().resolve()
    if not spec_path.exists():
        print(f"Error: spec 파일이 존재하지 않습니다: {spec_path}", file=sys.stderr)
        return 1

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error: spec 파일 파싱 실패: {exc}", file=sys.stderr)
        return 1

    if not isinstance(spec, dict):
        print("Error: spec JSON 루트가 object가 아닙니다.", file=sys.stderr)
        return 1

    # 메타데이터 추출
    try:
        meta = _extract_metadata(spec, str(spec_path))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # entry 구성
    intent = args.intent.strip()
    if not intent:
        print("Error: --intent 값이 비어 있습니다.", file=sys.stderr)
        return 1

    domain_tags: List[str] = []
    if args.domain_tags.strip():
        domain_tags = [t.strip() for t in args.domain_tags.split(",") if t.strip()]

    success_rate = max(0.0, min(1.0, args.success_rate))
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    entry: Dict[str, Any] = {
        "id": meta["id"],
        "intent": intent,
        "domain_tags": domain_tags,
        "topology_type": meta["topology_type"],
        "n_nodes": meta["n_nodes"],
        "success_rate": success_rate,
        "last_used": now_iso,
        "spec_path": meta["spec_path"],
    }

    # registry 경로 결정
    if args.local:
        # 로컬: spec 파일과 같은 디렉토리에 workflow_registry.json
        registry_path = spec_path.parent / "workflow_registry.json"
    else:
        registry_path = Path(args.registry).expanduser().resolve()

    # 로드 → upsert → 저장
    registry_data = _load_registry(registry_path)
    was_update = upsert(registry_data, entry)

    _save_registry(registry_path, registry_data)

    action = "갱신" if was_update else "등록"
    print(f"[OK] {action} 완료: id={entry['id']}")
    print(f"     registry: {registry_path}")
    print(f"     intent: {intent}")
    print(f"     topology: {meta['topology_type']} ({meta['n_nodes']} nodes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
