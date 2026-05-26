#!/usr/bin/env python3
"""
Workflow YAML to Mermaid Diagram Converter

용도:
  1. 글로벌 workflow → 프로젝트 전체 flow chart
  2. 모듈별 workflow → discovery → development → testing flow
  3. 모듈 간 dependencies → graph visualization

사용법:
  python workflow_to_mermaid.py --global
  python workflow_to_mermaid.py --module 01.consultdata
  python workflow_to_mermaid.py --dependencies
"""

import yaml
import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class WorkflowMermaidConverter:
    """Workflow YAML을 Mermaid 다이어그램으로 변환"""

    def __init__(self, workflow_dir: Path = Path(__file__).parent.parent):
        self.workflow_dir = workflow_dir
        self.global_workflow_path = workflow_dir / "workflow-00.yaml"

    def load_yaml(self, path: Path) -> Dict:
        """YAML 파일 로드 (오류 무시하고 계속)"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            print(f"⚠️  YAML Error in {path.name}: {str(e)[:50]}... (skipping)")
            return {}

    # ─────────────────────────────────────────────────────────
    # 1. Global Workflow to Flowchart
    # ─────────────────────────────────────────────────────────

    def global_workflow_to_flowchart(self) -> str:
        """글로벌 workflow-00.yaml → Mermaid flowchart 변환"""
        data = self.load_yaml(self.global_workflow_path)
        phases = data.get("phases", [])
        milestones = data.get("milestones", [])

        mermaid_lines = [
            "flowchart TD",
            '    Start([AI Chatbot 1.0 Project]) --> Phase1',
            ""
        ]

        # Phase들을 연결
        prev_phase = None
        for phase in phases:
            phase_id = phase.get("id", "")
            phase_name = phase.get("name", "")
            status_emoji = self._status_emoji(phase.get("status"))
            phase_node_id = f'Phase_{phase_id.replace("-", "_")}'

            # Phase 노드 생성
            mermaid_lines.append(
                f'    {phase_node_id}["{status_emoji} {phase_name}"]'
            )

            # 이전 phase와 연결
            if prev_phase:
                mermaid_lines.append(f"    {prev_phase} --> {phase_node_id}")
            prev_phase = phase_node_id

            # 의존성 표시
            dependencies = phase.get("dependencies", [])
            if dependencies:
                for dep in dependencies:
                    dep_phase_id = f'Phase_{dep.replace("-", "_")}'
                    mermaid_lines.append(
                        f'    {dep_phase_id} -->|dependency| {phase_node_id}'
                    )

        # 마일스톤 추가
        mermaid_lines.append("")
        for milestone in milestones:
            ms_id = milestone.get("id", "")
            ms_name = milestone.get("name", "")
            ms_status = milestone.get("status", "pending")
            status_emoji = self._status_emoji(ms_status)
            ms_node_id = f'Milestone_{ms_id.replace("-", "_")}'

            mermaid_lines.append(f'    {ms_node_id}["{status_emoji} {ms_name}"]')

            # Milestone을 해당 phase에 연결
            phase_ref = milestone.get("phase_ref", "")
            if phase_ref:
                phase_node_id = f'Phase_{phase_ref.replace("-", "_")}'
                mermaid_lines.append(
                    f'    {phase_node_id} -.->|milestone| {ms_node_id}'
                )

        # End 노드
        mermaid_lines.append(f"    {prev_phase} --> End([Project Complete])")

        return "\n".join(mermaid_lines)

    # ─────────────────────────────────────────────────────────
    # 2. Module Workflow to Flowchart
    # ─────────────────────────────────────────────────────────

    def module_workflow_to_flowchart(self, module_id: str) -> str:
        """모듈 workflow → Mermaid flowchart 변환"""
        module_path = self.workflow_dir / module_id / f"{module_id}-workflow-00.yaml"
        if not module_path.exists():
            return f"Error: {module_path} not found"

        data = self.load_yaml(module_path)
        module_name = data.get("module", {}).get("name", module_id)

        mermaid_lines = [
            "flowchart TD",
            f'    Start(["{module_name}"]) --> Discovery',
            ""
        ]

        # Discovery Phase
        discovery = data.get("discovery", {})
        discovery_steps = discovery.get("steps", [])
        mermaid_lines.append(f'    Discovery["🔍 Discovery & Planning"]')
        prev_node = "Discovery"
        for i, step in enumerate(discovery_steps, 1):
            step_title = self._extract_step_title(step, i)
            if not step_title:
                continue
            step_id = f"Disc_Step_{i}"
            safe_title = str(step_title).replace('"', "'")
            mermaid_lines.append(f'    {step_id}["{safe_title}"]')
            mermaid_lines.append(f'    {prev_node} --> {step_id}')
            prev_node = step_id

        # Development Phase
        mermaid_lines.append("")
        mermaid_lines.append(f'    Development["⚙️ Development & Implementation"]')
        mermaid_lines.append(f'    {prev_node} --> Development')

        development = data.get("development", {})
        dev_steps = development.get("steps", [])
        prev_dev_node = "Development"
        for i, step_obj in enumerate(dev_steps, 1):
            step_title = self._extract_step_title(step_obj, i)
            if step_title:
                step_id = f"Dev_Step_{i}"
                safe_title = str(step_title).replace('"', "'")
                mermaid_lines.append(f'    {step_id}["{safe_title}"]')
                mermaid_lines.append(f'    {prev_dev_node} --> {step_id}')
                prev_dev_node = step_id

        # Testing Phase
        mermaid_lines.append("")
        mermaid_lines.append(f'    Testing["✅ Testing & Evaluation"]')
        mermaid_lines.append(f'    {prev_dev_node} --> Testing')

        testing = data.get("testing", {})
        test_steps = testing.get("steps", [])
        prev_test_node = "Testing"
        for i, step_obj in enumerate(test_steps, 1):
            step_title = self._extract_step_title(step_obj, i)
            if step_title:
                step_id = f"Test_Step_{i}"
                safe_title = str(step_title).replace('"', "'")
                mermaid_lines.append(f'    {step_id}["{safe_title}"]')
                mermaid_lines.append(f'    {prev_test_node} --> {step_id}')
                prev_test_node = step_id

        # End
        mermaid_lines.append("")
        status = testing.get("status", "pending")
        status_emoji = self._status_emoji(status)
        mermaid_lines.append(f'    {prev_test_node} --> End(["{status_emoji} Complete"])')

        return "\n".join(mermaid_lines)

    # ─────────────────────────────────────────────────────────
    # 3. Dependencies Graph
    # ─────────────────────────────────────────────────────────

    def dependencies_graph(self) -> str:
        """모듈 간 의존성 → Mermaid graph 변환"""
        # 모든 모듈 워크플로우 찾기
        modules = []
        for module_dir in self.workflow_dir.iterdir():
            if module_dir.is_dir() and module_dir.name not in {"templates", "scripts", "diagrams", "references", "assets"} and not module_dir.name.startswith("."):
                workflow_file = module_dir / f"{module_dir.name}-workflow-00.yaml"
                if workflow_file.exists():
                    modules.append((module_dir.name, workflow_file))

        # 의존성 수집
        edges: Set[Tuple[str, str, str]] = set()
        module_names: Dict[str, str] = {}

        for module_id, workflow_path in sorted(modules):
            data = self.load_yaml(workflow_path)
            module_name = data.get("module", {}).get("name", module_id)
            module_names[module_id] = module_name

            dependencies = data.get("dependencies", [])
            for dep in dependencies:
                provides = dep.get("provides", "")
                consumers = dep.get("consumers", [])
                if consumers and isinstance(consumers, list):
                    for consumer in consumers:
                        if consumer != module_id:
                            edges.add((module_id, consumer, provides))

        # Mermaid graph 생성
        mermaid_lines = [
            "graph TB",
            ""
        ]

        # 노드 생성
        for module_id, module_name in sorted(module_names.items()):
            node_id = module_id.replace(".", "_").replace("-", "_")
            display_name = module_name[:20]  # 길이 제한
            mermaid_lines.append(f'    {node_id}["{module_id}<br/>{display_name}"]')

        mermaid_lines.append("")

        # 엣지 생성
        for from_module, to_module, label in sorted(edges):
            from_id = from_module.replace(".", "_").replace("-", "_")
            to_id = to_module.replace(".", "_").replace("-", "_")
            # 라벨이 길면 축약
            label_short = label[:15] + "..." if len(label) > 15 else label
            mermaid_lines.append(f'    {from_id} -->|"{label_short}"| {to_id}')

        return "\n".join(mermaid_lines)

    # ─────────────────────────────────────────────────────────
    # 4. Deliverables Tree
    # ─────────────────────────────────────────────────────────

    def deliverables_tree(self, module_id: str) -> str:
        """모듈의 deliverables를 tree 구조로 시각화"""
        module_path = self.workflow_dir / module_id / f"{module_id}-workflow-00.yaml"
        if not module_path.exists():
            return f"Error: {module_path} not found"

        data = self.load_yaml(module_path)
        module_name = data.get("module", {}).get("name", module_id)
        deliverables = data.get("deliverables", [])

        mermaid_lines = [
            "graph TD",
            f'    Root["📦 {module_name}<br/>Deliverables"]',
            ""
        ]

        for i, deliv in enumerate(deliverables, 1):
            deliv_type = deliv.get("type", "unknown")
            location = deliv.get("location", "")
            status = deliv.get("status", "unknown")
            status_emoji = self._status_emoji(status)

            node_id = f"D_{i}"
            label = f'{status_emoji} {deliv_type}\n{location}'
            mermaid_lines.append(f'    {node_id}["{label}"]')
            mermaid_lines.append(f'    Root --> {node_id}')

            # type-specific details
            if deliv_type == "scripts" and "count" in deliv:
                count = deliv.get("count")
                mermaid_lines.append(f'    {node_id}_count["Count: {count}"]')
                mermaid_lines.append(f'    {node_id} --> {node_id}_count')

            if deliv_type == "data" and "subfolders" in deliv:
                for j, subfolder in enumerate(deliv.get("subfolders", []), 1):
                    if isinstance(subfolder, dict):
                        subfolder_name = subfolder.get("path") or next(iter(subfolder.values()), str(subfolder))
                    else:
                        subfolder_name = str(subfolder)
                    safe_name = subfolder_name.replace('"', "'")
                    subfolder_id = f'{node_id}_sf_{j}'
                    mermaid_lines.append(
                        f'    {subfolder_id}["📁 {safe_name}"]'
                    )
                    mermaid_lines.append(f'    {node_id} --> {subfolder_id}')

        return "\n".join(mermaid_lines)

    # ─────────────────────────────────────────────────────────
    # 5. Timeline Gantt Chart
    # ─────────────────────────────────────────────────────────

    def timeline_gantt(self, module_id: str) -> str:
        """모듈 timeline을 Gantt chart로 변환"""
        module_path = self.workflow_dir / module_id / f"{module_id}-workflow-00.yaml"
        if not module_path.exists():
            return f"Error: {module_path} not found"

        data = self.load_yaml(module_path)
        timeline = data.get("timeline", [])

        if not timeline:
            return f"No timeline data for {module_id}"

        mermaid_lines = [
            "gantt",
            f'    title {module_id} Timeline',
            "    dateFormat YYYY-MM-DD",
            ""
        ]

        for phase in timeline:
            phase_name = phase.get("phase", "")
            date_range = phase.get("date", "")
            status = phase.get("status", "")

            if date_range and "-" in date_range:
                # Parse date range
                parts = date_range.split(" to ")
                if len(parts) == 2:
                    start_date = parts[0].strip()
                    end_date = parts[1].strip()
                    status_code = "done" if status == "completed" else "active" if status == "active" else "crit"

                    mermaid_lines.append(
                        f'    {phase_name.replace(" ", "_")}: {status_code}, {start_date}, {end_date}'
                    )

        return "\n".join(mermaid_lines)

    # ─────────────────────────────────────────────────────────
    # Utility Functions
    # ─────────────────────────────────────────────────────────

    def _extract_step_title(self, step, idx: int):
        """Step에서 제목을 추출. dict, string 모두 처리."""
        if isinstance(step, str):
            return step
        if isinstance(step, dict):
            # try step-01, step-02, ...
            for key in (f"step-0{idx}", f"step-{idx}"):
                if key in step:
                    return step[key]
            # fallback: first key starting with "step-"
            for key, val in step.items():
                if isinstance(key, str) and key.startswith("step-"):
                    return val
        return None

    def _status_emoji(self, status: str) -> str:
        """status를 emoji로 변환"""
        status_map = {
            "completed": "✅",
            "active": "🔄",
            "pending": "⏳",
            "draft": "📝",
            "production-ready": "🚀",
            "complete": "✔️",
        }
        return status_map.get(status, "❓")

    # ─────────────────────────────────────────────────────────
    # 6. Aggregate (계층 참조 → subgraph 클러스터)
    # ─────────────────────────────────────────────────────────

    RESERVED_TOP_KEYS = {
        "meta", "metadata", "module", "project",
        "dependencies", "key_decisions",
        "deliverables", "quality_metrics", "timeline",
        "versioning", "governance", "metrics",
    }
    MAX_DEPTH = 3

    def aggregate_to_flowchart(self, root_yaml: Path, max_depth: int = 3) -> str:
        """root workflow YAML → phase.workflows[].ref 트리 → subgraph 통합 다이어그램.

        - root 의 각 phase 가 cluster 가 됨
        - phase.workflows[].ref 가 있으면 해당 sub workflow 의 phase/group 을 nested
          subgraph 로 렌더링 (anchor 가 있으면 그 phase 만)
        - depth > max_depth 면 ERROR 텍스트 노드 삽입
        """
        lines = ["flowchart TD", ""]
        visited: Set[Path] = {root_yaml.resolve()}
        ctx = {"counter": 0}

        root_doc = self.load_yaml(root_yaml)
        if not root_doc:
            return "flowchart TD\n    Empty[\"(root yaml 로드 실패)\"]"

        # root level phases (RESERVED 제외 dict)
        root_phases = self._collect_phases(root_doc)
        if not root_phases:
            return "flowchart TD\n    Empty[\"(phase 없음)\"]"

        prev_cluster = None
        for phase_key, phase in root_phases:
            cluster_id = self._safe_id(f"P_{phase_key}")
            label = phase.get("label", phase_key)
            status_emoji = self._status_emoji(phase.get("status", "pending"))
            lines.append(f'    subgraph {cluster_id}["{status_emoji} {label}"]')

            entry_nodes = self._render_phase_body(phase, lines, ctx)

            # phase.workflows[] 가 있으면 nested subgraph
            for ref_obj in phase.get("workflows", []) or []:
                ref_str = ref_obj.get("ref", "")
                if not ref_str:
                    continue
                ref_path_str, _, anchor = ref_str.partition("#")
                sub_path = (root_yaml.parent / ref_path_str).resolve()
                if sub_path in visited:
                    err_id = self._safe_id("err_" + str(ctx["counter"]))
                    lines.append(f'    {err_id}["⚠ 순환: {ref_str}"]')
                    ctx["counter"] += 1
                    continue
                visited.add(sub_path)
                nested_entry = self._render_sub_workflow(
                    sub_path, anchor, lines, ctx, depth=2, max_depth=max_depth, visited=visited
                )
                if nested_entry and entry_nodes:
                    lines.append(f'    {entry_nodes[-1]} --> {nested_entry}')

            lines.append("    end")
            if prev_cluster:
                lines.append(f'    {prev_cluster} --> {cluster_id}')
            prev_cluster = cluster_id
            lines.append("")

        return "\n".join(lines)

    def _render_phase_body(self, phase: dict, lines: list, ctx: dict) -> list[str]:
        """phase.steps 노드를 렌더링하고 entry node id 목록 반환."""
        steps = phase.get("steps", []) or []
        entry_nodes: list[str] = []
        prev_node = None
        for node in steps:
            if not isinstance(node, dict):
                continue
            nid = node.get("id") or f"anon_{ctx['counter']}"
            ctx["counter"] += 1
            safe = self._safe_id(nid)
            label = (node.get("label") or nid).replace('"', "'")
            ntype = node.get("type", "step")
            shape_open, shape_close = self._node_shape(ntype)
            lines.append(f'    {safe}{shape_open}"{label}"{shape_close}')
            if prev_node:
                lines.append(f'    {prev_node} --> {safe}')
            else:
                entry_nodes.append(safe)
            prev_node = safe
            # decision branches
            for b in node.get("branches", []) or []:
                goto = b.get("goto")
                on_val = b.get("on", b.get(True))
                if goto:
                    safe_goto = self._safe_id(goto)
                    lbl = f'|{on_val}|' if on_val else ''
                    lines.append(f'    {safe} -->{lbl} {safe_goto}')
        if prev_node and prev_node not in entry_nodes:
            entry_nodes.append(prev_node)
        return entry_nodes

    def _render_sub_workflow(self, sub_path: Path, anchor: str, lines: list,
                              ctx: dict, depth: int, max_depth: int, visited: set) -> str | None:
        """sub workflow YAML 의 (anchor 있으면 해당) phase 를 nested subgraph 로 렌더링.

        Returns: nested subgraph 의 entry node id (없으면 None)
        """
        if depth > max_depth:
            err_id = self._safe_id("err_d_" + str(ctx["counter"]))
            lines.append(f'    {err_id}["⚠ max_depth({max_depth}) 초과"]')
            ctx["counter"] += 1
            return None
        if not sub_path.exists():
            err_id = self._safe_id("err_f_" + str(ctx["counter"]))
            lines.append(f'    {err_id}["⚠ sub 파일 없음: {sub_path.name}"]')
            ctx["counter"] += 1
            return None

        sub_doc = self.load_yaml(sub_path)
        if not sub_doc:
            return None

        phases = self._collect_phases(sub_doc)
        target_phases = phases
        if anchor:
            target_phases = [(k, v) for k, v in phases if k == anchor]
            if not target_phases:
                err_id = self._safe_id("err_a_" + str(ctx["counter"]))
                lines.append(f'    {err_id}["⚠ anchor 없음: #{anchor}"]')
                ctx["counter"] += 1
                return None

        first_entry: str | None = None
        for pkey, phase in target_phases:
            cluster_id = self._safe_id(f"sub_{sub_path.stem}_{pkey}_{ctx['counter']}")
            ctx["counter"] += 1
            label = phase.get("label", pkey)
            lines.append(f'    subgraph {cluster_id}["{label}"]')
            entries = self._render_phase_body(phase, lines, ctx)

            # 재귀: sub 의 phase 가 다시 workflows[] 를 가질 수 있음
            for ref_obj in phase.get("workflows", []) or []:
                ref_str = ref_obj.get("ref", "")
                if not ref_str:
                    continue
                ref_path_str, _, sub_anchor = ref_str.partition("#")
                sub_sub_path = (sub_path.parent / ref_path_str).resolve()
                if sub_sub_path in visited:
                    continue
                visited.add(sub_sub_path)
                nested = self._render_sub_workflow(
                    sub_sub_path, sub_anchor, lines, ctx,
                    depth=depth + 1, max_depth=max_depth, visited=visited
                )
                if nested and entries:
                    lines.append(f'    {entries[-1]} --> {nested}')

            lines.append("    end")
            if first_entry is None and entries:
                first_entry = entries[0]
        return first_entry

    def _collect_phases(self, doc: dict) -> list:
        if not isinstance(doc, dict):
            return []
        out = []
        for k, v in doc.items():
            if k in self.RESERVED_TOP_KEYS:
                continue
            if isinstance(v, dict):
                out.append((k, v))
        return out

    @staticmethod
    def _safe_id(s: str) -> str:
        return "n_" + "".join(c if c.isalnum() else "_" for c in str(s))

    @staticmethod
    def _node_shape(ntype: str) -> tuple[str, str]:
        # decision: {} (마름모), validation: {{}} (육각형), 그 외: []
        if ntype == "decision":
            return ("{", "}")
        if ntype == "validation":
            return ("{{", "}}")
        if ntype == "group":
            return ("([", "])")
        return ("[", "]")

    def save_mermaid(self, content: str, output_path: Path) -> None:
        """Mermaid 콘텐츠를 파일로 저장"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Saved: {output_path}")

    def save_markdown(self, mermaid_content: str, output_path: Path, title: str) -> None:
        """Mermaid를 Markdown 코드 블록으로 저장"""
        markdown = f"# {title}\n\n```mermaid\n{mermaid_content}\n```\n"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"✅ Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert Workflow YAML to Mermaid Diagrams"
    )
    parser.add_argument(
        "--global",
        dest="global_workflow",
        action="store_true",
        help="Generate global workflow flowchart"
    )
    parser.add_argument(
        "--module",
        type=str,
        help="Generate module workflow flowchart (e.g., 01.consultdata)"
    )
    parser.add_argument(
        "--dependencies",
        dest="dependencies_graph",
        action="store_true",
        help="Generate module dependencies graph"
    )
    parser.add_argument(
        "--deliverables",
        type=str,
        help="Generate deliverables tree (e.g., 01.consultdata)"
    )
    parser.add_argument(
        "--timeline",
        type=str,
        help="Generate timeline gantt chart (e.g., 01.consultdata)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate all diagrams"
    )
    parser.add_argument(
        "--aggregate",
        type=str,
        help="Aggregate hierarchical workflow into single subgraph diagram (root workflow YAML path)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "diagrams",
        help="Output directory for diagrams"
    )

    args = parser.parse_args()
    converter = WorkflowMermaidConverter()
    output_dir = args.output_dir

    try:
        if args.global_workflow or args.all:
            print("🔄 Converting global workflow...")
            mermaid = converter.global_workflow_to_flowchart()
            converter.save_markdown(
                mermaid,
                output_dir / "01-global-workflow.md",
                "Global Workflow"
            )

        if args.module:
            print(f"🔄 Converting module workflow: {args.module}...")
            mermaid = converter.module_workflow_to_flowchart(args.module)
            converter.save_markdown(
                mermaid,
                output_dir / f"02-module-{args.module}.md",
                f"Module: {args.module}"
            )

        if args.dependencies_graph or args.all:
            print("🔄 Converting dependencies graph...")
            mermaid = converter.dependencies_graph()
            converter.save_markdown(
                mermaid,
                output_dir / "03-dependencies-graph.md",
                "Module Dependencies"
            )

        if args.deliverables:
            print(f"🔄 Converting deliverables: {args.deliverables}...")
            mermaid = converter.deliverables_tree(args.deliverables)
            converter.save_markdown(
                mermaid,
                output_dir / f"04-deliverables-{args.deliverables}.md",
                f"Deliverables: {args.deliverables}"
            )

        if args.timeline:
            print(f"🔄 Converting timeline: {args.timeline}...")
            mermaid = converter.timeline_gantt(args.timeline)
            converter.save_markdown(
                mermaid,
                output_dir / f"05-timeline-{args.timeline}.md",
                f"Timeline: {args.timeline}"
            )

        if args.aggregate:
            root_yaml_path = Path(args.aggregate).resolve()
            print(f"🔄 Aggregating hierarchical workflow: {root_yaml_path.name}...")
            mermaid = converter.aggregate_to_flowchart(root_yaml_path)
            converter.save_markdown(
                mermaid,
                output_dir / f"06-aggregate-{root_yaml_path.stem}.md",
                f"Aggregate: {root_yaml_path.stem}"
            )

        if args.all:
            print("🔄 Generating all module diagrams...")
            for module_path in Path(__file__).parent.parent.iterdir():
                if module_path.is_dir() and module_path.name not in {"templates", "scripts", "diagrams", "references", "assets"} and not module_path.name.startswith("."):
                    module_id = module_path.name

                    # Module workflow
                    mermaid = converter.module_workflow_to_flowchart(module_id)
                    converter.save_markdown(
                        mermaid,
                        output_dir / f"02-module-{module_id}.md",
                        f"Module: {module_id}"
                    )

                    # Deliverables
                    mermaid = converter.deliverables_tree(module_id)
                    converter.save_markdown(
                        mermaid,
                        output_dir / f"04-deliverables-{module_id}.md",
                        f"Deliverables: {module_id}"
                    )

                    # Timeline
                    mermaid = converter.timeline_gantt(module_id)
                    if "No timeline" not in mermaid:
                        converter.save_markdown(
                            mermaid,
                            output_dir / f"05-timeline-{module_id}.md",
                            f"Timeline: {module_id}"
                        )

        print("\n✨ All conversions complete!")

    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
