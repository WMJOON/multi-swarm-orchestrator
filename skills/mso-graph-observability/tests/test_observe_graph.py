from __future__ import annotations

import importlib.util
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, RDF, RDFS, OWL, XSD


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
    assert "subgraph phase_phase_demo_p_" in markdown
    assert "-->|hasNode|" not in markdown
    assert "-->|hasBranch|" not in markdown
    assert "Branch" not in markdown
    assert "((start))" in markdown
    assert "((end))" in markdown
    assert '["A\\nid: a\\nStep"]' in markdown
    assert '{{"Gate\\nid: d\\nDecision"}}' in markdown


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


def test_workflow_subgraph_renders_dataflow_nodes():
    graph = Graph()
    wf = observe_graph.WF
    producer = wf["node/demo/producer"]
    consumer = wf["node/demo/consumer"]
    phase = wf["phase/demo/p"]

    for node, label in ((producer, "Produce"), (consumer, "Consume")):
        graph.add((node, RDF.type, wf.Step))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((phase, wf.hasNode, node))
    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("Phase")))

    out_dir = BNode()
    graph.add((producer, wf.directory, out_dir))
    graph.add((out_dir, wf.dirRole, Literal("output")))
    graph.add((out_dir, wf.dirPath, Literal("generated/results/")))
    graph.add((producer, wf.deliverables, Literal("report.md")))

    in_dir = BNode()
    graph.add((consumer, wf.directory, in_dir))
    graph.add((in_dir, wf.dirRole, Literal("input")))
    graph.add((in_dir, wf.dirPath, Literal("generated/results/")))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo")

    assert '(["DATA\\nid: local_file:generated/results/"])' in markdown
    assert "## Data Node Index" in markdown
    assert "`generated/results/`" in markdown
    assert "-->|downstream|" in markdown
    assert "-->|upstream|" in markdown
    assert "DATA\\nid: deliverable:" in markdown
    assert "report.md" in markdown
    assert "classDef data" in markdown


def test_workflow_subgraph_uses_index_data_ids_for_locations():
    graph = Graph()
    wf = observe_graph.WF
    producer = wf["node/demo/producer"]
    phase = wf["phase/demo/p"]
    graph.add((producer, RDF.type, wf.Step))
    graph.add((producer, RDF.type, wf.Node))
    graph.add((producer, RDFS.label, Literal("Produce")))
    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("Phase")))
    graph.add((phase, wf.hasNode, producer))

    out_dir = BNode()
    graph.add((producer, wf.directory, out_dir))
    graph.add((out_dir, wf.dirRole, Literal("output")))
    graph.add((out_dir, wf.dirPath, Literal("content/draft/")))

    duplicate_out_dir = BNode()
    graph.add((producer, wf.directory, duplicate_out_dir))
    graph.add((duplicate_out_dir, wf.dirRole, Literal("output")))
    graph.add((duplicate_out_dir, wf.dirPath, Literal("content/draft/archive/")))

    data_registry = {
        "content/draft/": {
            "id": "content.draft",
            "data_type": "local_file",
            "locator": "content/draft/",
            "source": "subdir",
        },
        "content/draft/archive/": {
            "id": "content.draft",
            "data_type": "local_file",
            "locator": "content/draft/archive/",
            "source": "subdir",
        }
    }

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", data_registry=data_registry)

    assert "id: content.draft" in markdown
    assert markdown.count('(["DATA\\nid: content.draft"])') == 1
    assert "`index:content.draft`" in markdown
    assert "`content/draft/`" in markdown
    assert "-->|downstream|" in markdown
    assert markdown.count("-->|downstream|") == 1


def test_data_registry_uses_longest_locator_prefix():
    data_registry = {
        "agent-context/": {
            "id": "agent-context",
            "data_type": "local_file",
            "locator": "agent-context/",
            "source": "module",
        },
        "agent-context/work-memory/": {
            "id": "agent-context.work-memory",
            "data_type": "local_file",
            "locator": "agent-context/work-memory/",
            "source": "subdir",
        },
    }

    ref = observe_graph.data_ref_for_locator(
        data_registry,
        data_type="local_file",
        locator="agent-context/work-memory/track-record/user-decision/",
    )

    assert ref["id"] == "agent-context.work-memory"
    assert ref["location"] == "index:agent-context.work-memory"


def test_workflow_subgraph_renders_oracle_shape():
    graph = Graph()
    wf = observe_graph.WF
    task = wf["node/demo/task"]
    oracle = wf["node/demo/oracle"]
    phase = wf["phase/demo/p"]

    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("Phase")))
    for node, cls, label in ((task, wf.Step, "Task"), (oracle, wf.Oracle, "Quality Gate")):
        graph.add((node, RDF.type, cls))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((phase, wf.hasNode, node))
    graph.add((task, wf.next, oracle))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo")

    assert '["Task\\nid: task\\nStep"]' in markdown
    assert '[/"Quality Gate\\nid: oracle\\nOracle"\\]' in markdown
    assert "-->|next|" in markdown
    assert "classDef oracle" in markdown
