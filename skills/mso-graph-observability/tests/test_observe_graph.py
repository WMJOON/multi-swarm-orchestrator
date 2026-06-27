from __future__ import annotations

import importlib.util
import subprocess
import sys
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

    assert '@{ shape: doc, label: "DOCUMENT\\nid: local_file:generated/results/" }' in markdown
    assert "## Artifact Node Index" in markdown
    assert "| Artifact Type | Primary Consumer | Id | Medium | Location | Locator | Detail |" in markdown
    assert "`generated/results/`" in markdown
    assert "-->|downstream|" in markdown
    assert "-->|upstream|" in markdown
    assert "boundary_start_demo_start_" in markdown
    assert "boundary_end_demo_end_" in markdown
    assert "-->|next|" in markdown
    assert any(
        "boundary_start_demo_start_" in line and "-->|next|" in line and "step_node_demo_producer_" in line
        for line in markdown.splitlines()
    )
    assert any(
        "step_node_demo_producer_" in line and "-->|next|" in line and "step_node_demo_consumer_" in line
        for line in markdown.splitlines()
    )
    assert any(
        "step_node_demo_consumer_" in line and "-->|next|" in line and "boundary_end_demo_end_" in line
        for line in markdown.splitlines()
    )
    assert "DOCUMENT\\nid: deliverable:" in markdown
    assert "report.md" in markdown
    assert "classDef document" in markdown
    assert "classDef knowledge_store" in markdown


def test_workflow_and_artifact_stream_views_are_separated():
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

    in_dir = BNode()
    graph.add((consumer, wf.directory, in_dir))
    graph.add((in_dir, wf.dirRole, Literal("input")))
    graph.add((in_dir, wf.dirPath, Literal("generated/results/")))

    workflow = observe_graph.build_workflow_topology(graph, scope="demo", view="workflow")
    artifact_stream = observe_graph.build_workflow_topology(graph, scope="demo", view="artifact-stream")

    assert "((start))" in workflow
    assert "((end))" in workflow
    assert "-->|next|" in workflow
    assert "KNOWLEDGE STORE\\nid:" not in workflow
    assert "DOCUMENT\\nid:" not in workflow
    assert "-->|upstream|" not in workflow
    assert "-->|downstream|" not in workflow

    assert "`artifact-stream` view" in artifact_stream
    assert "DOCUMENT\\nid: local_file:generated/results/" in artifact_stream
    assert "-->|upstream|" in artifact_stream
    assert "-->|downstream|" in artifact_stream
    assert "((start))" not in artifact_stream
    assert "-->|next|" not in artifact_stream


def test_data_stream_report_flags_unconsumed_outputs_and_external_inputs():
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

    output_dir = BNode()
    graph.add((producer, wf.directory, output_dir))
    graph.add((output_dir, wf.dirRole, Literal("output")))
    graph.add((output_dir, wf.dirPath, Literal("generated/results/")))
    graph.add((producer, wf.deliverables, Literal("final-report.md")))

    input_dir = BNode()
    graph.add((consumer, wf.directory, input_dir))
    graph.add((input_dir, wf.dirRole, Literal("input")))
    graph.add((input_dir, wf.dirPath, Literal("external/source/")))

    report = observe_graph.build_data_stream_report(graph)

    assert "Produced But Unconsumed" in report
    assert "External Inputs" in report
    assert "Consumer Fit Heuristic" in report
    assert "local_file:generated/results/" in report
    assert "Produced but unconsumed artifacts" in report
    assert "terminal/review document candidate" in report
    assert "confirm agent/user consumer" in report
    assert "else omit or convert to jsonl/ttl/sqlite" in report
    assert "local_file:external/source/" in report
    assert "external input (document)" in report


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
    assert markdown.count('@{ shape: doc, label: "DOCUMENT\\nid: content.draft" }') == 1
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
    assert ref["artifact_type"] == "event_store"
    assert ref["resource_kind"] == "data"


def test_artifact_type_explicit_value_overrides_inference():
    data_registry = {
        "agent-context/ontology/": {
            "id": "agent-context.ontology",
            "data_type": "local_file",
            "artifact_type": "document",
            "locator": "agent-context/ontology/",
            "source": "subdir",
        },
    }

    ref = observe_graph.data_ref_for_locator(
        data_registry,
        data_type="local_file",
        locator="agent-context/ontology/model.ttl",
    )

    assert ref["artifact_type"] == "document"
    assert ref["resource_kind"] == "file"


def test_artifact_type_inference_distinguishes_machine_hybrid_and_human_artifacts():
    assert (
        observe_graph.infer_artifact_type(
            data_type="local_file",
            locator="agent-context/work-memory/track-record/user-decision/",
        )
        == "event_store"
    )
    assert (
        observe_graph.infer_artifact_type(
            data_type="local_file",
            locator="ontology/shapes/workflow-shapes.ttl",
        )
        == "knowledge_store"
    )
    assert (
        observe_graph.infer_artifact_type(
            data_type="local_file",
            locator="docs/final-report.md",
        )
        == "document"
    )
    assert (
        observe_graph.infer_artifact_type(
            data_type="local_file",
            locator="40.prompt-generation/templates/example-prompt-template.md",
        )
        == "document"
    )
    assert observe_graph.infer_artifact_type(data_type="mcp", locator="mcp://server/resource") == "knowledge_store"
    assert observe_graph.infer_artifact_type(data_type="local_file", locator="exports/final-slide.png") == "media"


def test_artifact_nodes_render_document_and_knowledge_store_shapes():
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

    ontology_dir = BNode()
    graph.add((producer, wf.directory, ontology_dir))
    graph.add((ontology_dir, wf.dirRole, Literal("output")))
    graph.add((ontology_dir, wf.dirPath, Literal("ontology/")))
    graph.add((producer, wf.deliverables, Literal("brief.md")))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo")

    assert '[("KNOWLEDGE STORE\\nid: local_file:ontology/")]' in markdown
    assert '@{ shape: doc, label: "DOCUMENT\\nid: deliverable:' in markdown
    assert "| knowledge_store | Agent | `local_file:ontology/`" in markdown
    assert "| document | Human + Agent | `deliverable:" in markdown


def test_exporter_writes_resource_stream_and_deprecated_alias_outputs(tmp_path):
    workflow_dir = tmp_path / "agent-context" / "workflow"
    workflow_dir.mkdir(parents=True)
    (tmp_path / "agent-context" / "index").mkdir(parents=True)
    (tmp_path / "agent-context" / "index" / "index.yaml").write_text(
        "project:\n  name: Demo\nmodules: []\n",
        encoding="utf-8",
    )
    (workflow_dir / "demo.abox.ttl").write_text(
        """
@prefix wf: <https://mso.dev/ontology/workflow#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<https://mso.dev/ontology/workflow#phase/demo/p> a wf:Phase ;
  rdfs:label "Phase" ;
  wf:hasNode <https://mso.dev/ontology/workflow#node/demo/producer> .

<https://mso.dev/ontology/workflow#node/demo/producer> a wf:Step, wf:Node ;
  rdfs:label "Producer" ;
  wf:directory [
    wf:dirRole "output" ;
    wf:dirPath "ontology/"
  ] .
""".strip(),
        encoding="utf-8",
    )

    subprocess.run([sys.executable, str(SCRIPT), "--root", str(tmp_path)], check=True)

    output_dir = tmp_path / "agent-context" / "observability" / "graph"
    assert (output_dir / "artifact-stream-report.md").exists()
    assert (output_dir / "artifact-stream-views" / "demo.md").exists()
    assert not (output_dir / "resource-stream-report.md").exists()
    assert not (output_dir / "resource-stream-views").exists()
    assert not (output_dir / "data-stream-report.md").exists()
    assert not (output_dir / "data-stream-views").exists()


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
