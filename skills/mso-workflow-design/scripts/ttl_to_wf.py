#!/usr/bin/env python3
"""ttl_to_wf — workflow ABox TTL 을 SHACL 검증 후 YAML 로 변환(ingestion).

방향: TTL → (SHACL+비순환 게이트) → YAML.  `wf_to_ttl.py serialize`(YAML→TTL)의 역.

위치 (§11.2 SSOT): YAML 이 SSOT-of-record. 이 스크립트는 *생성/수기 TTL* 을 받아
TBox/SHACL 게이트를 통과한 것만 YAML 로 **승격**하는 ingestion 경로다. UUG 가 엄브렐러
워크플로우를 그래프로 materialize 하거나, 손으로 ABox TTL 을 적은 경우의 입구.
게이트 실패 시 YAML 을 내지 않는다(불량 승격 차단) — 이게 "shacl 검증 필요"의 핵심.

검증·shape·비순환 로직은 wf_to_ttl 의 run_shacl / find_cycles 를 **재사용**(중복 없음).
필드 list/scalar 카디널리티는 schemas/*.yaml 에서 읽어 schema-구동 재구성.

사용:
  python ttl_to_wf.py <workflow.abox.ttl> [-o out.yaml]   # 검증 통과 시 YAML(stdout 또는 -o)
  python ttl_to_wf.py <ttl> --force                       # 게이트 무시하고 변환(디버그)

라운드트립 현황: phases/nodes 의 스칼라·리스트 필드 + directories(role+path)는 충실.
미충실(현 vocab 한계): decision.branches, workflow_ref.module/harness_propagate
(refersTo 가 문자열만 보존). 필요 시 투영 vocab 확장은 후속.
"""
import argparse
import re
import sys
from pathlib import Path

import yaml
from rdflib import Graph, RDF

_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR))
import wf_to_ttl as W  # WF, run_shacl, find_cycles, _TYPE_CLASS, _camel 재사용

SCHEMAS = _DIR.parent / "references" / "schemas"

# 클래스 localname → YAML type 리터럴 (W._TYPE_CLASS 의 역).
_TYPE_BY_CLASS = {str(cls).rsplit("#", 1)[-1]: t for t, cls in W._TYPE_CLASS.items()}
# 재구성에서 특수 처리(필드 generic 루프 제외).
_NODE_SPECIAL = {"type", "id", "steps", "branches", "directories", "workflows"}
_PHASE_SPECIAL = {"id", "name", "label", "steps", "workflows", "dependencies", "phases"}


def _uncamel(s: str) -> str:
    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), s)


def _localname(uri: str, prefix: str) -> str:
    tail = str(uri).rsplit("#", 1)[-1]
    return tail[len(prefix):] if tail.startswith(prefix) else tail


def _load_field_cardinality() -> dict:
    """type → {snake_field: is_list}. schemas/*.yaml 에서 읽음(schema-구동)."""
    out = {}
    for p in SCHEMAS.glob("*.schema.yaml"):
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        t = doc.get("type")
        fields = {}
        for fname, spec in (doc.get("fields") or {}).items():
            if isinstance(spec, dict):
                fields[fname] = (spec.get("type") == "list")
        out[t] = fields
    return out


_CARD = _load_field_cardinality()


def _emit_fields(g: Graph, subj, ntype: str, skip: set) -> dict:
    """노드/페이즈 subject 의 schema 필드를 YAML dict 로 재구성(scalar/list 카디널리티 반영)."""
    out = {}
    fields = _CARD.get(ntype, {})
    for fname, is_list in fields.items():
        if fname in skip:
            continue
        objs = list(g.objects(subj, W.WF[W._camel(fname)]))
        if not objs:
            continue
        vals = [o.toPython() for o in objs]
        out[fname] = vals if is_list else vals[0]
    return out


def _reconstruct_directories(g: Graph, subj) -> list:
    dirs = []
    for dn in g.objects(subj, W.WF.directory):
        d = {}
        role = list(g.objects(dn, W.WF.dirRole))
        path = list(g.objects(dn, W.WF.dirPath))
        if role:
            d["role"] = str(role[0])
        if path:
            d["path"] = str(path[0])
        if d:
            dirs.append(d)
    return dirs


def _reconstruct_node(g: Graph, nu) -> dict:
    # specific class (wf:Node 제외) → type
    ntype = None
    for c in g.objects(nu, RDF.type):
        ln = str(c).rsplit("#", 1)[-1]
        if ln in _TYPE_BY_CLASS:
            ntype = _TYPE_BY_CLASS[ln]
            break
    node = {"type": ntype, "id": _localname(nu, "node/")}
    node.update(_emit_fields(g, nu, ntype, _NODE_SPECIAL))
    dirs = _reconstruct_directories(g, nu)
    if dirs:
        node["directories"] = dirs
    return node


def graph_to_doc(g: Graph) -> dict:
    phases = []
    phase_subjects = sorted(g.subjects(RDF.type, W.WF.Phase), key=str)
    for pu in phase_subjects:
        pid = _localname(pu, "phase/")
        phase = {"id": pid}
        label = list(g.objects(pu, W.WF.label))
        if label:
            phase["name"] = str(label[0])
        phase.update(_emit_fields(g, pu, "phase", _PHASE_SPECIAL))
        deps = sorted(_localname(o, "phase/") for o in g.objects(pu, W.WF.dependsOn))
        if deps:
            phase["dependencies"] = deps
        refs = [str(o) for o in g.objects(pu, W.WF.refersTo)]
        if refs:
            phase["workflows"] = [{"ref": r} for r in sorted(refs)]
        steps = [_reconstruct_node(g, nu) for nu in g.objects(pu, W.WF.hasNode)]
        steps.sort(key=lambda s: s.get("id", ""))
        if steps:
            phase["steps"] = steps
        phases.append(phase)

    doc = {"phases": phases}

    crit = []
    for fu in g.subjects(W.WF.criticalDep, None):
        for tu in g.objects(fu, W.WF.criticalDep):
            crit.append({"from": _localname(fu, "module/"), "to": _localname(tu, "module/")})
    if crit:
        doc["critical_dependencies"] = sorted(crit, key=lambda c: (c["from"], c["to"]))

    miles = []
    for mu in g.subjects(RDF.type, W.WF.Milestone):
        ph = list(g.objects(mu, W.WF.milestoneOf))
        if ph:
            miles.append({"id": _localname(mu, "milestone/"),
                          "phase_ref": _localname(ph[0], "phase/")})
    if miles:
        doc["milestones"] = sorted(miles, key=lambda m: m["id"])
    return doc


def validate_graph(g: Graph) -> dict:
    cycles = W.find_cycles(g)
    conforms, report = W.run_shacl(g)
    return {"ok": conforms and not cycles, "cycles": cycles,
            "shacl_conforms": conforms, "shacl_report": report if not conforms else ""}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ttl_to_wf",
        description="workflow ABox TTL → SHACL 검증 후 YAML 변환(ingestion)")
    ap.add_argument("ttl", help="workflow ABox TTL 파일")
    ap.add_argument("-o", "--out", default=None, help="출력 YAML 경로 (생략 시 stdout)")
    ap.add_argument("--force", action="store_true",
                    help="게이트 실패해도 변환(디버그). 기본은 SHACL/비순환 통과분만 변환")
    args = ap.parse_args(argv)

    ttl_path = Path(args.ttl).resolve()
    if not ttl_path.exists():
        print(f"파일 없음: {ttl_path}", file=sys.stderr)
        return 2

    g = Graph().parse(str(ttl_path), format="turtle")
    v = validate_graph(g)
    if not v["ok"]:
        print("✗ TTL 검증 실패 — YAML 승격 차단 (게이트):", file=sys.stderr)
        if v["cycles"]:
            print(f"  의존 사이클: {v['cycles']}", file=sys.stderr)
        if not v["shacl_conforms"]:
            print("  SHACL 위반:\n" + v["shacl_report"], file=sys.stderr)
        if not args.force:
            return 1
        print("  (--force: 게이트 무시하고 변환)", file=sys.stderr)

    doc = graph_to_doc(g)
    out_yaml = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
    if args.out:
        Path(args.out).write_text(out_yaml, encoding="utf-8")
        print(f"✓ 변환 완료 → {args.out}", file=sys.stderr)
    else:
        print(out_yaml)
    return 0


if __name__ == "__main__":
    sys.exit(main())
