from __future__ import annotations

import importlib.util
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, XSD


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "observe_graph.py"
SPEC = importlib.util.spec_from_file_location("observe_graph", SCRIPT)
observe_graph = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(observe_graph)


def test_property_map_uses_mermaid_code_fence():
    graph = Graph()
    ex = Namespace("urn:test:")
    graph.add((ex.title, RDF.type, OWL.DatatypeProperty))
    graph.add((ex.title, RDFS.domain, ex.Card))
    graph.add((ex.title, RDFS.range, XSD.string))

    markdown = observe_graph.build_property_map(graph)

    assert "```mermaid" in markdown
    assert "```plaintext" not in markdown
    assert "flowchart LR" in markdown


def test_workflow_topology_renders_execution_edges():
    graph = Graph()
    wf = observe_graph.WF
    node_a = wf["node/demo/a"]
    node_b = wf["node/demo/b"]
    decision = wf["node/demo/d"]
    branch = wf["node/demo/d_branch_rejected_a"]
    phase = wf["phase/demo/p"]

    for node, cls, label in (
        (node_a, wf.Step, "A"),
        (decision, wf.Decision, "Gate"),
        (node_b, wf.Step, "B"),
    ):
        graph.add((node, RDF.type, cls))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((phase, wf.hasNode, node))
    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("Phase")))
    graph.add((node_a, wf.next, decision))
    graph.add((decision, wf.next, node_b))
    graph.add((decision, wf.hasBranch, branch))
    graph.add((branch, RDF.type, wf.Branch))
    graph.add((branch, wf.on, Literal("rejected")))
    graph.add((branch, wf.gotoNode, node_a))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo")

    assert "-->|next|" in markdown
    assert "-.->|on: rejected|" in markdown


def test_repository_topology_hides_internal_node_flow():
    graph = Graph()
    wf = observe_graph.WF
    phase = wf["phase/demo/p"]
    node_a = wf["node/demo/a"]
    node_b = wf["node/demo/b"]

    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("Phase")))
    graph.add((node_a, RDF.type, wf.Step))
    graph.add((node_a, RDF.type, wf.Node))
    graph.add((node_b, RDF.type, wf.Step))
    graph.add((node_b, RDF.type, wf.Node))
    graph.add((phase, wf.hasNode, node_a))
    graph.add((node_a, wf.next, node_b))

    markdown = observe_graph.build_workflow_topology(graph)

    assert "-->|hasNode|" not in markdown
    assert "-->|next|" not in markdown
