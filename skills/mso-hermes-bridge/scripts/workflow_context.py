#!/usr/bin/env python3
"""
mso-hermes-bridge/scripts/workflow_context.py

workflow TTL ABox에서 특정 step의 컨텍스트를 추출해
Hermes에 전달할 구조화된 프롬프트를 생성한다.

Usage:
    python3 workflow_context.py --workflow-dir agent-context/workflow \
        --step-id <step-uri-local-name> \
        [--format prompt|json]
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from rdflib import Graph, Namespace, RDF, RDFS, URIRef
    from rdflib.namespace import XSD
    HAS_RDFLIB = True
except ImportError:
    HAS_RDFLIB = False

WF = Namespace("http://mso.org/workflow#")


def load_graph(workflow_dir: Path) -> "Graph":
    g = Graph()
    for ttl in workflow_dir.rglob("*.abox.ttl"):
        g.parse(str(ttl), format="turtle")
    # TBox가 있으면 같이 로드
    for ttl in workflow_dir.rglob("*.tbox.ttl"):
        g.parse(str(ttl), format="turtle")
    return g


def find_step(g: "Graph", step_id: str) -> "URIRef | None":
    """step_id (local name)로 URIRef를 찾는다."""
    for s in g.subjects():
        if isinstance(s, URIRef) and str(s).endswith(step_id):
            return s
    return None


def extract_step_context(g: "Graph", step_uri: "URIRef") -> dict:
    """step URI에서 MSO 컨텍스트를 추출한다."""
    ctx: dict = {
        "step_id": str(step_uri).split("#")[-1].split("/")[-1],
        "step_uri": str(step_uri),
        "label": "",
        "description": "",
        "node_type": "",
        "consumes": [],   # 입력 artifacts
        "produces": [],   # 출력 artifacts
        "executor": None,
        "delegates_to": None,
    }

    # label
    label = g.value(step_uri, RDFS.label)
    if label:
        ctx["label"] = str(label)

    # description/comment
    comment = g.value(step_uri, RDFS.comment)
    if comment:
        ctx["description"] = str(comment)

    # node type
    for rdf_type in g.objects(step_uri, RDF.type):
        local = str(rdf_type).split("#")[-1]
        if local not in ("NamedIndividual",):
            ctx["node_type"] = local
            break

    # consumes (artifact → step)
    for artifact in g.subjects(WF.consumed_by, step_uri):
        art_label = g.value(artifact, RDFS.label)
        art_type = g.value(artifact, WF.artifactType)
        art_loc = g.value(artifact, WF.location)
        ctx["consumes"].append({
            "id": str(artifact).split("#")[-1].split("/")[-1],
            "label": str(art_label) if art_label else "",
            "type": str(art_type) if art_type else "",
            "location": str(art_loc) if art_loc else "",
        })

    # produces (step → artifact)
    for artifact in g.objects(step_uri, WF.produces_to):
        art_label = g.value(artifact, RDFS.label)
        art_type = g.value(artifact, WF.artifactType)
        art_loc = g.value(artifact, WF.location)
        ctx["produces"].append({
            "id": str(artifact).split("#")[-1].split("/")[-1],
            "label": str(art_label) if art_label else "",
            "type": str(art_type) if art_type else "",
            "location": str(art_loc) if art_loc else "",
        })

    # delegates_to (Executor)
    executor = g.value(step_uri, WF.delegates_to)
    if executor:
        exec_label = g.value(executor, RDFS.label)
        exec_endpoint = g.value(executor, WF.apiEndpoint)
        ctx["delegates_to"] = {
            "id": str(executor).split("#")[-1].split("/")[-1],
            "label": str(exec_label) if exec_label else "",
            "endpoint": str(exec_endpoint) if exec_endpoint else "",
        }

    return ctx


def build_prompt(ctx: dict) -> str:
    """컨텍스트를 Hermes에 전달할 구조화된 프롬프트로 변환한다."""
    lines = []
    lines.append(f"# MSO Workflow Step: {ctx['label'] or ctx['step_id']}")
    lines.append("")

    if ctx["description"]:
        lines.append(f"{ctx['description']}")
        lines.append("")

    if ctx["consumes"]:
        lines.append("## 입력 Artifacts (consumes)")
        for art in ctx["consumes"]:
            loc = f" ― {art['location']}" if art["location"] else ""
            lines.append(f"- [{art['type'] or 'artifact'}] {art['label'] or art['id']}{loc}")
        lines.append("")

    if ctx["produces"]:
        lines.append("## 출력 Artifacts (produces)")
        for art in ctx["produces"]:
            loc = f" → {art['location']}" if art["location"] else ""
            lines.append(f"- [{art['type'] or 'artifact'}] {art['label'] or art['id']}{loc}")
        lines.append("")

    lines.append("## 실행 지침")
    lines.append("위 입력 Artifact를 기반으로 태스크를 수행하고, 출력 Artifact를 지정된 위치에 생성하라.")
    lines.append("MSO workflow의 일부로 실행되므로 결과는 반드시 구조화된 형태로 반환한다.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="MSO workflow step → Hermes 컨텍스트 추출")
    parser.add_argument("--workflow-dir", default="agent-context/workflow",
                        help="workflow TTL 디렉토리")
    parser.add_argument("--step-id", required=True,
                        help="step의 local name (ex: psd-s-034)")
    parser.add_argument("--format", choices=["prompt", "json"], default="prompt",
                        help="출력 형식")
    args = parser.parse_args()

    if not HAS_RDFLIB:
        print("[workflow_context] ERROR: rdflib 미설치. 'pip install rdflib' 실행", file=sys.stderr)
        sys.exit(1)

    workflow_dir = Path(args.workflow_dir)
    if not workflow_dir.exists():
        print(f"[workflow_context] ERROR: {workflow_dir} 없음", file=sys.stderr)
        sys.exit(1)

    g = load_graph(workflow_dir)
    step = find_step(g, args.step_id)
    if not step:
        print(f"[workflow_context] ERROR: step '{args.step_id}' 를 TTL에서 찾을 수 없음", file=sys.stderr)
        sys.exit(1)

    ctx = extract_step_context(g, step)

    if args.format == "json":
        print(json.dumps(ctx, ensure_ascii=False, indent=2))
    else:
        print(build_prompt(ctx))


if __name__ == "__main__":
    main()
