"""v0.7 Rail/Stream — 마이그레이터 · 검증기 · v0.6 호환 projection 테스트."""

import sys
from pathlib import Path

from rdflib import Graph, Literal, RDF, RDFS

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
sys.path.insert(0, str(SCRIPTS))

import migrate_abox_v06_to_v07 as migrate  # noqa: E402
import validate_abox  # noqa: E402
from wf_v07 import WF, is_v07_graph, project_v06_compat, rail_layer  # noqa: E402

EXAMPLE_V06 = ASSETS / "examples" / "root-workflow.abox.ttl"


def migrated_graph() -> Graph:
    src = Graph()
    src.parse(str(EXAMPLE_V06), format="turtle")
    return migrate.Migrator(src).migrate()


# ─── 어휘/파생 ────────────────────────────────────────────────────────────


def test_rail_layer_derivation():
    assert rail_layer("default") == "base"
    assert rail_layer("reads") == "base"
    assert rail_layer("delegates_to") == "base"
    assert rail_layer("measured_by") == "oracle"
    assert rail_layer("evolves_to") == "oracle"
    assert rail_layer("tests_to") == "oracle"


def test_v07_detection():
    v06 = Graph()
    v06.parse(str(EXAMPLE_V06), format="turtle")
    assert not is_v07_graph(v06)
    assert is_v07_graph(migrated_graph())


# ─── 마이그레이터 ──────────────────────────────────────────────────────────


def test_migrator_converts_execution_types():
    g = migrated_graph()
    executions = set(g.subjects(RDF.type, WF.Execution))
    tasks = set(g.subjects(RDF.type, WF.Task))
    evals = set(g.subjects(RDF.type, WF.Eval))
    assert executions and tasks and evals
    assert tasks <= executions and evals <= executions
    # v0.6 전용 클래스는 정본에서 제거됨
    assert not set(g.subjects(RDF.type, WF.Step))
    assert not set(g.subjects(RDF.type, WF.Branch))


def test_migrator_synthesizes_start_end_per_workflow():
    g = migrated_graph()
    starts = set(g.subjects(RDF.type, WF.Start))
    ends = set(g.subjects(RDF.type, WF.End))
    # discovery / development / development-oracle / testing = 4개 workflow
    assert len(starts) == 4
    assert len(ends) == 4
    # Start는 in-rail 0
    for start in starts:
        assert next(
            (r for r in g.subjects(RDF.type, WF.Rail) if g.value(r, WF.to) == start), None
        ) is None


def test_migrator_replaces_branches_with_rails():
    g = migrated_graph()
    for task, rail in g.subject_objects(WF.hasBranch):
        assert (rail, RDF.type, WF.Rail) in g
        assert isinstance(g.value(rail, WF.on), Literal)


def test_migrator_emits_measured_by_and_workflow_type():
    g = migrated_graph()
    measured = [
        r for r in g.subjects(RDF.type, WF.Rail)
        if g.value(r, WF.railType) == Literal("measured_by")
    ]
    assert measured
    oracle_types = {
        str(w).rsplit("/", 1)[-1]
        for w in g.subjects(WF.workflowType, Literal("oracle"))
    }
    assert "development-oracle" in oracle_types
    assert "testing" in oracle_types


def test_migrator_drops_cross_workflow_next_into_eval():
    g = migrated_graph()
    eval_nodes = set(g.subjects(RDF.type, WF.Eval))
    for rail in g.subjects(RDF.type, WF.Rail):
        if g.value(rail, WF.railType) != Literal("default"):
            continue
        target = g.value(rail, WF.to)
        if target in eval_nodes:
            source = g.value(rail, WF["from"])
            # eval로 향하는 default rail은 같은 workflow(branch/Start)에서만 허용
            owners_t = set(g.subjects(WF.has, target))
            owners_s = set(g.subjects(WF.has, source))
            assert owners_t & owners_s, f"cross-workflow eval 진입 rail 잔존: {rail}"


# ─── 검증기 (v0.7 스택) ────────────────────────────────────────────────────


def test_validate_migrated_example_passes(tmp_path):
    g = migrated_graph()
    path = tmp_path / "workflow-x.v07.abox.ttl"
    path.write_text(g.serialize(format="turtle"), encoding="utf-8")
    res = validate_abox.validate_abox([tmp_path])
    assert res["v07"] is not None
    assert res["v07"]["shacl_conforms"], res["v07"]["shacl_report"]
    assert res["ok"], res


def test_validate_v07_default_task_multi_out_is_error(tmp_path):
    body = """@prefix wf: <https://mso.dev/ontology/workflow#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<https://mso.dev/ontology/workflow#workflow/t> a wf:Workflow ;
    wf:workflowType "base" ;
    wf:has <https://mso.dev/ontology/workflow#node/t/start>,
        <https://mso.dev/ontology/workflow#node/t/a>,
        <https://mso.dev/ontology/workflow#node/t/b>,
        <https://mso.dev/ontology/workflow#node/t/c>,
        <https://mso.dev/ontology/workflow#node/t/end> .
<https://mso.dev/ontology/workflow#node/t/start> a wf:Start, wf:Node .
<https://mso.dev/ontology/workflow#node/t/end> a wf:End, wf:Node .
<https://mso.dev/ontology/workflow#node/t/a> a wf:Task, wf:Execution, wf:Node ; rdfs:label "A" .
<https://mso.dev/ontology/workflow#node/t/b> a wf:Task, wf:Execution, wf:Node ; rdfs:label "B" .
<https://mso.dev/ontology/workflow#node/t/c> a wf:Task, wf:Execution, wf:Node ; rdfs:label "C" .
<https://mso.dev/ontology/workflow#rail/t/s__a> a wf:Rail, wf:Edge ;
    wf:from <https://mso.dev/ontology/workflow#node/t/start> ;
    wf:to <https://mso.dev/ontology/workflow#node/t/a> ; wf:railType "default" .
<https://mso.dev/ontology/workflow#rail/t/a__b> a wf:Rail, wf:Edge ;
    wf:from <https://mso.dev/ontology/workflow#node/t/a> ;
    wf:to <https://mso.dev/ontology/workflow#node/t/b> ; wf:railType "default" .
<https://mso.dev/ontology/workflow#rail/t/a__c> a wf:Rail, wf:Edge ;
    wf:from <https://mso.dev/ontology/workflow#node/t/a> ;
    wf:to <https://mso.dev/ontology/workflow#node/t/c> ; wf:railType "default" .
<https://mso.dev/ontology/workflow#rail/t/b__end> a wf:Rail, wf:Edge ;
    wf:from <https://mso.dev/ontology/workflow#node/t/b> ;
    wf:to <https://mso.dev/ontology/workflow#node/t/end> ; wf:railType "default" .
<https://mso.dev/ontology/workflow#rail/t/c__end> a wf:Rail, wf:Edge ;
    wf:from <https://mso.dev/ontology/workflow#node/t/c> ;
    wf:to <https://mso.dev/ontology/workflow#node/t/end> ; wf:railType "default" .
"""
    path = tmp_path / "workflow-bad.v07.abox.ttl"
    path.write_text(body, encoding="utf-8")
    res = validate_abox.validate_abox([tmp_path])
    assert res["v07"] is not None
    assert not res["v07"]["shacl_conforms"]
    assert "정확히 1개" in res["v07"]["shacl_report"]


def test_validate_v07_eval_outside_oracle_is_error(tmp_path):
    body = """@prefix wf: <https://mso.dev/ontology/workflow#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<https://mso.dev/ontology/workflow#workflow/t> a wf:Workflow ;
    wf:workflowType "base" ;
    wf:has <https://mso.dev/ontology/workflow#node/t/start>,
        <https://mso.dev/ontology/workflow#node/t/e>,
        <https://mso.dev/ontology/workflow#node/t/end> .
<https://mso.dev/ontology/workflow#node/t/start> a wf:Start, wf:Node .
<https://mso.dev/ontology/workflow#node/t/end> a wf:End, wf:Node .
<https://mso.dev/ontology/workflow#node/t/e> a wf:Eval, wf:Execution, wf:Node ;
    rdfs:label "E" ; wf:hasSubject "system" .
<https://mso.dev/ontology/workflow#artifact/t/out> a wf:Artifact, wf:Node ;
    wf:locator "out/" ; rdfs:label "out/" .
<https://mso.dev/ontology/workflow#rail/t/s__e> a wf:Rail, wf:Edge ;
    wf:from <https://mso.dev/ontology/workflow#node/t/start> ;
    wf:to <https://mso.dev/ontology/workflow#node/t/e> ; wf:railType "default" .
<https://mso.dev/ontology/workflow#rail/t/m> a wf:Rail, wf:Edge ;
    wf:from <https://mso.dev/ontology/workflow#artifact/t/out> ;
    wf:to <https://mso.dev/ontology/workflow#node/t/e> ; wf:railType "measured_by" .
<https://mso.dev/ontology/workflow#rail/t/fail> a wf:Rail, wf:Edge ;
    wf:from <https://mso.dev/ontology/workflow#node/t/e> ;
    wf:to <https://mso.dev/ontology/workflow#node/t/end> ; wf:railType "default" ; wf:on "fail" .
<https://mso.dev/ontology/workflow#rail/t/pass> a wf:Rail, wf:Edge ;
    wf:from <https://mso.dev/ontology/workflow#node/t/e> ;
    wf:to <https://mso.dev/ontology/workflow#node/t/end> ; wf:railType "default" ; wf:on "pass" .
<https://mso.dev/ontology/workflow#node/t/e> wf:hasBranch
    <https://mso.dev/ontology/workflow#rail/t/fail>,
    <https://mso.dev/ontology/workflow#rail/t/pass> .
"""
    path = tmp_path / "workflow-bad.v07.abox.ttl"
    path.write_text(body, encoding="utf-8")
    res = validate_abox.validate_abox([tmp_path])
    assert not res["v07"]["shacl_conforms"]
    assert "oracle" in res["v07"]["shacl_report"]


def test_validate_v07_oracle_disjoint_violation():
    g = migrated_graph()
    # 고의 위반: oracle task의 evolves_to를 자기 소속 workflow로 변경
    oracle_wf = WF["workflow/workflow-00/development-oracle"]
    for rail in list(g.subjects(RDF.type, WF.Rail)):
        if g.value(rail, WF.railType) == Literal("evolves_to"):
            g.remove((rail, WF.to, None))
            g.add((rail, WF.to, oracle_wf))
    issues, _warnings = validate_abox.find_oracle_disjoint_violations_v07(g)
    assert issues


def test_validate_v07_task_partition_violation():
    g = migrated_graph()
    task = next(iter(g.subjects(RDF.type, WF.Task)))
    g.add((WF["workflow/other"], RDF.type, WF.Workflow))
    g.add((WF["workflow/other"], WF.has, task))
    issues = validate_abox.find_task_sharing_v07(g)
    assert issues


# ─── v0.6 호환 projection ──────────────────────────────────────────────────


def test_compat_projection_derives_v06_predicates():
    g = migrated_graph()
    compat = project_v06_compat(g)
    # Execution 유형 → v0.6 클래스
    assert set(compat.subjects(RDF.type, WF.Step))
    assert set(compat.subjects(RDF.type, WF.Eval))
    # measures rail → v0.6 wf:target 복원
    assert next(compat.subject_objects(WF.target), None) is not None
    # 브랜치 rail → Branch bnode 합성
    branches = [b for b in compat.objects(None, WF.hasBranch)
                if (b, RDF.type, WF.Branch) in compat]
    assert branches
    # measured_by → wf:measures
    assert next(compat.subject_objects(WF.measures), None) is not None
    # evolves_to → wf:evolves
    assert next(compat.subject_objects(WF.evolves), None) is not None
    # wf:has → wf:hasNode (Start/End 제외)
    for _, node in compat.subject_objects(WF.hasNode):
        assert (node, RDF.type, WF.Start) not in compat
        assert (node, RDF.type, WF.End) not in compat


def test_compat_projection_plain_rail_becomes_next():
    g = Graph()
    a = WF["node/t/a"]
    b = WF["node/t/b"]
    rail = WF["rail/t/a__default__b"]
    for node in (a, b):
        g.add((node, RDF.type, WF.Task))
        g.add((node, RDF.type, WF.Execution))
        g.add((node, RDF.type, WF.Node))
        g.add((node, RDFS.label, Literal(str(node)[-1])))
    g.add((rail, RDF.type, WF.Rail))
    g.add((rail, WF["from"], a))
    g.add((rail, WF.to, b))
    g.add((rail, WF.railType, Literal("default")))
    compat = project_v06_compat(g)
    assert (a, WF.next, b) in compat


def test_compat_projection_feeds_observe_graph():
    """observe_graph가 호환 projection 그래프에서 v0.6과 동일 계열 뷰를 생성하는지."""
    obs_scripts = SCRIPTS.parent.parent / "mso-graph-observability" / "scripts"
    sys.path.insert(0, str(obs_scripts))
    import observe_graph  # noqa: E402

    compat = project_v06_compat(migrated_graph())
    scopes = observe_graph.workflow_scopes(compat)
    assert scopes, "호환 그래프에서 workflow scope가 비어 있음"
    markdown = observe_graph.build_workflow_topology(
        compat, scope=scopes[0], view="workflow"
    )
    assert "```mermaid" in markdown


def test_migrator_legacy_phase_input(tmp_path):
    """legacy wf:Phase + goto 문자열 + wf:judge ABox → v0.7 변환 회귀."""
    body = """@prefix wf: <https://mso.dev/ontology/workflow#> .
<https://mso.dev/ontology/workflow#phase/p1> a wf:Phase ;
    wf:label "P1" ;
    wf:hasNode <https://mso.dev/ontology/workflow#node/x-d-001> .
<https://mso.dev/ontology/workflow#phase/p2> a wf:Phase ;
    wf:label "P2" ;
    wf:hasNode <https://mso.dev/ontology/workflow#node/x-s-001> .
<https://mso.dev/ontology/workflow#node/x-d-001> a wf:Decision, wf:Node ;
    wf:label "게이트" ; wf:judge "HITL" ;
    wf:hasBranch <https://mso.dev/ontology/workflow#node/x-d-001_b1>,
        <https://mso.dev/ontology/workflow#node/x-d-001_b2> .
<https://mso.dev/ontology/workflow#node/x-d-001_b1> a wf:Branch ;
    wf:on "approved" ; wf:goto "x-s-001" .
<https://mso.dev/ontology/workflow#node/x-d-001_b2> a wf:Branch ;
    wf:on "rejected" ; wf:goto "missing-node" .
<https://mso.dev/ontology/workflow#node/x-s-001> a wf:Step, wf:Node, wf:Task ;
    wf:label "작업" ; wf:instruction "실행" ; wf:status "pending" .
"""
    src_path = tmp_path / "workflow-legacy.abox.ttl"
    src_path.write_text(body, encoding="utf-8")
    src = Graph()
    src.parse(str(src_path), format="turtle")
    migrator = migrate.Migrator(src)
    g = migrator.migrate()

    # Phase → Workflow 승격
    p1 = WF["phase/p1"]
    assert (p1, RDF.type, WF.Workflow) in g
    assert any("wf:Workflow로 승격" in w for w in migrator.warnings)
    # judge HITL → hasSubject human (Q-6)
    assert (WF["node/x-d-001"], WF.hasSubject, Literal("human")) in g
    # cross-phase goto 문자열 해석: x-d-001 → x-s-001 (다른 phase 멤버)
    resolved = [
        r for r in g.subjects(RDF.type, WF.Rail)
        if g.value(r, WF.to) == WF["node/x-s-001"]
        and g.value(r, WF["from"]) == WF["node/x-d-001"]
    ]
    assert resolved
    # dangling goto → End + 경고
    assert any("dangling" in w for w in migrator.warnings)


# ─── D-12: oracle 대상의 Artifact 확장 ─────────────────────────────────────


def _oracle_artifact_graph(*, oracle_produces_target: bool, target_consumed: bool) -> Graph:
    """oracle task가 지식 artifact를 evolve하는 최소 그래프."""
    g = Graph()
    oracle_wf = WF["workflow/o"]
    base_wf = WF["workflow/b"]
    task = WF["node/o/fix"]
    base_task = WF["node/b/run"]
    kb = WF["artifact/b/kb"]

    g.add((oracle_wf, RDF.type, WF.Workflow))
    g.add((oracle_wf, WF.workflowType, Literal("oracle")))
    g.add((oracle_wf, WF.has, task))
    g.add((base_wf, RDF.type, WF.Workflow))
    g.add((base_wf, WF.workflowType, Literal("base")))
    g.add((base_wf, WF.has, base_task))
    for node in (task, base_task):
        g.add((node, RDF.type, WF.Task))
        g.add((node, RDF.type, WF.Execution))
        g.add((node, RDF.type, WF.Node))
        g.add((node, RDFS.label, Literal(str(node)[-3:])))
    g.add((kb, RDF.type, WF.Artifact))
    g.add((kb, RDF.type, WF.Node))
    g.add((kb, WF.locator, Literal("ontology/vio.ttl")))
    g.add((kb, WF.artifactType, Literal("knowledge_store")))

    evolve_rail = WF["rail/o/fix__evolves_to__kb"]
    g.add((evolve_rail, RDF.type, WF.Rail))
    g.add((evolve_rail, WF["from"], task))
    g.add((evolve_rail, WF.to, kb))
    g.add((evolve_rail, WF.railType, Literal("evolves_to")))

    if target_consumed:
        stream = WF["stream/b/kb__consumed_by__run"]
        g.add((stream, RDF.type, WF.Stream))
        g.add((stream, WF["from"], kb))
        g.add((stream, WF.to, base_task))
        g.add((stream, WF.streamType, Literal("consumed_by")))
    if oracle_produces_target:
        stream = WF["stream/o/fix__produces_to__kb"]
        g.add((stream, RDF.type, WF.Stream))
        g.add((stream, WF["from"], task))
        g.add((stream, WF.to, kb))
        g.add((stream, WF.streamType, Literal("produces_to")))
    return g


def test_d12_evolves_to_consumed_artifact_is_valid():
    """workflow가 소비하는 지식 artifact를 evolve — 정합 (D-12)."""
    g = _oracle_artifact_graph(oracle_produces_target=False, target_consumed=True)
    issues, warnings = validate_abox.find_oracle_disjoint_violations_v07(g)
    assert not issues
    assert not warnings


def test_d12_oracle_self_produced_artifact_is_error():
    """oracle이 자기가 생산한 artifact를 evolve — 자기 증거 조작 루프 (오류)."""
    g = _oracle_artifact_graph(oracle_produces_target=True, target_consumed=True)
    issues, _warnings = validate_abox.find_oracle_disjoint_violations_v07(g)
    assert any("self-produce" in i for i in issues)


def test_d12_unconsumed_artifact_target_is_warning():
    """아무도 소비하지 않는 artifact를 evolve — 정당화 근거 없음 (경고)."""
    g = _oracle_artifact_graph(oracle_produces_target=False, target_consumed=False)
    issues, warnings = validate_abox.find_oracle_disjoint_violations_v07(g)
    assert not issues
    assert any("no-consumer" in w for w in warnings)


def test_d12_shacl_allows_artifact_target(tmp_path):
    """SHACL: evolves_to의 to가 Artifact면 통과, Executor면 위반."""
    g = _oracle_artifact_graph(oracle_produces_target=False, target_consumed=True)
    conforms, report = validate_abox.run_shacl_v07(g)
    assert "Workflow 또는 Artifact" not in report
    # 잘못된 대상 (Terminal — Workflow도 Artifact도 아님)
    bad = WF["node/o/badstart"]
    g.add((bad, RDF.type, WF.Start))
    g.add((bad, RDF.type, WF.Node))
    rail = WF["rail/o/bad"]
    g.add((rail, RDF.type, WF.Rail))
    g.add((rail, WF["from"], WF["node/o/fix"]))
    g.add((rail, WF.to, bad))
    g.add((rail, WF.railType, Literal("evolves_to")))
    conforms2, report2 = validate_abox.run_shacl_v07(g)
    assert not conforms2
    assert "Workflow 또는 Artifact" in report2


# ─── v0.9.0: Provenance + Execution Metadata (§6/§7) ────────────────────────


def test_provenance_coverage_warnings():
    """provenance 없는 artifact / method 없는 execution → 경고 (D-22, 오류 아님)."""
    g = _oracle_artifact_graph(oracle_produces_target=False, target_consumed=True)
    warnings = validate_abox.find_provenance_coverage_v07(g)
    assert any("provenance coverage" in w for w in warnings)
    assert any("method 미선언" in w for w in warnings)
    # provenance 채우면 artifact 경고 소멸
    kb = WF["artifact/b/kb"]
    g.add((kb, WF.author, Literal("repo-owner")))
    warnings2 = validate_abox.find_provenance_coverage_v07(g)
    assert not any("artifact kb" in w for w in warnings2 if "provenance coverage" in w)


def test_provenance_format_shacl_rejects_out_of_range_confidence(tmp_path):
    from rdflib.namespace import XSD
    g = _oracle_artifact_graph(oracle_produces_target=False, target_consumed=True)
    kb = WF["artifact/b/kb"]
    g.add((kb, WF.confidence, Literal("1.5", datatype=XSD.decimal)))  # 0..1 위반
    conforms, report = validate_abox.run_shacl_v07(g)
    assert not conforms
    assert "confidence" in report


def test_execution_method_enum_shacl(tmp_path):
    g = _oracle_artifact_graph(oracle_produces_target=False, target_consumed=True)
    task = WF["node/b/run"]
    g.add((task, WF.method, Literal("telepathy")))  # enum 위반
    conforms, report = validate_abox.run_shacl_v07(g)
    assert not conforms
    assert "method" in report
    g.remove((task, WF.method, Literal("telepathy")))
    g.add((task, WF.method, Literal("script")))
    _, report2 = validate_abox.run_shacl_v07(g)
    assert "method" not in report2  # 유효 enum이면 method 위반 소멸 (다른 shape와 무관)
