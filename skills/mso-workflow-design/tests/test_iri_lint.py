"""validate_abox.py — IRI lint (charset/case-fold collision/type-prefix) 테스트."""

import sys
from pathlib import Path

from rdflib import Graph

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
sys.path.insert(0, str(SCRIPTS))

import validate_abox  # noqa: E402

PREFIX = "@prefix wf: <https://mso.dev/ontology/workflow#> .\n"


def graph_from(body: str) -> Graph:
    g = Graph()
    g.parse(data=PREFIX + body, format="turtle")
    return g


def test_bundled_examples_have_no_iri_lint_issues():
    from validate_abox import collect_abox_paths, parse_graph

    paths = collect_abox_paths([ASSETS / "examples"])
    g = parse_graph(paths)
    assert validate_abox.find_iri_lint_issues(g) == []


def test_unknown_type_prefix_is_flagged():
    g = graph_from(
        "<https://mso.dev/ontology/workflow#midule/policy-engine> a wf:Module .\n"
    )
    issues = validate_abox.find_iri_lint_issues(g)
    assert any("[I2]" in i and "midule" in i for i in issues)


def test_uppercase_local_segment_is_flagged():
    g = graph_from(
        "<https://mso.dev/ontology/workflow#module/PolicyEngine> a wf:Module .\n"
    )
    issues = validate_abox.find_iri_lint_issues(g)
    assert any("[I4]" in i for i in issues)


def test_case_folded_iri_collision_is_flagged():
    g = graph_from(
        "<https://mso.dev/ontology/workflow#module/policy-engine> a wf:Module .\n"
        "<https://mso.dev/ontology/workflow#module/Policy-Engine> a wf:Module .\n"
    )
    issues = validate_abox.find_iri_lint_issues(g)
    assert any("[I5]" in i for i in issues)


def test_vocabulary_terms_are_not_lint_targets():
    """단일 세그먼트(class/property, camelCase)는 인스턴스 IRI 접두사 검사 대상이 아니다."""
    g = graph_from(
        "<https://mso.dev/ontology/workflow#module/policy-engine> a wf:Module ;\n"
        "  wf:criticalDep <https://mso.dev/ontology/workflow#module/ingestion> .\n"
    )
    issues = validate_abox.find_iri_lint_issues(g)
    assert issues == []


def test_validate_abox_fails_on_iri_lint_issue(tmp_path):
    path = tmp_path / "workflow-t.abox.ttl"
    path.write_text(
        PREFIX + "<https://mso.dev/ontology/workflow#midule/policy-engine> a wf:Module .\n",
        encoding="utf-8",
    )
    res = validate_abox.validate_abox([path])
    assert res["iri_lint_issues"]
    assert not res["ok"]
