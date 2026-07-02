#!/usr/bin/env python3
"""materialize_v07 — Property Chain 파생 (v0.8.0, ROADMAP §5).

    consumed_by ∘ produces_to = evidence_of

정본 `.abox.ttl`의 Stream 인스턴스에서 chain을 매칭해 derived `evidence_of`
Stream을 합성하고 sibling `<name>.inferred.ttl` 로 출력한다 (멱등 — 전체 재생성).

원칙 (SPEC mso-v0.8.0):
  D-18  파생 edge는 wf:derived true + wf:derivedFrom(원본 2개)으로 표시한다.
  D-19  정본에 섞지 않는다 — .inferred.ttl sibling. validate는 SSOT만 검증,
        observe는 workflow dir 전체 .ttl을 읽어 자동 포함.
  D-20  같은 (from, to)의 explicit evidence_of가 있으면 파생을 생략한다.
  자기근거 방지: from == to 인 chain(같은 artifact를 읽고 쓰는 tool)은 생략.

부가: 술어-레벨 projection triple(wf:consumed_by/produces_to/evidence_of)도
동봉해 OWL propertyChainAxiom interop을 지원한다 (D-17).

Usage:
  python materialize_v07.py <dir|file.abox.ttl> [...] [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rdflib import Graph, Literal, RDF, URIRef
from rdflib.namespace import XSD

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wf_v07 import WF, is_v07_graph  # noqa: E402


def _streams(g: Graph, stream_type: str) -> list[tuple[URIRef, URIRef, URIRef]]:
    """[(stream_uri, from, to)] of the given streamType."""
    out = []
    for stream in sorted(g.subjects(RDF.type, WF.Stream), key=str):
        if g.value(stream, WF.streamType) != Literal(stream_type):
            continue
        source = g.value(stream, WF["from"])
        target = g.value(stream, WF.to)
        if isinstance(source, URIRef) and isinstance(target, URIRef):
            out.append((stream, source, target))
    return out


def _explicit_evidence_pairs(g: Graph) -> set[tuple[URIRef, URIRef]]:
    return {(s, t) for _, s, t in _streams(g, "evidence_of")}


def _slug_local(node: URIRef) -> str:
    text = str(node)
    return text.rsplit("/", 1)[-1] if "/" in text else text


def materialize(g: Graph) -> Graph:
    """chain 매칭 → derived evidence_of Stream 합성 그래프 반환 (원본 불변)."""
    inferred = Graph()
    inferred.bind("wf", WF)

    consumed = _streams(g, "consumed_by")     # (stream, Artifact, Execution)
    produced = _streams(g, "produces_to")     # (stream, Execution, Artifact)
    explicit = _explicit_evidence_pairs(g)

    by_execution: dict[URIRef, list[tuple[URIRef, URIRef]]] = {}
    for stream, execution, artifact in produced:
        by_execution.setdefault(execution, []).append((stream, artifact))

    emitted: set[tuple[URIRef, URIRef]] = set()
    for c_stream, source_artifact, execution in consumed:
        for p_stream, target_artifact in by_execution.get(execution, []):
            pair = (source_artifact, target_artifact)
            if source_artifact == target_artifact:
                continue  # 자기근거 방지 (같은 artifact 소비·생산)
            if pair in explicit or pair in emitted:
                continue  # D-20: 명시 선언 우선 / 중복 방지
            emitted.add(pair)
            uri = WF[
                "stream/inferred/"
                f"{_slug_local(source_artifact)}__evidence_of__{_slug_local(target_artifact)}"
            ]
            inferred.add((uri, RDF.type, WF.Stream))
            inferred.add((uri, RDF.type, WF.Edge))
            inferred.add((uri, WF["from"], source_artifact))
            inferred.add((uri, WF.to, target_artifact))
            inferred.add((uri, WF.streamType, Literal("evidence_of")))
            inferred.add((uri, WF.derived, Literal(True, datatype=XSD.boolean)))
            inferred.add((uri, WF.derivedFrom, c_stream))
            inferred.add((uri, WF.derivedFrom, p_stream))
            # 술어-레벨 projection (OWL chain interop, D-17)
            inferred.add((source_artifact, WF.evidence_of, target_artifact))

    # 저장 관계의 술어 projection도 동봉 (chain 공리의 입력)
    for _, source, target in consumed:
        inferred.add((source, WF.consumed_by, target))
    for _, source, target in produced:
        inferred.add((source, WF.produces_to, target))

    return inferred


def collect_abox_paths(targets: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for target in targets:
        if target.is_dir():
            paths.extend(sorted(p for p in target.rglob("*.abox.ttl")))
        elif target.suffix == ".ttl" and not target.name.endswith(".inferred.ttl"):
            paths.append(target)
    return paths


def materialize_file(path: Path) -> tuple[Path | None, int]:
    g = Graph()
    g.parse(str(path), format="turtle")
    if not is_v07_graph(g):
        return None, 0
    inferred = materialize(g)
    derived_count = len(set(inferred.subjects(RDF.type, WF.Stream)))
    target = path.with_name(path.name.replace(".abox.ttl", ".inferred.ttl"))
    if len(inferred):
        target.write_text(inferred.serialize(format="turtle"), encoding="utf-8")
        return target, derived_count
    if target.exists():
        target.unlink()  # 파생이 사라지면 잔재 제거 (멱등)
    return None, 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="materialize_v07",
                                 description="property chain 파생: consumed_by ∘ produces_to = evidence_of")
    ap.add_argument("targets", nargs="+", help="*.abox.ttl 파일 또는 디렉토리")
    ap.add_argument("--check", action="store_true",
                    help="파생 결과가 기존 .inferred.ttl과 동일한지만 확인 (drift 가드)")
    args = ap.parse_args(argv)

    targets = [Path(t).resolve() for t in args.targets]
    for t in targets:
        if not t.exists():
            print(f"경로 없음: {t}", file=sys.stderr)
            return 2

    paths = collect_abox_paths(targets)
    if not paths:
        print("materialize할 .abox.ttl 없음", file=sys.stderr)
        return 1

    status = 0
    for path in paths:
        if args.check:
            g = Graph()
            g.parse(str(path), format="turtle")
            if not is_v07_graph(g):
                continue
            expected = materialize(g).serialize(format="turtle")
            target = path.with_name(path.name.replace(".abox.ttl", ".inferred.ttl"))
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            expected_norm = expected if len(Graph().parse(data=expected, format="turtle")) else ""
            if (current or expected_norm) and current != expected:
                print(f"✗ drift: {target.name} — materialize 재실행 필요", file=sys.stderr)
                status = 1
            continue
        written, count = materialize_file(path)
        if written:
            print(f"✓ {path.name} → {written.name} (derived evidence_of {count}건)")
        else:
            print(f"- {path.name}: 파생 없음")
    if args.check and status == 0:
        print("✓ inferred가 정본과 동기 상태")
    return status


if __name__ == "__main__":
    sys.exit(main())
