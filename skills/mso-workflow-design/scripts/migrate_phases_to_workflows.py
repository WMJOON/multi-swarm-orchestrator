#!/usr/bin/env python3
"""migrate_phases_to_workflows.py — phase/validation legacy 마이그레이션.

yaml `phases:` → `workflows:` (각 phase = sub-workflow). phase 중간 계층 폐지.
yaml `type: validation` → `type: eval`. Validation node type은 TTL 정본에서
별도 실행 노드로 유지하지 않고 산출물 측정·평가·검증 Eval로 승격한다.
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


def _ensure_validation_branches(node: dict) -> bool:
    changed = False
    branches = node.get("branches")
    if not isinstance(branches, list):
        branches = []
        node["branches"] = branches
        changed = True
    seen = {
        str(branch.get("on", branch.get(True))).lower()
        for branch in branches
        if isinstance(branch, dict) and branch.get("on", branch.get(True)) is not None
    }
    if not ({"pass", "passed"} & seen):
        branches.append({"on": "passed"})
        changed = True
    if not ({"fail", "failed"} & seen):
        branches.append({"on": "failed"})
        changed = True
    return changed


def _migrate_validation_node(node: dict) -> bool:
    if str(node.get("type", "")).lower() != "validation":
        return False

    changed = True
    node["type"] = "eval"
    node.setdefault("oracle_type", "metric")
    if not node.get("criteria"):
        criteria = node.pop("pass_criteria", None) or node.pop("passCriteria", None)
        if criteria:
            node["criteria"] = criteria if isinstance(criteria, list) else [str(criteria)]

    if _ensure_validation_branches(node):
        changed = True
    return changed


def _migrate_nodes(nodes) -> bool:
    changed = False
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if _migrate_validation_node(node):
            changed = True
        if _migrate_nodes(node.get("steps")):
            changed = True
    return changed


def _migrate_workflow_list(workflows) -> bool:
    changed = False
    if not isinstance(workflows, list):
        return False
    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        if _migrate_nodes(workflow.get("steps")):
            changed = True
        if _migrate_workflow_list(workflow.get("workflows")):
            changed = True
    return changed


def migrate_doc(doc: dict) -> tuple[dict, bool]:
    """phases → workflows, validation → eval. 반환: (변환된 doc, 변경 여부)."""
    if not isinstance(doc, dict):
        return doc, False
    changed = False
    # root 스타일: 최상위 phases: 리스트 → workflows: 리스트 (각 phase = sub-workflow)
    if isinstance(doc.get("phases"), list) and "workflows" not in doc:
        doc["workflows"] = doc.pop("phases")
        changed = True
    if _migrate_workflow_list(doc.get("workflows")):
        changed = True
    if _migrate_nodes(doc.get("steps")):
        changed = True
    return doc, changed


def main() -> int:
    ap = argparse.ArgumentParser(description="phases→workflows, validation→eval legacy 마이그레이션")
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
            print(f"  [skip] legacy phases/validation 없음: {p}")
            continue
        if args.apply:
            path.write_text(
                yaml.dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
            print(f"  [MIGRATED] phases→workflows, validation→eval: {p}")
        else:
            print(f"  [dry-run] phases→workflows, validation→eval 예정: {p}")
        migrated += 1

    print(f"\n{'적용' if args.apply else 'dry-run'}: {migrated}개 파일")
    return 0


if __name__ == "__main__":
    sys.exit(main())
