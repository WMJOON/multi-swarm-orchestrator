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
    assert "subgraph workflow_demo_p_" in markdown
    assert "legacy_phase" not in markdown
    assert "workflow_phase" not in markdown
    assert "-->|hasNode|" not in markdown
    assert "-->|hasBranch|" not in markdown
    assert "Branch" not in markdown
    assert "((start))" in markdown
    assert "((end))" in markdown
    assert '["A<br>id: a<br>Step"]' in markdown
    assert '{{"Gate<br>id: d<br>Decision"}}' in markdown


def test_oracle_view_normalizes_phase_target_ids_to_workflow():
    graph = Graph()
    wf = observe_graph.WF
    eval_node = wf["node/demo/eval"]
    phase = wf["phase/demo/p"]

    graph.add((eval_node, RDF.type, wf.Eval))
    graph.add((eval_node, RDFS.label, Literal("Eval")))
    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("Phase")))
    graph.add((eval_node, wf.target, phase))

    markdown = observe_graph.build_oracle_view(graph)

    assert "--o|target|" in markdown
    assert "o_workflow_demo_p_" in markdown
    assert "o_phase" not in markdown
    assert "o_workflow_phase" not in markdown


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

    assert '@{ shape: doc, label: "generated/results/<br>DOCUMENT" }' in markdown
    assert "## Artifact Node Index" in markdown
    assert "| Artifact Type | Primary Consumer | Id | Medium | Location | Locator | Detail |" in markdown
    assert "`generated/results/`" in markdown
    assert "-.->|produces|" in markdown
    assert "-.->|consumes|" in markdown
    assert "boundary_start_demo_start_" in markdown
    assert "boundary_end_demo_end_" in markdown
    assert "-->|next|" in markdown
    assert any(
        "boundary_start_demo_start_" in line and "-->|next|" in line and "step_node_demo_producer_" in line
        for line in markdown.splitlines()
    )
    assert not any(
        "step_node_demo_producer_" in line and "-->|next|" in line and "step_node_demo_consumer_" in line
        for line in markdown.splitlines()
    )
    assert any(
        "step_node_demo_consumer_" in line and "-->|next|" in line and "boundary_end_demo_end_" in line
        for line in markdown.splitlines()
    )
    assert "report.md<br>DOCUMENT" in markdown
    assert "report.md" in markdown
    assert "classDef document" in markdown
    assert "classDef knowledge_store" in markdown


def test_step_with_deliverable_and_tool_remains_agent_task():
    """A produced artifact is not a branch; tool delegation stays attached to the Step."""
    graph = Graph()
    wf = observe_graph.WF
    step = wf["node/demo/nlu-s-101"]
    next_step = wf["node/demo/nlu-v-101"]
    phase = wf["phase/demo/p"]

    for node, label in ((step, "라운드 실행"), (next_step, "검증")):
        graph.add((node, RDF.type, wf.Step))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((phase, wf.hasNode, node))
    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("NLU")))
    graph.add((step, wf.next, next_step))
    graph.add((step, wf.deliverables, Literal("data/labeling.db#labels")))
    graph.add((step, wf.usesTool, Literal("[[nlu engine process]]")))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", view="workflow")

    assert "step_node_demo_nlu_s_101_" in markdown
    assert "Decision / inferred-branch" not in markdown
    assert "nlu engine process<br>TOOL" in markdown
    assert "-.->|delegates_to|" in markdown
    assert "|target|" not in markdown


def test_tool_step_can_consume_and_produce_same_table_without_internal_scripts():
    graph = Graph()
    wf = observe_graph.WF
    step = wf["node/demo/nlu-s-101"]
    phase = wf["phase/demo/p"]

    graph.add((step, RDF.type, wf.Step))
    graph.add((step, RDF.type, wf.Node))
    graph.add((step, RDFS.label, Literal("라운드 실행")))
    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("NLU")))
    graph.add((phase, wf.hasNode, step))
    graph.add((step, wf.usesTool, Literal("[[nlu engine process]]")))

    table_dir = BNode()
    graph.add((step, wf.directory, table_dir))
    graph.add((table_dir, wf.dirRole, Literal("input_output")))
    graph.add((table_dir, wf.dirPath, Literal("data/labeling.db#labels")))

    scripts_dir = BNode()
    graph.add((step, wf.directory, scripts_dir))
    graph.add((scripts_dir, wf.dirRole, Literal("implementation")))
    graph.add((scripts_dir, wf.dirPath, Literal("scripts/")))

    data_registry = {
        "data/": {
            "id": "demo.data",
            "data_type": "local_file",
            "locator": "data/",
            "artifact_type": "local_database",
        }
    }

    markdown = observe_graph.build_workflow_topology(
        graph,
        scope="demo",
        data_registry=data_registry,
        view="artifact-stream",
    )

    assert "labeling.db#labels<br>TABLE" in markdown
    assert "demo.data" not in markdown
    assert "nlu engine process<br>TOOL" in markdown
    assert any(
        "labeling.db#labels" not in line
        and "data_local_file_data_labeling_db_labels_" in line
        and "-.->|consumes|" in line
        and "data_local_file___nlu_engine_process_" in line
        for line in markdown.splitlines()
    )
    assert any(
        "data_local_file___nlu_engine_process_" in line
        and "-.->|produces|" in line
        and "data_local_file_data_labeling_db_labels_" in line
        for line in markdown.splitlines()
    )
    assert "scripts/<br>" not in markdown


def test_step_with_multiple_control_targets_is_marked_as_shape_violation():
    graph = Graph()
    wf = observe_graph.WF
    step = wf["node/demo/nlu-s-104"]
    target_a = wf["node/demo/a"]
    target_b = wf["node/demo/b"]
    phase = wf["phase/demo/p"]

    for node, label in ((step, "분기"), (target_a, "A"), (target_b, "B")):
        graph.add((node, RDF.type, wf.Step))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((phase, wf.hasNode, node))
    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("NLU")))
    graph.add((step, wf.next, target_a))
    graph.add((step, wf.next, target_b))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", view="workflow")

    # 관측기는 Step을 Decision으로 승격하지 않는다 — 위반 표기만 한다.
    assert "Decision / inferred-branch" not in markdown
    assert "multi-outgoing" in markdown
    assert "model as wf:Decision" in markdown
    assert "shape_violation" in markdown


def test_eval_tool_target_validates_tool_outputs_and_approves_next_task():
    graph = Graph()
    wf = observe_graph.WF
    producer = wf["node/demo/nlu-s-101"]
    eval_node = wf["node/demo/eval"]
    next_task = wf["node/demo/fix"]
    phase = wf["phase/demo/p"]

    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("NLU")))
    for node, cls, label in (
        (producer, wf.Step, "라벨링"),
        (eval_node, wf.Eval, "검수"),
        (next_task, wf.Step, "수정"),
    ):
        graph.add((node, RDF.type, cls))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((phase, wf.hasNode, node))
    graph.add((producer, wf.usesTool, Literal("[[nlu engine process]]")))
    graph.add((producer, wf.deliverables, Literal("data/labeling.db#labels")))
    graph.add((eval_node, wf.targetArtifact, Literal("[[nlu engine process]]")))
    graph.add((eval_node, wf.orderTarget, Literal("fix")))
    graph.add((eval_node, wf.next, next_task))
    graph.add((next_task, wf.targetArtifact, Literal("[[nlu engine process]]")))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", view="workflow")

    assert "nlu engine process<br>TOOL" in markdown
    assert "-->|target|" in markdown
    assert "labeling.db#labels<br>TABLE" in markdown
    assert "-.->|measured_by|" in markdown
    assert "eval_node_demo_eval_" in markdown
    assert "step_node_demo_fix_" in markdown
    assert "-->|requests_revision|" in markdown
    assert any(
        "step_node_demo_fix_" in line and "-->|target|" in line and "data_local_file___nlu_engine_process_" in line
        for line in markdown.splitlines()
    )
    assert not any(
        "data_local_file___nlu_engine_process_" in line and "|validated_by|" in line and "eval_node_demo_eval_" in line
        for line in markdown.splitlines()
    )
    assert not any(
        "eval_node_demo_eval_" in line and "|approves|" in line and "data_local_file___nlu_engine_process_" in line
        for line in markdown.splitlines()
    )


def test_eval_target_artifact_reuses_target_workflow_produced_deliverable():
    graph = Graph()
    wf = observe_graph.WF
    producer = wf["node/demo/gby-s-006"]
    eval_node = wf["node/demo/gby-o-001"]
    workflow = wf["phase/demo/settle"]
    deliverable = "campaign SETTLED (trajectory 로그 append, 원장 대사 완료)"

    graph.add((workflow, RDF.type, wf.Phase))
    graph.add((workflow, RDFS.label, Literal("Settlement")))
    for node, cls, label in (
        (producer, wf.Step, "정산 완료 처리"),
        (eval_node, wf.Eval, "Settlement Oracle"),
    ):
        graph.add((node, RDF.type, cls))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((workflow, wf.hasNode, node))
    graph.add((producer, wf.deliverables, Literal(deliverable)))
    graph.add((eval_node, wf.target, workflow))
    graph.add((eval_node, wf.targetArtifact, Literal(deliverable)))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", view="workflow")
    produced_ref = observe_graph.deliverable_data_ref(deliverable)
    produced_node_id = observe_graph.data_id(produced_ref["id"])

    assert any(
        f"{produced_node_id} -.->|measured_by| eval_node_demo_gby_o_001_" in line
        for line in markdown.splitlines()
    )
    assert "data_local_file_campaign_SETTLED_" not in markdown


def test_eval_target_artifact_reuses_explicit_produced_artifact():
    graph = Graph()
    wf = observe_graph.WF
    producer = wf["node/demo/ccw-d-010"]
    eval_node = wf["node/demo/ccw-o-010"]
    workflow = wf["phase/demo/source_and_style"]
    artifact = wf["artifact/demo/text-policy-selection"]
    label = "text policy selection"

    graph.add((workflow, RDF.type, wf.Phase))
    graph.add((workflow, RDFS.label, Literal("Source and Style")))
    for node, cls, node_label in (
        (producer, wf.Decision, "Text policy gate"),
        (eval_node, wf.Eval, "Text policy oracle"),
    ):
        graph.add((node, RDF.type, cls))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(node_label)))
        graph.add((workflow, wf.hasNode, node))
    graph.add((artifact, RDF.type, wf.Artifact))
    graph.add((artifact, RDFS.label, Literal(label)))
    graph.add((producer, wf.produces, artifact))
    graph.add((artifact, wf.measures, eval_node))
    graph.add((eval_node, wf.target, workflow))
    graph.add((eval_node, wf.targetArtifact, Literal(label)))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", view="workflow")
    artifact_node_id = observe_graph.data_id(observe_graph.artifact_node_data_ref(graph, artifact)["id"])
    measured_lines = [
        line for line in markdown.splitlines()
        if f"-.->|measured_by| eval_node_demo_ccw_o_010_" in line
    ]

    assert any(line.startswith(f"  {artifact_node_id} ") for line in measured_lines)
    assert len(measured_lines) == 1
    assert "data_local_file_text_policy_selection" not in markdown


def test_eval_multiple_target_artifacts_render_all_measured_by_edges():
    graph = Graph()
    wf = observe_graph.WF
    workflow = wf["phase/demo/development"]
    producer_a = wf["node/demo/rmp-s-001"]
    producer_b = wf["node/demo/rmp-s-002"]
    eval_node = wf["node/demo/rmp-v-002"]
    artifact_a = "상태 테이블, append-only trajectory 로그, 멱등키 컬럼"
    artifact_b = "얇은 오케스트레이터, 무상태 워커 계약 인터페이스"

    graph.add((workflow, RDF.type, wf.Phase))
    graph.add((workflow, RDFS.label, Literal("Development")))
    for node, cls, label in (
        (producer_a, wf.Step, "Foundation"),
        (producer_b, wf.Step, "Orchestration"),
        (eval_node, wf.Eval, "Workflow shape eval"),
    ):
        graph.add((node, RDF.type, cls))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((workflow, wf.hasNode, node))
    graph.add((producer_a, wf.deliverables, Literal(artifact_a)))
    graph.add((producer_b, wf.deliverables, Literal(artifact_b)))
    graph.add((eval_node, wf.target, workflow))
    graph.add((eval_node, wf.targetArtifact, Literal(artifact_a)))
    graph.add((eval_node, wf.targetArtifact, Literal(artifact_b)))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", view="workflow")
    measured_lines = [
        line for line in markdown.splitlines()
        if "-.->|measured_by| eval_node_demo_rmp_v_002_" in line
    ]

    assert len(measured_lines) == 2
    assert observe_graph.data_id(observe_graph.deliverable_data_ref(artifact_a)["id"]) in measured_lines[0] + measured_lines[1]
    assert observe_graph.data_id(observe_graph.deliverable_data_ref(artifact_b)["id"]) in measured_lines[0] + measured_lines[1]


def test_eval_without_next_does_not_invent_approval_edge():
    graph = Graph()
    wf = observe_graph.WF
    eval_node = wf["node/demo/eval"]
    phase = wf["phase/demo/p"]

    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("NLU")))
    graph.add((eval_node, RDF.type, wf.Eval))
    graph.add((eval_node, RDF.type, wf.Node))
    graph.add((eval_node, RDFS.label, Literal("검수")))
    graph.add((phase, wf.hasNode, eval_node))
    graph.add((eval_node, wf.targetArtifact, Literal("[[nlu engine process]]")))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", view="workflow")

    assert "boundary_end_demo_end_" in markdown
    assert not any(
        "eval_node_demo_eval_" in line and "-->|approves|" in line
        for line in markdown.splitlines()
    )
    assert not any(
        "eval_node_demo_eval_" in line and "-->|next|" in line and "boundary_end_demo_end_" in line
        for line in markdown.splitlines()
    )


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
    assert "-.->|consumes|" not in workflow
    assert "-.->|produces|" not in workflow

    assert "`artifact-stream` view" in artifact_stream
    assert "generated/results/<br>DOCUMENT" in artifact_stream
    assert "-.->|consumes|" in artifact_stream
    assert "-.->|produces|" in artifact_stream
    assert "((start))" not in artifact_stream
    assert "-->|next|" not in artifact_stream


def test_artifact_stream_omits_control_edges_between_declared_stream_nodes():
    graph = Graph()
    wf = observe_graph.WF
    producer = wf["node/demo/producer"]
    decision = wf["node/demo/decision"]
    consumer = wf["node/demo/consumer"]
    phase = wf["phase/demo/p"]
    branch = wf["node/demo/decision_branch_approved_consumer"]

    for node, cls, label in (
        (producer, wf.Step, "Produce"),
        (decision, wf.Decision, "Gate"),
        (consumer, wf.Step, "Consume"),
    ):
        graph.add((node, RDF.type, cls))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((phase, wf.hasNode, node))
    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("Phase")))

    output_dir = BNode()
    graph.add((producer, wf.directory, output_dir))
    graph.add((output_dir, wf.dirRole, Literal("output")))
    graph.add((output_dir, wf.dirPath, Literal("generated/results/")))

    decision_input = BNode()
    graph.add((decision, wf.directory, decision_input))
    graph.add((decision_input, wf.dirRole, Literal("input")))
    graph.add((decision_input, wf.dirPath, Literal("generated/results/")))

    consumer_input = BNode()
    graph.add((consumer, wf.directory, consumer_input))
    graph.add((consumer_input, wf.dirRole, Literal("input")))
    graph.add((consumer_input, wf.dirPath, Literal("generated/results/")))

    graph.add((producer, wf.next, decision))
    graph.add((decision, wf.next, consumer))
    graph.add((decision, wf.hasBranch, branch))
    graph.add((branch, RDF.type, wf.Branch))
    graph.add((branch, wf.on, Literal("approved")))
    graph.add((branch, wf.gotoNode, consumer))

    artifact_stream = observe_graph.build_workflow_topology(graph, scope="demo", view="artifact-stream")

    assert "step_node_demo_producer_" in artifact_stream
    assert "decision_node_demo_decision_" in artifact_stream
    assert "step_node_demo_consumer_" in artifact_stream
    assert "-.->|consumes|" in artifact_stream
    assert "-.->|produces|" in artifact_stream
    assert "-->|next|" not in artifact_stream
    assert "|on: approved|" not in artifact_stream
    assert "((end))" not in artifact_stream


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


def test_artifact_object_edges_render_and_clear_unconsumed_report():
    graph = Graph()
    wf = observe_graph.WF
    producer = wf["node/demo/cur-s-001"]
    consumer = wf["node/demo/cur-s-002"]
    artifact = wf["artifact/demo/vendor-url-list"]
    phase = wf["phase/demo/p"]

    for node, label in ((producer, "크롤 대상 allow-list 로드"), (consumer, "W1 크롤 실행")):
        graph.add((node, RDF.type, wf.Step))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((phase, wf.hasNode, node))
    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("Curation")))
    graph.add((artifact, RDF.type, wf.Artifact))
    graph.add((artifact, RDFS.label, Literal("벤더 URL 목록 (화이트리스트)")))
    graph.add((producer, wf.produces, artifact))
    graph.add((artifact, wf.consumes, consumer))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", view="artifact-stream")
    report = observe_graph.build_data_stream_report(graph)
    artifact_id = observe_graph.data_id(observe_graph.artifact_node_data_ref(graph, artifact)["id"])

    assert "벤더 URL 목록 (화이트리스트)<br>DOCUMENT" in markdown
    assert any(
        f"step_node_demo_cur_s_001_" in line and f"-.->|produces| {artifact_id}" in line
        for line in markdown.splitlines()
    )
    assert any(
        f"{artifact_id} -.->|consumes| step_node_demo_cur_s_002_" in line
        for line in markdown.splitlines()
    )
    assert "Produced but unconsumed artifacts: 0" in report


def test_artifact_measures_eval_renders_measured_by_and_clears_unconsumed_report():
    graph = Graph()
    wf = observe_graph.WF
    producer = wf["node/demo/s-001"]
    evaluator = wf["node/demo/o-001"]
    artifact = wf["artifact/demo/campaign-settled"]
    phase = wf["phase/demo/p"]

    graph.add((producer, RDF.type, wf.Step))
    graph.add((producer, RDF.type, wf.Node))
    graph.add((producer, RDFS.label, Literal("SETTLED 산출")))
    graph.add((evaluator, RDF.type, wf.Eval))
    graph.add((evaluator, RDF.type, wf.Node))
    graph.add((evaluator, RDFS.label, Literal("Oracle 평가")))
    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("Groupbuy")))
    graph.add((phase, wf.hasNode, producer))
    graph.add((phase, wf.hasNode, evaluator))
    graph.add((artifact, RDF.type, wf.Artifact))
    graph.add((artifact, RDFS.label, Literal("campaign SETTLED")))
    graph.add((producer, wf.produces, artifact))
    graph.add((artifact, wf.measures, evaluator))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", view="artifact-stream")
    report = observe_graph.build_data_stream_report(graph)
    artifact_id = observe_graph.data_id(observe_graph.artifact_node_data_ref(graph, artifact)["id"])

    assert f"{artifact_id} -.->|measured_by|" in markdown
    assert f"{artifact_id} -.->|consumes|" not in markdown
    assert "Produced but unconsumed artifacts: 0" in report


def test_validation_node_renders_as_validation_not_generic_node():
    graph = Graph()
    wf = observe_graph.WF
    workflow = wf["phase/demo/validation"]
    validation = wf["node/demo/v-001"]
    next_step = wf["node/demo/s-001"]

    graph.add((workflow, RDF.type, wf.Workflow))
    graph.add((workflow, RDFS.label, Literal("Validation")))
    graph.add((workflow, wf.hasNode, validation))
    graph.add((workflow, wf.hasNode, next_step))
    graph.add((validation, RDF.type, wf.Node))
    graph.add((validation, RDF.type, wf.Task))
    graph.add((validation, RDF.type, wf.Validation))
    graph.add((validation, RDFS.label, Literal("workflow schema validation")))
    graph.add((validation, wf.status, Literal("pending")))
    graph.add((validation, wf.next, next_step))
    graph.add((next_step, RDF.type, wf.Node))
    graph.add((next_step, RDF.type, wf.Step))
    graph.add((next_step, RDFS.label, Literal("next task")))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", view="workflow")

    assert "validation_node_demo_v_001_" in markdown
    assert "class validation_node_demo_v_001_" in markdown
    assert "node_node_demo_v_001_" not in markdown
    assert "validation_node_demo_v_001_" in markdown and "-->|next| step_node_demo_s_001_" in markdown


def test_artifact_object_consumer_with_tool_renders_tool_actor():
    graph = Graph()
    wf = observe_graph.WF
    producer = wf["node/demo/cur-s-001"]
    consumer = wf["node/demo/cur-s-002"]
    artifact = wf["artifact/demo/vendor-url-list"]
    phase = wf["phase/demo/p"]
    tool = "[[curation crawler agent]]"

    for node, label in ((producer, "크롤 대상 allow-list 로드"), (consumer, "W1 크롤 실행")):
        graph.add((node, RDF.type, wf.Step))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((phase, wf.hasNode, node))
    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("Curation")))
    graph.add((artifact, RDF.type, wf.Artifact))
    graph.add((artifact, RDFS.label, Literal("벤더 URL 목록 (화이트리스트)")))
    graph.add((producer, wf.produces, artifact))
    graph.add((artifact, wf.consumes, consumer))
    graph.add((consumer, wf.usesTool, Literal(tool)))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo", view="artifact-stream")
    artifact_id = observe_graph.data_id(observe_graph.artifact_node_data_ref(graph, artifact)["id"])
    tool_ref = observe_graph.tool_data_ref({}, tool)
    tool_id = observe_graph.data_id(tool_ref["id"])

    assert "curation crawler agent<br>TOOL" in markdown
    assert f"{artifact_id} -.->|consumes| {tool_id}" in markdown
    assert f"-.->|consumes| step_node_demo_cur_s_002_" not in markdown
    assert "-.->|delegates_to|" in markdown


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

    assert "`content.draft`" in markdown
    assert markdown.count('@{ shape: doc, label: "content/draft/<br>DOCUMENT" }') == 1
    assert "`index:content.draft`" in markdown
    assert "`content/draft/`" in markdown
    assert "-.->|produces|" in markdown
    assert markdown.count("-.->|produces|") == 1


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

    assert '[("ontology/<br>KNOWLEDGE STORE")]' in markdown
    assert '@{ shape: doc, label: "brief.md<br>DOCUMENT" }' in markdown
    assert "| knowledge_store | Agent | `local_file:ontology/`" in markdown
    assert "| document | Human + Agent | `deliverable:" in markdown


def test_exporter_writes_per_workflow_graph_outputs_and_deprecated_aliases_absent(tmp_path):
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
    report_dir = tmp_path / "agent-context" / "observability"
    # 출력 규약 (2026-07-02): 리포트는 observability/, 시각화는 observability/graph/
    assert (report_dir / "artifact-stream-report.md").exists()
    assert (report_dir / "workflow-ssot-report.md").exists()
    assert not (output_dir / "artifact-stream-report.md").exists()
    assert (output_dir / "demo" / "repository-graph.md").exists()
    assert (output_dir / "demo" / "workflow-graph.md").exists()
    assert (output_dir / "demo" / "artifact-stream-graph.md").exists()
    assert not (output_dir / "workflow-topology.md").exists()
    assert not (output_dir / "workflow-subgraphs").exists()
    assert not (output_dir / "workflow-views").exists()
    assert not (output_dir / "artifact-stream-views").exists()
    assert not (output_dir / "resource-stream-report.md").exists()
    assert not (output_dir / "resource-stream-views").exists()
    assert not (output_dir / "data-stream-report.md").exists()
    assert not (output_dir / "data-stream-views").exists()


def test_workflow_ssot_report_treats_yaml_as_legacy_migration_input(tmp_path):
    workflow_dir = tmp_path / "agent-context" / "workflow"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "workflow-ready.yaml").write_text("id: ready\n", encoding="utf-8")
    (workflow_dir / "workflow-ready.abox.ttl").write_text("", encoding="utf-8")
    (workflow_dir / "workflow-blocked.yaml").write_text("id: blocked\n", encoding="utf-8")
    (workflow_dir / "workflow-ttl-only.abox.ttl").write_text("", encoding="utf-8")
    references = workflow_dir / "references" / "schemas"
    references.mkdir(parents=True)
    (references / "step.schema.yaml").write_text("name: step\n", encoding="utf-8")

    state = observe_graph.workflow_ssot_state(workflow_dir)
    graph = Graph()
    wf = observe_graph.WF
    ref = wf["phase/demo_wref_module"]
    graph.add((ref, RDF.type, wf.WorkflowRef))
    graph.add((ref, wf.ref, Literal("../module/workflow/module-workflow-00.yaml#testing")))

    report, legacy_count = observe_graph.build_workflow_ssot_report(workflow_dir, graph)

    assert legacy_count == 3
    assert state["yaml"] == [
        workflow_dir / "workflow-blocked.yaml",
        workflow_dir / "workflow-ready.yaml",
    ]
    assert state["yaml_with_abox"] == [workflow_dir / "workflow-ready.yaml"]
    assert state["yaml_without_abox"] == [workflow_dir / "workflow-blocked.yaml"]
    assert "Legacy workflow YAML files remaining: 2" in report
    assert "Legacy YAML ready to remove (sibling TTL exists): 1" in report
    assert "Migration blockers (legacy YAML without sibling TTL): 1" in report
    assert "Legacy YAML references inside TTL: 1" in report
    assert "`workflow-ready.yaml`" in report
    assert "`workflow-blocked.yaml`" in report
    assert "`../module/workflow/module-workflow-00.yaml#testing`" in report
    assert "step.schema.yaml" not in report
    assert "After migration, remove the YAML" in report


def test_workflow_subgraph_renders_eval_shape():
    graph = Graph()
    wf = observe_graph.WF
    task = wf["node/demo/task"]
    eval_node = wf["node/demo/eval"]
    phase = wf["phase/demo/p"]

    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("Phase")))
    for node, cls, label in ((task, wf.Step, "Task"), (eval_node, wf.Eval, "Quality Gate")):
        graph.add((node, RDF.type, cls))
        graph.add((node, RDF.type, wf.Node))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((phase, wf.hasNode, node))
    graph.add((task, wf.next, eval_node))

    markdown = observe_graph.build_workflow_topology(graph, scope="demo")

    assert '["Task<br>id: task<br>Step"]' in markdown
    assert '[/"Quality Gate<br>id: eval<br>Eval"/]' in markdown
    assert "-->|next|" in markdown
    assert "classDef eval" in markdown


def test_explicit_ttl_artifact_type_overrides_inference():
    graph = Graph()
    wf = observe_graph.WF
    step = wf["node/demo/at-s-001"]
    phase = wf["phase/demo/p"]
    directory = wf["node/demo/at-s-001_dir_out"]

    graph.add((phase, RDF.type, wf.Phase))
    graph.add((phase, RDFS.label, Literal("AT")))
    graph.add((phase, wf.hasNode, step))
    graph.add((step, RDF.type, wf.Step))
    graph.add((step, RDF.type, wf.Node))
    graph.add((step, RDFS.label, Literal("산출")))
    graph.add((step, wf.directory, directory))
    graph.add((directory, wf.dirPath, Literal("out/report.md")))
    graph.add((directory, wf.dirRole, Literal("output")))
    # 추론이라면 .md → document. TTL 명시 선언이 이겨야 한다.
    graph.add((directory, wf.artifactType, Literal("knowledge_store")))

    items = observe_graph.directory_data_for_node(graph, step)
    assert items == [("output", "out/report.md", "local_file:out/report.md", "knowledge_store")]

    ref = observe_graph.apply_explicit_artifact_type(
        observe_graph.data_ref_for_locator({}, data_type="local_file", locator="out/report.md"),
        "knowledge_store",
    )
    assert ref["artifact_type"] == "knowledge_store"
    assert ref["resource_kind"] == "data"


def test_invalid_explicit_artifact_type_falls_back_to_inference():
    graph = Graph()
    wf = observe_graph.WF
    directory = wf["node/demo/at-s-002_dir_out"]
    graph.add((directory, wf.dirPath, Literal("out/report.md")))
    graph.add((directory, wf.dirRole, Literal("output")))
    graph.add((directory, wf.artifactType, Literal("nonsense_type")))

    assert observe_graph.explicit_artifact_type(graph, directory) == ""
    ref = observe_graph.apply_explicit_artifact_type(
        observe_graph.data_ref_for_locator({}, data_type="local_file", locator="out/report.md"),
        "",
    )
    assert ref["artifact_type"] == "document"  # .md 추론 유지
