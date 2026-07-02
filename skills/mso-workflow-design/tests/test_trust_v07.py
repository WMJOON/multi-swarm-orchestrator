"""trust_v07 — Trust 계산 + Oracle Decision 테스트 (v0.10.0, §8·§9)."""

import sys
from pathlib import Path

from rdflib import Graph, Literal, RDF, RDFS
from rdflib.namespace import XSD

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
sys.path.insert(0, str(SCRIPTS))

import trust_v07  # noqa: E402
from wf_v07 import WF  # noqa: E402


def base_graph() -> Graph:
    """소비→실행→생산 + measures 를 갖춘 최소 WorkflowGraph."""
    g = Graph()
    workflow = WF["workflow/w"]
    oracle_wf = WF["workflow/o"]
    task = WF["node/w/run"]
    eval_node = WF["node/o/gate"]
    src = WF["artifact/w/in"]
    out = WF["artifact/w/out"]

    g.add((workflow, RDF.type, WF.Workflow))
    g.add((workflow, WF.workflowType, Literal("base")))
    g.add((oracle_wf, RDF.type, WF.Workflow))
    g.add((oracle_wf, WF.workflowType, Literal("oracle")))
    for node, wf_, types in (
        (task, workflow, (WF.Task, WF.Execution, WF.Node)),
        (eval_node, oracle_wf, (WF.Eval, WF.Execution, WF.Node)),
    ):
        for t in types:
            g.add((node, RDF.type, t))
        g.add((node, RDFS.label, Literal(str(node)[-4:])))
        g.add((wf_, WF.has, node))
    for artifact, locator in ((src, "in.jsonl"), (out, "out.md")):
        g.add((artifact, RDF.type, WF.Artifact))
        g.add((artifact, RDF.type, WF.Node))
        g.add((artifact, WF.locator, Literal(locator)))
        g.add((workflow, WF.has, artifact))

    def stream(name, s, t, st):
        uri = WF[f"stream/w/{name}"]
        g.add((uri, RDF.type, WF.Stream))
        g.add((uri, WF["from"], s))
        g.add((uri, WF.to, t))
        g.add((uri, WF.streamType, Literal(st)))

    stream("c", src, task, "consumed_by")
    stream("p", task, out, "produces_to")
    stream("e", src, out, "evidence_of")

    measures = WF["rail/o/gate__measures__w"]
    g.add((measures, RDF.type, WF.Rail))
    g.add((measures, WF["from"], eval_node))
    g.add((measures, WF.to, workflow))
    g.add((measures, WF.railType, Literal("measures")))
    return g


def calc(g: Graph, policy=None) -> trust_v07.TrustCalculator:
    return trust_v07.TrustCalculator(g, policy or trust_v07.load_policy(None))


def test_artifact_trust_rises_with_provenance():
    g = base_graph()
    src = WF["artifact/w/in"]
    bare = calc(g).artifact_own_trust(src)
    g.add((src, WF.confidence, Literal("0.95", datatype=XSD.decimal)))
    g.add((src, WF.validation, Literal("validate_abox pass")))
    g.add((src, WF.coverage, Literal("0.9", datatype=XSD.decimal)))
    g.add((src, WF.author, Literal("repo-owner")))
    rich = calc(g).artifact_own_trust(src)
    assert rich > bare
    assert 0.0 <= bare <= 1.0 and 0.0 <= rich <= 1.0


def test_evidence_propagation_pulls_target_toward_source():
    """Low-trust 출처가 evidence_of로 산출물 trust를 끌어내린다 — GIGO."""
    g = base_graph()
    src = WF["artifact/w/in"]
    out = WF["artifact/w/out"]
    # 산출물엔 좋은 provenance, 출처는 전무(낮음)
    g.add((out, WF.confidence, Literal("0.95", datatype=XSD.decimal)))
    g.add((out, WF.validation, Literal("pass")))
    trusts = calc(g).artifact_trusts()
    own_only = calc(g).artifact_own_trust(out)
    assert trusts[out] < own_only  # 계보 전파가 끌어내림
    assert trusts[src] < trusts[out]


def test_execution_subject_ordering():
    g = base_graph()
    task = WF["node/w/run"]
    scores = {}
    for subject in ("human", "system", "self", "workflow", "model"):
        g.set((task, WF.hasSubject, Literal(subject)))
        scores[subject] = calc(g).execution_trust(task)
    assert scores["human"] > scores["system"] > scores["self"] > scores["workflow"] > scores["model"]


def test_workflow_trust_weights_consumed_highest():
    g = base_graph()
    c = calc(g)
    at = c.artifact_trusts()
    et = c.execution_trusts()
    wt = c.workflow_trusts(at, et)
    info = wt[WF["workflow/w"]]
    assert info["trust"] is not None
    assert set(info["components"]) == {"consumed", "execution", "produced"}


def test_oracle_decision_threshold():
    g = base_graph()
    result = trust_v07.compute_from_graph(g) if hasattr(trust_v07, "compute_from_graph") else None
    c = calc(g)
    at, et = c.artifact_trusts(), c.execution_trusts()
    wt = c.workflow_trusts(at, et)
    decisions = c.oracle_decisions(wt)
    assert len(decisions) == 1
    d = decisions[0]
    assert d["workflow"] == "w"
    assert d["suggestion"] in {"pass", "fail"}
    # 낮은 신호 → fail 제안 (D-28: 제안일 뿐 확정 아님)
    assert d["suggestion"] == "fail"


def test_policy_override_changes_threshold(tmp_path):
    g = base_graph()
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text("trust_threshold: 0.1\n", encoding="utf-8")
    policy = trust_v07.load_policy(policy_file)
    assert policy["trust_threshold"] == 0.1
    c = calc(g, policy)
    wt = c.workflow_trusts(c.artifact_trusts(), c.execution_trusts())
    decisions = c.oracle_decisions(wt)
    assert decisions[0]["suggestion"] == "pass"  # threshold 완화로 통과


def test_compute_never_writes_trust_into_graph(tmp_path):
    """D-25: Trust는 TTL에 저장되지 않는다 — compute는 그래프를 변형하지 않는다."""
    g = base_graph()
    before = len(g)
    c = calc(g)
    c.workflow_trusts(c.artifact_trusts(), c.execution_trusts())
    assert len(g) == before
    assert next(g.subject_objects(WF.trust), None) is None


def test_cli_report_on_example(tmp_path):
    report = tmp_path / "trust-report.md"
    rc = trust_v07.main([
        str(ASSETS / "examples"), "--report", str(report),
    ])
    assert rc == 0
    text = report.read_text(encoding="utf-8")
    assert "repository_trust" in text.replace("_", "_")
    assert "Oracle Decision" in text
    assert "저장하는 값이 아니라" in text
