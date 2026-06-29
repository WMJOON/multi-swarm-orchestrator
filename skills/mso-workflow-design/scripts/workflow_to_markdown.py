#!/usr/bin/env python3
"""
workflow YAML을 마크다운으로 변환
"""

import argparse
import sys
from pathlib import Path

import yaml


def load_workflow(yaml_path: str) -> dict:
    """워크플로우 YAML 파일 로드"""
    with open(yaml_path) as f:
        return yaml.safe_load(f)


def workflow_to_markdown(workflow: dict) -> str:
    """워크플로우를 마크다운 형식으로 변환"""

    lines = []

    # 헤더: workflow 블록 우선, module 블록 폴백
    header = workflow.get("workflow") or workflow.get("module") or {}
    module_name = header.get("name") or header.get("slug") or "Workflow"
    module_id = header.get("id", "unknown")
    module_version = header.get("version", "1.0.0")
    module_desc = header.get("description", "")

    lines.append(f"# {module_name}")
    lines.append("")
    lines.append(f"**ID**: {module_id}  ")
    lines.append(f"**버전**: {module_version}  ")
    lines.append(f"**상태**: {_get_overall_status(workflow)}")
    lines.append("")

    if module_desc:
        lines.append(f"> {module_desc}")
        lines.append("")

    # Mermaid 다이어그램
    mermaid_diagram = _workflow_to_mermaid(workflow)
    lines.append("## Workflow Diagram")
    lines.append("")
    lines.append("```mermaid")
    lines.extend(mermaid_diagram.split("\n"))
    lines.append("```")
    lines.append("")

    # Phase 순회 (임의 phase 키 — RESERVED 제외, YAML 선언 순서 보존)
    for phase_name, phase in _collect_phases_aggr(workflow):
        phase_label = phase.get("label", phase_name)
        phase_status = phase.get("status", "unknown")

        # Phase 헤더
        lines.append(f"## {phase_label}")
        lines.append("")
        lines.append(f"**상태**: {_format_status(phase_status)} | **단계 수**: {len(phase.get('steps', []))}")
        lines.append("")

        # Steps를 한 번에 표 형식으로 표시
        steps = phase.get("steps", [])
        if steps:
            lines.append("| ID | Type | Title | State | Output | Validation |")
            lines.append("|-----|------|-------|-------|--------|------------|")
            for step in steps:
                step_type = step.get("type", "step")
                node_id = step.get("id", "unknown")
                node_label = step.get("label", "")
                node_status = step.get("status", "pending")
                status_emoji = _format_status(node_status)

                # Output 컬럼: 노드 타입별 처리
                # - validation: harness
                # - decision: decision_subject / owner / sla
                # - step/group: deliverables
                if step_type == "validation":
                    harness = step.get("harness", "")
                    output_str = f"harness: `{harness}`" if harness else ""
                elif step_type == "decision":
                    meta_parts = []
                    if step.get("decision_subject"):
                        meta_parts.append(f"subject: {step['decision_subject']}")
                    if step.get("owner"):
                        meta_parts.append(f"owner: {step['owner']}")
                    if step.get("sla"):
                        meta_parts.append(f"SLA: {step['sla']}")
                    output_str = " / ".join(meta_parts)
                else:
                    deliverables = step.get("deliverables", [])
                    output_str = ""
                    if deliverables:
                        output_list = []
                        for d in deliverables:
                            if isinstance(d, dict):
                                for k, v in d.items():
                                    output_list.append(f"{k}")
                            else:
                                output_list.append(str(d))
                        output_str = " / ".join(output_list)

                # Validation 컬럼: 노드 타입별 처리
                # - validation: pass_criteria
                # - decision: description (사람/모델이 검증할 항목)
                # - step/group: validation
                if step_type == "validation":
                    validation = step.get("pass_criteria", [])
                    validation_str = ""
                    if validation:
                        validation_list = [str(v) for v in validation]
                        validation_str = " / ".join(validation_list)
                elif step_type == "decision":
                    desc = step.get("description", "")
                    # 개행을 <br/>로 변환 (테이블 셀 내 줄바꿈)
                    validation_str = desc.strip().replace("\n", "<br/>")
                else:
                    validation = step.get("validation", [])
                    validation_str = ""
                    if validation:
                        validation_list = []
                        for v in validation:
                            if isinstance(v, dict):
                                for k, val in v.items():
                                    validation_list.append(f"{k}: {val}")
                            else:
                                validation_list.append(str(v))
                        validation_str = " / ".join(validation_list)

                # 테이블 셀에서 | 문자 제거를 위해 escape 처리
                output_str = output_str.replace("|", "\\|")
                validation_str = validation_str.replace("|", "\\|")
                node_label = node_label.replace("|", "\\|")

                lines.append(f"| `{node_id}` | {step_type} | {node_label} | {status_emoji} | {output_str} | {validation_str} |")

            lines.append("")

        # Phase 수준 artifacts
        artifacts = phase.get("artifacts", [])
        if artifacts:
            lines.append("**Phase 산출물**:")
            lines.append("")
            for a in artifacts:
                if isinstance(a, dict):
                    for k, v in a.items():
                        lines.append(f"- {k}: {v}")
                else:
                    lines.append(f"- {a}")
            lines.append("")

    # 메타데이터 섹션
    if "dependencies" in workflow or "key_decisions" in workflow or "metrics" in workflow:
        lines.append("## 메타데이터")
        lines.append("")

        # Dependencies
        deps = workflow.get("dependencies", [])
        if deps:
            lines.append("### 의존성")
            lines.append("")
            for dep in deps:
                requires = dep.get("requires", "")
                source = dep.get("source", "")
                status = dep.get("status", "")
                lines.append(f"- **{requires}** (from {source}) — {status}")
            lines.append("")

        # Key Decisions
        decisions = workflow.get("key_decisions", [])
        if decisions:
            lines.append("### 주요 결정")
            lines.append("")
            for dec in decisions:
                decision = dec.get("decision", "")
                rationale = dec.get("rationale", "")
                status = dec.get("status", "")
                lines.append(f"- **{decision}**")
                lines.append(f"  - 근거: {rationale}")
                lines.append(f"  - 상태: {status}")
            lines.append("")

        # Metrics
        metrics = workflow.get("metrics", [])
        if metrics:
            lines.append("### 메트릭")
            lines.append("")
            if isinstance(metrics, list):
                for item in metrics:
                    if isinstance(item, dict):
                        for key, value in item.items():
                            lines.append(f"- {key}: {value}")
                    else:
                        lines.append(f"- {item}")
            elif isinstance(metrics, dict):
                for key, value in metrics.items():
                    lines.append(f"- {key}: {value}")
            lines.append("")

    return "\n".join(lines)


def _get_overall_status(workflow: dict) -> str:
    """워크플로우의 전체 상태 판단 (임의 phase 키)"""
    statuses = [
        phase.get("status", "unknown")
        for _, phase in _collect_phases_aggr(workflow)
    ]

    if not statuses:
        return "⏳ 예정"
    if all(s == "completed" for s in statuses):
        return "✅ 완료"
    elif any(s == "active" for s in statuses):
        return "🔄 진행중"
    else:
        return "⏳ 예정"


def _format_status(status: str) -> str:
    """상태를 이모지와 함께 포맷"""
    status_map = {
        "completed": "✅ 완료",
        "active": "🔄 진행중",
        "pending": "⏳ 예정",
        "blocked": "🚫 차단됨",
    }
    return status_map.get(status, status)


def _workflow_to_mermaid(workflow: dict) -> str:
    """워크플로우를 mermaid flowchart로 변환"""
    lines = ["graph TD"]

    phases = _collect_phases_aggr(workflow)

    # phase 키/id → 첫 step id 매핑 (cross-phase goto 를 진입 노드로 해석)
    phase_entry: dict = {}
    for phase_name, phase in phases:
        steps = phase.get("steps", [])
        if not steps:
            continue
        first_id = steps[0].get("id")
        if not first_id:
            continue
        phase_entry[phase_name] = first_id
        if phase.get("id"):
            phase_entry[phase["id"]] = first_id

    def _resolve(goto: str) -> str:
        # goto 가 phase 를 가리키면 그 phase 의 첫 step 으로, step 이면 그대로
        return phase_entry.get(goto, goto)

    nodes = {}
    edges = []
    prev_last_node = None
    prev_last_type = None

    for phase_name, phase in phases:
        steps = phase.get("steps", [])
        if not steps:
            continue

        first_node = None
        last_node = None
        last_step_type = None

        for step in steps:
            step_type = step.get("type", "step")
            node_id = step.get("id", f"{phase_name}-unknown")
            node_label = step.get("label", node_id)
            node_status = step.get("status", "unknown")

            shape = _get_node_shape(step_type)
            status_color = _get_status_color(node_status)

            # 노드 타입별 mermaid 형태
            # decision: {} (마름모), validation: {{}} (육각형), 그 외: []
            if step_type == "decision":
                node_def = f'{node_id}{{"{node_label}<br/><sub>{node_id}</sub>"}}'
            elif step_type == "validation":
                node_def = f'{node_id}{{{{"{node_label}<br/><sub>{node_id}</sub>"}}}}'
            else:
                node_def = f'{node_id}["{node_label}<br/><sub>{node_id}</sub>"{shape}]'

            if status_color:
                lines.append(f"style {node_id} fill:{status_color},color:#000")

            nodes[node_id] = node_def

            if first_node is None:
                first_node = node_id

            # Sequential edge: 이전 노드가 decision이면 branches로 분기 처리되므로 생략
            prev_step_type = last_step_type if last_node is not None else None
            if last_node is not None and prev_step_type != "decision":
                edges.append((last_node, node_id, None))

            last_node = node_id
            last_step_type = step_type

            # Decision 노드의 분기 edge (라벨 포함: approved/rejected 등)
            if step_type == "decision" and "branches" in step:
                for branch in step.get("branches", []):
                    goto = branch.get("goto", "")
                    if goto:
                        label = branch.get("on") or branch.get(True) or ""
                        edges.append((node_id, _resolve(goto), str(label) if label else None))

        # phase 경계 자동 edge — 직전 phase 가 decision 으로 끝나면 명시 분기가
        # 흐름을 책임지므로 생략 (중복/오해 유발 방지)
        if prev_last_node and first_node and prev_last_type != "decision":
            edges.append((prev_last_node, first_node, None))

        prev_last_node = last_node
        prev_last_type = last_step_type

    for node_def in nodes.values():
        lines.append(f"    {node_def}")

    # 동일 edge 중복 제거 (선언 순서 보존)
    seen_edges: set = set()
    for from_node, to_node, label in edges:
        key = (from_node, to_node, label)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        if label:
            lines.append(f"    {from_node} -->|{label}| {to_node}")
        else:
            lines.append(f"    {from_node} --> {to_node}")

    return "\n".join(lines)


def _get_node_shape(node_type: str) -> str:
    """노드 타입에 따른 mermaid 형태 (decision/validation은 본문에서 별도 처리)"""
    shapes = {
        "step": "",
        "decision": "{}",
        "validation": "{{}}",
        "group": "([])",
        "phase": "[\\\\]",
    }
    return shapes.get(node_type, "")


def _get_status_color(status: str) -> str:
    """상태에 따른 색상"""
    colors = {
        "completed": "#90EE90",
        "active": "#FFE4B5",
        "pending": "#E6E6FA",
        "blocked": "#FFB6C6",
    }
    return colors.get(status, "")


def cmd_convert(yaml_path: str, output_path: str | None = None):
    """워크플로우 YAML을 마크다운으로 변환"""

    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        sys.exit(f"[ERROR] 파일 없음: {yaml_path}")

    # 기본 출력 경로
    if not output_path:
        output_path = yaml_file.with_suffix(".md")

    out_file = Path(output_path)

    try:
        workflow = load_workflow(yaml_path)
        markdown = workflow_to_markdown(workflow)

        with open(out_file, "w") as f:
            f.write(markdown)

        print(f"✓ 마크다운 생성 완료: {out_file}")

    except Exception as e:
        sys.exit(f"[ERROR] 변환 실패: {e}")


# ─── aggregate (계층 통합) ────────────────────────────────────────────────────

RESERVED_TOP_KEYS = {
    "workflow", "meta", "metadata", "module", "project",
    "dependencies", "key_decisions",
    "deliverables", "quality_metrics", "timeline",
    "versioning", "governance", "metrics",
}
MAX_DEPTH = 3


def _collect_phases_aggr(doc: dict) -> list:
    if not isinstance(doc, dict):
        return []
    out = []
    for k, v in doc.items():
        if k in RESERVED_TOP_KEYS:
            continue
        if isinstance(v, dict):
            out.append((k, v))
    return out


def _walk_sub_workflows(root_yaml: Path, max_depth: int = MAX_DEPTH):
    """root → sub_workflow tree 를 BFS 로 평탄화. (path, doc) 리스트 반환."""
    visited: set[Path] = {root_yaml.resolve()}
    result: list[tuple[Path, dict, int]] = []

    def _walk(path: Path, depth: int):
        if not path.exists():
            return
        try:
            with open(path) as f:
                doc = yaml.safe_load(f) or {}
        except Exception:
            return
        result.append((path, doc, depth))
        if depth >= max_depth:
            return
        for _, phase in _collect_phases_aggr(doc):
            for ref_obj in phase.get("workflows", []) or []:
                ref_str = ref_obj.get("ref", "")
                if not ref_str:
                    continue
                ref_path_str, _, _anchor = ref_str.partition("#")
                sub_path = (path.parent / ref_path_str).resolve()
                if sub_path in visited:
                    continue
                visited.add(sub_path)
                _walk(sub_path, depth + 1)

    _walk(root_yaml.resolve(), 1)
    return result


def cmd_aggregate(root_yaml_path: str, output_path: str | None = None):
    """root workflow + sub workflow 트리를 단일 마크다운으로 통합."""
    root = Path(root_yaml_path).resolve()
    if not root.exists():
        sys.exit(f"[ERROR] 파일 없음: {root_yaml_path}")

    if not output_path:
        output_path = root.with_name(f"{root.stem}-aggregate.md")
    out_file = Path(output_path)

    docs = _walk_sub_workflows(root)
    if not docs:
        sys.exit(f"[ERROR] 문서 로드 실패: {root}")

    sections: list[str] = []
    root_doc = docs[0][1]
    root_module = root_doc.get("module", {})
    sections.append(f"# Aggregated Workflow: {root_module.get('name', root.stem)}")
    sections.append("")
    sections.append(f"**Root**: `{root.name}`  ")
    sections.append(f"**총 sub workflow 수**: {len(docs) - 1}  ")
    sections.append(f"**계층 depth**: {max(d for _, _, d in docs)}")
    sections.append("")

    sections.append("## Source Tree")
    sections.append("")
    for path, _, depth in docs:
        indent = "  " * (depth - 1)
        sections.append(f"- {indent}`{path.name}` (depth {depth})")
    sections.append("")

    for path, doc, depth in docs:
        rel_name = path.name
        section_header = "##" if depth == 1 else "###"
        module = doc.get("module", {})
        title = module.get("name") or rel_name
        sections.append(f"{section_header} {'  ' * (depth - 1)}{title}")
        sections.append("")
        sections.append(f"_Source: `{rel_name}` (depth {depth})_")
        sections.append("")
        sections.append(workflow_to_markdown(doc))
        sections.append("")
        sections.append("---")
        sections.append("")

    out_file.write_text("\n".join(sections))
    print(f"✓ Aggregate 마크다운 생성 완료: {out_file} ({len(docs)} 문서)")


def main():
    parser = argparse.ArgumentParser(
        description="Workflow YAML을 마크다운으로 변환",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "사용 예:\n"
            "  python workflow_to_markdown.py workflow.yaml\n"
            "  python workflow_to_markdown.py root_workflow.yaml --aggregate\n"
        ),
    )
    parser.add_argument("yaml", help="변환할 workflow YAML 경로 (단일) 또는 root YAML (--aggregate 시)")
    parser.add_argument("-o", "--output", help="출력 파일 (생략 시 YAML 파일명.md)")
    parser.add_argument(
        "--aggregate",
        action="store_true",
        help="root → sub workflow 트리를 단일 md 로 통합 (계층 참조 자동 해석)",
    )

    args = parser.parse_args()
    if args.aggregate:
        cmd_aggregate(args.yaml, args.output)
    else:
        cmd_convert(args.yaml, args.output)


if __name__ == "__main__":
    main()
