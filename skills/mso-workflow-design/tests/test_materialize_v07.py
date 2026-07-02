"""materialize_v07 — property chain 파생 테스트 (v0.8.0, ROADMAP §5)."""

import sys
from pathlib import Path

from rdflib import Graph, Literal, RDF, RDFS

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
sys.path.insert(0, str(SCRIPTS))

import materialize_v07  # noqa: E402
from wf_v07 import WF  # noqa: E402


def chain_graph(*, same_artifact: bool = False, explicit_evidence: bool = False) -> Graph:
    """Artifact --consumed_by--> Execution --produces_to--> Artifact 최소 그래프."""
    g = Graph()
    execution = WF["node/t/run"]
    src = WF["artifact/t/in"]
    out = src if same_artifact else WF["artifact/t/out"]

    g.add((execution, RDF.type, WF.Task))
    g.add((execution, RDF.type, WF.Execution))
    g.add((execution, RDF.type, WF.Node))
    g.add((execution, RDFS.label, Literal("실행")))
    for artifact, locator in ((src, "in.jsonl"), (out, "out.md")):
        g.add((artifact, RDF.type, WF.Artifact))
        g.add((artifact, RDF.type, WF.Node))
        g.add((artifact, WF.locator, Literal(locator)))

    consumed = WF["stream/t/in__consumed_by__run"]
    g.add((consumed, RDF.type, WF.Stream))
    g.add((consumed, WF["from"], src))
    g.add((consumed, WF.to, execution))
    g.add((consumed, WF.streamType, Literal("consumed_by")))

    produced = WF["stream/t/run__produces_to__out"]
    g.add((produced, RDF.type, WF.Stream))
    g.add((produced, WF["from"], execution))
    g.add((produced, WF.to, out))
    g.add((produced, WF.streamType, Literal("produces_to")))

    if explicit_evidence:
        explicit = WF["stream/t/in__evidence_of__out"]
        g.add((explicit, RDF.type, WF.Stream))
        g.add((explicit, WF["from"], src))
        g.add((explicit, WF.to, out))
        g.add((explicit, WF.streamType, Literal("evidence_of")))
    return g


def test_chain_derives_evidence_of_with_provenance():
    g = chain_graph()
    inferred = materialize_v07.materialize(g)
    derived = [s for s in inferred.subjects(RDF.type, WF.Stream)]
    assert len(derived) == 1
    stream = derived[0]
    assert inferred.value(stream, WF.streamType) == Literal("evidence_of")
    assert str(inferred.value(stream, WF.derived)) == "true"          # D-18
    origins = set(inferred.objects(stream, WF.derivedFrom))
    assert len(origins) == 2                                          # 원본 2개 provenance
    # 술어 projection 동봉 (D-17 OWL interop)
    assert (WF["artifact/t/in"], WF.evidence_of, WF["artifact/t/out"]) in inferred
    assert (WF["artifact/t/in"], WF.consumed_by, WF["node/t/run"]) in inferred


def test_explicit_evidence_suppresses_derivation():
    """명시 선언 우선 (D-20)."""
    g = chain_graph(explicit_evidence=True)
    inferred = materialize_v07.materialize(g)
    assert not list(inferred.subjects(RDF.type, WF.Stream))


def test_same_artifact_chain_is_skipped():
    """같은 artifact를 읽고 쓰는 실행은 자기근거를 만들지 않는다."""
    g = chain_graph(same_artifact=True)
    inferred = materialize_v07.materialize(g)
    assert not list(inferred.subjects(RDF.type, WF.Stream))


def test_materialize_file_idempotent(tmp_path):
    src = ASSETS / "examples" / "root-workflow.v07.abox.ttl"
    work = tmp_path / "workflow-x.abox.ttl"
    work.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    written1, count1 = materialize_v07.materialize_file(work)
    written2, count2 = materialize_v07.materialize_file(work)
    assert written1 == written2
    assert count1 == count2 > 0
    assert written1.name == "workflow-x.inferred.ttl"


def test_derived_edge_renders_with_star():
    """관측 표기 D-21: 파생 edge는 evidence_of* 로 구분."""
    obs_scripts = SCRIPTS.parent.parent / "mso-graph-observability" / "scripts"
    sys.path.insert(0, str(obs_scripts))
    import observe_v07  # noqa: E402

    g = chain_graph()
    inferred = materialize_v07.materialize(g)
    merged = g + inferred
    workflow = WF["workflow/t"]
    merged.add((workflow, RDF.type, WF.Workflow))
    merged.add((workflow, WF.workflowType, Literal("base")))
    merged.add((workflow, WF.has, WF["node/t/run"]))
    md = observe_v07.build_view(merged, workflow, "t", "artifact-stream")
    assert "evidence_of*" in md
    assert "-->|consumed_by|" in md
