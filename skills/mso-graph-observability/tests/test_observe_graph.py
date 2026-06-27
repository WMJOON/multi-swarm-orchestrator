from __future__ import annotations

import importlib.util
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD


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
