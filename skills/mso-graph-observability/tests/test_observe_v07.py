"""observe_v07 — v0.7 Rail/Stream 네이티브 렌더러 테스트."""

import sys
from pathlib import Path

from rdflib import Graph, Literal, RDF, RDFS

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import observe_v07  # noqa: E402
from observe_v07 import WF  # noqa: E402

EXAMPLE_V07 = (
    Path(__file__).resolve().parent.parent.parent
    / "mso-workflow-design" / "assets" / "examples" / "root-workflow.v07.abox.ttl"
)


def example_graph() -> Graph:
    g = Graph()
    g.parse(str(EXAMPLE_V07), format="turtle")
    return g


def synthetic_delegation_graph() -> Graph:
    """Artifact --reads--> Task --delegates_to--> Executor(realizedBy Workflow) 합성."""
    g = Graph()
    workflow = WF["workflow/t"]
    skill_wf = WF["workflow/skill-x"]
    task = WF["node/t/a"]
    start = WF["node/t/start"]
    end = WF["node/t/end"]
    artifact = WF["artifact/t/in"]
    out_artifact = WF["artifact/t/out"]
    executor = WF["node/t/a__exec_skill-x"]

    g.add((workflow, RDF.type, WF.Workflow))
    g.add((workflow, WF.workflowType, Literal("base")))
    g.add((workflow, RDFS.label, Literal("T")))
    for node, cls in ((start, WF.Start), (end, WF.End)):
        g.add((node, RDF.type, cls))
        g.add((node, RDF.type, WF.Node))
        g.add((workflow, WF.has, node))
    g.add((task, RDF.type, WF.Task))
    g.add((task, RDF.type, WF.Execution))
    g.add((task, RDF.type, WF.Node))
    g.add((task, RDFS.label, Literal("작업")))
    g.add((workflow, WF.has, task))
    for a, locator, atype in (
        (artifact, "data/in.jsonl", "event_store"),
        (out_artifact, "out/report.md", "document"),
    ):
        g.add((a, RDF.type, WF.Artifact))
        g.add((a, RDF.type, WF.Node))
        g.add((a, WF.locator, Literal(locator)))
        g.add((a, RDFS.label, Literal(locator)))
        g.add((a, WF.artifactType, Literal(atype)))
        g.add((workflow, WF.has, a))
    g.add((executor, RDF.type, WF.Execution))
    g.add((executor, RDF.type, WF.Node))
    g.add((executor, RDFS.label, Literal("skill-x")))
    g.add((executor, WF.hasSubject, Literal("workflow")))
    g.add((executor, WF.realizedBy, skill_wf))
    g.add((workflow, WF.has, executor))
    g.add((skill_wf, RDF.type, WF.Workflow))
    g.add((skill_wf, RDFS.label, Literal("Skill X")))

    def rail(name, source, target, rail_type, on=None):
        uri = WF[f"rail/t/{name}"]
        g.add((uri, RDF.type, WF.Rail))
        g.add((uri, WF["from"], source))
        g.add((uri, WF.to, target))
        g.add((uri, WF.railType, Literal(rail_type)))
        if on:
            g.add((uri, WF.on, Literal(on)))
        return uri

    def stream(name, source, target, stream_type):
        uri = WF[f"stream/t/{name}"]
        g.add((uri, RDF.type, WF.Stream))
        g.add((uri, WF["from"], source))
        g.add((uri, WF.to, target))
        g.add((uri, WF.streamType, Literal(stream_type)))
        return uri

    rail("s__a", start, task, "default")
    rail("a__end", task, end, "default")
    rail("in__a", artifact, task, "reads")
    rail("a__x", task, executor, "delegates_to")
    stream("in__x", artifact, executor, "consumed_by")
    stream("x__out", executor, out_artifact, "produces_to")
    stream("out__in", out_artifact, artifact, "evidence_of")
    return g


def test_v07_workflow_scope_uses_last_uri_segment():
    g = example_graph()
    scopes = set(observe_v07.v07_workflows(g).values())
    assert scopes == {"development", "development-oracle", "discovery", "testing"}


def test_workflow_view_renders_start_end_and_branches():
    g = example_graph()
    wfs = observe_v07.v07_workflows(g)
    oracle = next(u for u, s in wfs.items() if s == "development-oracle")
    md = observe_v07.build_view(g, oracle, "development-oracle", "workflow")
    assert '(("start")):::start' in md
    assert '(("end")):::end_' in md
    assert "on: fail" in md and "on: pass" in md
    assert "Eval" in md
    assert "-->|evolves_to|" in md
    assert "v0.7 native" in md


def test_stream_view_only_streams_and_explicit_artifact_type():
    g = example_graph()
    wfs = observe_v07.v07_workflows(g)
    dev = next(u for u, s in wfs.items() if s == "development")
    md = observe_v07.build_view(g, dev, "development", "artifact-stream")
    assert "consumed_by" in md or "produces_to" in md
    assert "evolves_to" not in md  # rail은 stream 뷰에서 제외
    # 명시 artifactType 없는 artifact는 추론하지 않고 unspecified
    assert "unspecified" in md


def test_delegation_pair_renders_reads_and_executor():
    g = synthetic_delegation_graph()
    workflow = WF["workflow/t"]
    md = observe_v07.build_view(g, workflow, "t", "repository")
    assert "-.->|reads|" in md
    assert "-.->|delegates_to|" in md
    assert "subject: workflow" in md and "[[" in md
    assert "-.->|realizedBy|" in md  # Skill = sub-workflow 링크
    assert "-->|consumed_by|" in md
    assert "-->|produces_to|" in md
    assert "-.->|evidence_of|" in md
    # 명시 artifactType 렌더 (추론 아님)
    assert "EVENT_STORE" in md.upper()


def test_workflow_view_excludes_streams():
    g = synthetic_delegation_graph()
    md = observe_v07.build_view(g, WF["workflow/t"], "t", "workflow")
    assert "-.->|reads|" in md            # Rail은 포함
    assert "consumed_by" not in md        # Stream은 제외
    assert "produces_to" not in md
