#!/usr/bin/env python3
"""wf_to_ttl — workflow YAML 을 RDF(TTL) 그래프로 투영하고 shape 를 검증한다.

설계 결정 (§ TTL-first, 2026-06-18):
  TTL ABox 가 SSOT-of-record, YAML 은 편집 편의층이다. `serialize` 는 편집층 YAML 을
  정본 ABox 로 **컴파일**하고(역은 ttl_to_wf — 무손실), `validate` 는 그 그래프를
  검증한다. 이 스크립트는 wf_node.py 의 resolve_workflow_tree 로
  평탄화한 워크플로 트리를 rdflib 그래프로 투영한 뒤 두 층위로 검증한다:

    1) 로컬 shape (pyshacl)   — references/shapes/workflow-shapes.ttl
       노드-단위 불변식: status enum, validation=harness+pass_criteria,
       decision=judge, label 비어있지 않음. (스키마 structural_invariants 의 로컬분)

    2) 전역 DAG (rdflib SPARQL) — 비순환성 / back-edge.
       SHACL core 가 못 하는 임의-깊이 도달성. "다운스트림 결과가 업스트림으로
       재참조되면(=의존 사이클) 오류"를 ASK { ?x wf:dependsOn+ ?x } 로 잡는다.

사용:
  python wf_to_ttl.py serialize <workflow.yaml>          # TTL stdout
  python wf_to_ttl.py validate  <workflow.yaml> [--json] # shape+DAG 검증, 위반 시 exit 1

검증 노드 배선: workflow 의 validation 노드에서
  harness: wf_shape_validator   (= `python wf_to_ttl.py validate <this.yaml>`)
로 가리키면 워크플로 자체 형상이 게이트가 된다(자기 검증).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import RDFS

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
import wf_node  # noqa: E402  (resolve_workflow_tree, _collect_phases, _walk_nodes 재사용)

WF = Namespace("https://mso.dev/ontology/workflow#")
_REF = _SCRIPT_DIR.parent / "references"
SHAPES = _REF / "shapes" / "workflow-shapes.ttl"
TBOX = _REF / "tbox" / "workflow-tbox.ttl"

# YAML node type → RDF class
_TYPE_CLASS = {
    "step": WF.Step,
    "decision": WF.Decision,
    "validation": WF.Validation,
    "group": WF.Group,
}


def _safe(s) -> str:
    """IRI-안전 슬러그: 영숫자·-._ 외는 _ 로."""
    return "".join(c if (c.isalnum() or c in "-._") else "_" for c in str(s))


def _hash8(s: str) -> str:
    return hashlib.sha1(str(s).encode("utf-8")).hexdigest()[:8]


def _node_uri(node_id: str) -> URIRef:
    # IRI-안전: 공백·# 등을 _ 로. id 는 워크플로 내 unique 라는 전제.
    return WF["node/" + _safe(node_id)]


def _phase_uri(phase_id: str) -> URIRef:
    safe = "".join(c if (c.isalnum() or c in "-._") else "_" for c in str(phase_id))
    return WF["phase/" + safe]


def _module_uri(module_id: str) -> URIRef:
    safe = "".join(c if (c.isalnum() or c in "-._") else "_" for c in str(module_id))
    return WF["module/" + safe]


def _camel(snake: str) -> str:
    parts = str(snake).split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _project_fields(g: Graph, subj: URIRef, doc: dict, skip: set) -> None:
    """스칼라·스칼라리스트 필드를 wf:camelCase 로 generic 투영(스키마-구동).

    명시 per-field 코드 없이 schemas/*.yaml 필드를 따라간다 → drift 0.
    bool 은 xsd:boolean Literal(SHACL sh:datatype 정합), list-of-dict(branches/
    directories)는 여기서 건너뛰고 호출부가 특수 처리한다.
    """
    for k, v in doc.items():
        if k in skip:
            continue
        pred = WF[_camel(k)]
        if isinstance(v, bool):
            g.add((subj, pred, Literal(v)))
        elif isinstance(v, (str, int, float)):
            g.add((subj, pred, Literal(v if isinstance(v, (str, bool)) else str(v))))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, bool):
                    g.add((subj, pred, Literal(item)))
                elif isinstance(item, (str, int, float)):
                    g.add((subj, pred, Literal(item if isinstance(item, str) else str(item))))
                # list-of-dict (branches/directories) → 호출부 특수 처리


_NODE_SKIP = {"type", "id", "steps", "branches", "directories", "workflows"}


def _project_nodes(g: Graph, nodes, phase_uri: URIRef) -> None:
    """phase.steps[] (group 재귀 포함) 의 구조화 노드(type 보유)를 투영."""
    for n in wf_node._walk_nodes(nodes or []):
        ntype = n.get("type")
        cls = _TYPE_CLASS.get(ntype)
        if cls is None or not n.get("id"):
            continue  # 레거시(type 없는 step-01: 형태)는 DAG 투영 대상 아님
        nu = _node_uri(n["id"])
        g.add((nu, RDF.type, cls))
        g.add((nu, RDF.type, WF.Node))   # 명시 상위타입 — 추론 없이 hasNode range(sh:class wf:Node) 성립
        g.add((phase_uri, WF.hasNode, nu))
        _project_fields(g, nu, n, _NODE_SKIP)  # label/instruction/status/harness/passCriteria/judge/owner/...
        for d in (n.get("directories") or []):  # 특수: directories[] → 구조화 노드(안정 URI, 라운드트립)
            if isinstance(d, dict) and d.get("path"):
                dn = URIRef(str(nu) + "_dir_" + _safe(d["path"]))
                g.add((nu, WF.directory, dn))
                g.add((dn, WF.dirPath, Literal(str(d["path"]))))
                if d.get("role"):
                    g.add((dn, WF.dirRole, Literal(str(d["role"]))))
        for b in (n.get("branches") or []):  # 특수: decision.branches[] → wf:Branch 노드(안정 URI)
            if not isinstance(b, dict):
                continue
            # 'on' 미인용 시 YAML 이 True 키로 파싱 → 정규화.
            on_val = b.get("on", b.get(True))
            if on_val is None:
                continue
            bn = URIRef(str(nu) + "_branch_" + _safe(str(on_val) + "_" + str(b.get("goto") or "")))
            g.add((nu, WF.hasBranch, bn))
            g.add((bn, RDF.type, WF.Branch))
            g.add((bn, WF.on, Literal(str(on_val))))
            if b.get("goto"):
                g.add((bn, WF.goto, Literal(str(b["goto"]))))
            if b.get("label"):
                g.add((bn, WF.label, Literal(str(b["label"]))))


def _project_workflows(g: Graph, phase_uri: URIRef, phase: dict) -> None:
    """phase.workflows[] 투영. module 보유 → 구조화 wf:WorkflowRef 노드(라운드트립),
    module 없는 doc-ref → wf:refersTo Literal(dual-rep, 템플릿 호환)."""
    for ref in (phase.get("workflows") or []):
        if not isinstance(ref, dict) or not ref.get("ref"):
            continue
        if ref.get("module"):
            wr = URIRef(str(phase_uri) + "_wref_" + _safe(ref["module"]))
            g.add((phase_uri, WF.hasWorkflowRef, wr))
            g.add((wr, RDF.type, WF.WorkflowRef))
            g.add((wr, WF.ref, Literal(str(ref["ref"]))))
            g.add((wr, WF.module, Literal(str(ref["module"]))))
            if "harness_propagate" in ref:
                g.add((wr, WF.harnessPropagate, Literal(bool(ref["harness_propagate"]))))
        else:
            g.add((phase_uri, WF.refersTo, Literal(str(ref["ref"]))))


# top-level non-phase 메타 블록(wf_node 의 phase-제외 키 + 소비자 x_* 확장).
# 임의 중첩 구조(scalar/list/dict)를 가질 수 있어 canonical JSON literal 로 무손실 보존.
_META_BLOCK_KEYS = ("workflow", "module", "meta", "metadata")


def _is_meta_block_key(key) -> bool:
    return key in _META_BLOCK_KEYS or str(key).startswith(("x_", "x-"))


def _project_meta_blocks(g: Graph, doc: dict) -> None:
    """workflow/module/meta/metadata + x_* 확장을 wf:MetaBlock(rawJson) 으로 무손실 투영.

    sort_keys 로 결정적, default=str 로 date 등 비-JSON 타입 안전화. 그래프 역할이 있는
    project/key_decisions/milestones/critical_dependencies/success_criteria 는 별도 구조화.
    """
    for key, val in doc.items():
        if not _is_meta_block_key(key) or not isinstance(val, (dict, list)):
            continue
        bn = WF["metablock/" + _safe(key)]
        g.add((bn, RDF.type, WF.MetaBlock))
        g.add((bn, WF.blockKey, Literal(str(key))))
        g.add((bn, WF.rawJson, Literal(
            json.dumps(val, sort_keys=True, ensure_ascii=False, default=str))))


def _project_narrative(g: Graph, doc: dict) -> None:
    """root-workflow narrative/meta 층 투영(무손실): project, key_decisions,
    success_criteria(top-level), critical_dependencies 서술. 그래프 층(criticalDep
    에지·Module 타입)은 build_graph 본문이 별도 투영(DAG 검사용)."""
    proj = doc.get("project")
    if isinstance(proj, dict):
        pju = WF["project/" + _safe(proj.get("id") or "_root")]
        g.add((pju, RDF.type, WF.Project))
        if proj.get("name"):
            g.add((pju, WF.label, Literal(str(proj["name"]))))
        if proj.get("version"):
            g.add((pju, WF.version, Literal(str(proj["version"]))))
        if proj.get("description"):
            g.add((pju, WF.description, Literal(str(proj["description"]))))
        if proj.get("owner"):
            g.add((pju, WF.owner, Literal(str(proj["owner"]))))
        if proj.get("created"):
            g.add((pju, WF.created, Literal(str(proj["created"]))))

    for kd in (doc.get("key_decisions") or []):
        if not isinstance(kd, dict):
            continue
        kn = WF["keydecision/" + _hash8(str(kd.get("decision", "")))]
        g.add((kn, RDF.type, WF.KeyDecision))
        if kd.get("decision"):
            g.add((kn, WF.decisionText, Literal(str(kd["decision"]))))
        if kd.get("rationale"):
            g.add((kn, WF.rationale, Literal(str(kd["rationale"]))))
        for im in (kd.get("impact_modules") or []):
            g.add((kn, WF.impactModule, Literal(str(im))))

    _project_meta_blocks(g, doc)

    # top-level success_criteria: list-of-single-key-dict (phase 의 list-of-string 과 다름)
    for sc in (doc.get("success_criteria") or []):
        if not isinstance(sc, dict):
            continue
        for k, v in sc.items():
            sn = WF["sc/" + _safe(k)]
            g.add((sn, RDF.type, WF.SuccessCriterion))
            g.add((sn, WF.scKey, Literal(str(k))))
            if v is not None:
                g.add((sn, WF.scValue, Literal(str(v))))


def build_graph(root_yaml: Path) -> tuple[Graph, "wf_node.ResolvedWorkflow"]:
    """resolve_workflow_tree → rdflib Graph 투영. (graph, resolved) 반환."""
    resolved = wf_node.resolve_workflow_tree(root_yaml)
    g = Graph()
    g.bind("wf", WF)
    g.bind("rdfs", RDFS)

    for src, doc in resolved.docs.items():
        if not isinstance(doc, dict):
            continue
        # ── root 스타일: 최상위 phases: 리스트 ──
        phases = doc.get("phases")
        # name→label / dependencies→dependsOn / workflows→refersTo 는 특수, 나머지 generic.
        _PHASE_SKIP = {"id", "name", "label", "dependencies", "workflows", "steps", "phases"}
        if isinstance(phases, list):
            for ph in phases:
                if not isinstance(ph, dict) or not ph.get("id"):
                    continue
                pu = _phase_uri(ph["id"])
                g.add((pu, RDF.type, WF.Phase))
                g.add((pu, WF.label, Literal(str(ph.get("label") or ph.get("name") or ph["id"]))))
                for dep in (ph.get("dependencies") or []):
                    g.add((pu, WF.dependsOn, _phase_uri(dep)))
                _project_workflows(g, pu, ph)
                _project_fields(g, pu, ph, _PHASE_SKIP)  # status/defaultJudge/showWrapper/artifacts/successCriteria
                _project_nodes(g, ph.get("steps", []), pu)
        # ── module 스타일: 이름붙은 phase 키(discovery/development/...) ──
        else:
            for phase_key, phase in wf_node._collect_phases(doc):
                pid = phase.get("id") or phase_key
                pu = _phase_uri(pid)
                g.add((pu, RDF.type, WF.Phase))
                g.add((pu, WF.label, Literal(str(phase.get("label") or phase.get("name") or pid))))
                _project_workflows(g, pu, phase)
                _project_fields(g, pu, phase, _PHASE_SKIP)
                _project_nodes(g, phase.get("steps", []), pu)

        # ── critical_dependencies: DAG 검사용 from→to 에지(Module) + 서술 보존용 노드(dual-rep) ──
        for cd in (doc.get("critical_dependencies") or []):
            if isinstance(cd, dict) and cd.get("from") and cd.get("to"):
                fu, tu = _module_uri(cd["from"]), _module_uri(cd["to"])
                g.add((fu, RDF.type, WF.Module))
                g.add((tu, RDF.type, WF.Module))
                g.add((fu, WF.criticalDep, tu))
                cdn = WF["criticaldep/" + _safe(cd["from"]) + "__" + _safe(cd["to"])]
                g.add((cdn, RDF.type, WF.CriticalDependency))
                g.add((cdn, WF.cdFrom, Literal(str(cd["from"]))))
                g.add((cdn, WF.cdTo, Literal(str(cd["to"]))))
                if cd.get("description"):
                    g.add((cdn, WF.description, Literal(str(cd["description"]))))

        # ── milestones: phase_ref + name/date/status(무손실) ──
        for ms in (doc.get("milestones") or []):
            if isinstance(ms, dict) and ms.get("id") and ms.get("phase_ref"):
                mu = WF["milestone/" + str(ms["id"])]
                g.add((mu, RDF.type, WF.Milestone))
                g.add((mu, WF.milestoneOf, _phase_uri(ms["phase_ref"])))
                if ms.get("name"):
                    g.add((mu, WF.label, Literal(str(ms["name"]))))
                if ms.get("date"):
                    g.add((mu, WF.milestoneDate, Literal(str(ms["date"]))))
                if ms.get("status"):
                    g.add((mu, WF.status, Literal(str(ms["status"]))))

        # ── narrative/meta 층(project, key_decisions, top-level success_criteria) ──
        _project_narrative(g, doc)

    return g, resolved


# ─── 검증 ────────────────────────────────────────────────────────────────────

_CYCLE_QUERY = """
PREFIX wf: <https://mso.dev/ontology/workflow#>
SELECT ?x WHERE { ?x (wf:dependsOn|wf:criticalDep)+ ?x }
"""


def find_cycles(g: Graph) -> list[str]:
    """비순환성 위반(자기 자신에게 도달하는 노드) 목록. 빈 리스트=DAG."""
    seen = []
    for row in g.query(_CYCLE_QUERY):
        uri = str(row[0])
        if uri not in seen:
            seen.append(uri)
    return seen


# 교차-스킬: workflow directories[].path ∈ scaffold(index) 등록 경로(모듈 fs 루트 자손).
# scaffold 해소는 wf_node._resolve_scaffold 재사용(중복 로직 안 만듦) → 멤버십만 SPARQL join.
_SCAFFOLD_QUERY = """
PREFIX wf: <https://mso.dev/ontology/workflow#>
SELECT ?step ?p WHERE {
  ?step wf:usesPathAbs ?p .
  FILTER NOT EXISTS {
    ?m wf:moduleRoot ?r .
    FILTER( ?p = ?r || STRSTARTS(?p, CONCAT(?r, "/")) )
  }
}
"""


def _iter_phases(doc):
    """root-style(phases: 리스트) + module-style(이름붙은 phase 키) 양쪽에서 phase dict 산출."""
    phases = doc.get("phases") if isinstance(doc, dict) else None
    if isinstance(phases, list):
        for ph in phases:
            if isinstance(ph, dict):
                yield ph
    else:
        for _, ph in wf_node._collect_phases(doc):
            yield ph


def check_scaffold(resolved, index_yaml: Path) -> list[str]:
    """directories[].path 가 scaffold 모듈 fs 루트의 자손인지 SPARQL containment join.

    wf_node 와 동일 의미(절대화·NFC·descendant). 위반은 warning 성격의 문자열 목록.
    """
    import unicodedata
    sc = wf_node._resolve_scaffold(index_yaml.resolve())
    jg = Graph()
    for root in sc.get("module_paths", {}).values():
        jg.add((WF["scaffold/module"], WF.moduleRoot,
                Literal(unicodedata.normalize("NFC", str(root)))))
    for src, doc in resolved.docs.items():
        for phase in _iter_phases(doc):
            for n in wf_node._walk_nodes(phase.get("steps", []) or []):
                for d in (n.get("directories") or []):
                    p = d.get("path") if isinstance(d, dict) else None
                    if not p:
                        continue
                    p_abs = unicodedata.normalize("NFC", str((src.parent / p).resolve()))
                    su = _node_uri(n.get("id", "?"))
                    jg.add((su, WF.usesPathAbs, Literal(p_abs)))
    out = []
    for row in jg.query(_SCAFFOLD_QUERY):
        out.append(f"{str(row[0]).rsplit('/', 1)[-1]}: scaffold 미등록 경로 {row[1]}")
    return out


def run_shacl(g: Graph) -> tuple[bool, str]:
    """pyshacl 로 ABox↔TBox 정합 검증. (conforms, report_text).

    추론은 끈다(inference="none"). 투영기가 노드를 specific class + wf:Node 로
    명시 타입핑하므로 sh:class 제약이 추론 없이 성립한다. rdfs 추론을 켜면
    rdfs:range 가 dependsOn 타깃을 자동 Phase 로 타입핑해 range 검증이 무의미해지는
    OWA 함정을 피한다 — range 위반(잘못된 타깃)을 진짜로 잡으려면 추론을 꺼야 한다.
    """
    try:
        from pyshacl import validate as shacl_validate
    except ImportError:
        return True, "[skip] pyshacl 미설치 — shape 검증 생략"
    shapes = Graph().parse(str(SHAPES), format="turtle")
    conforms, _, text = shacl_validate(
        g, shacl_graph=shapes, inference="none", advanced=True, meta_shacl=False,
    )
    return conforms, text


def validate(root_yaml: Path, index_yaml: Path | None = None) -> dict:
    g, resolved = build_graph(root_yaml)
    tree_issues = [str(i) for i in resolved.issues]
    cycles = find_cycles(g)
    conforms, shacl_text = run_shacl(g)
    # 교차-스킬(scaffold) 경로 멤버십은 warning — ok 를 뒤집지 않는다(wf_node 와 동일 severity).
    scaffold_warnings = check_scaffold(resolved, index_yaml) if index_yaml else []
    ok = conforms and not cycles and not tree_issues
    return {
        "ok": ok,
        "triples": len(g),
        "cycles": cycles,
        "shacl_conforms": conforms,
        "shacl_report": shacl_text if not conforms else "",
        "tree_issues": tree_issues,
        "scaffold_warnings": scaffold_warnings,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wf_to_ttl",
        description="workflow YAML → TTL 투영 + shape/DAG 검증")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serialize", help="TTL 직렬화 (stdout)")
    s.add_argument("workflow")
    v = sub.add_parser("validate", help="shape(SHACL) + 비순환성(SPARQL) 검증")
    v.add_argument("workflow")
    v.add_argument("--index", default=None,
                   help="scaffold index.yaml — directories[].path 교차-스킬 멤버십 검증(warning)")
    v.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    wf_path = Path(args.workflow).resolve()
    if not wf_path.exists():
        print(f"파일 없음: {wf_path}", file=sys.stderr)
        return 2

    if args.cmd == "serialize":
        g, _ = build_graph(wf_path)
        print(g.serialize(format="turtle"))
        return 0

    if args.cmd == "validate":
        idx = Path(args.index).resolve() if args.index else None
        res = validate(wf_path, index_yaml=idx)
        if args.json:
            import json
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"triples={res['triples']}  ok={res['ok']}")
            if res["tree_issues"]:
                print("✗ 트리 이슈:")
                for i in res["tree_issues"]:
                    print(f"  - {i}")
            if res["cycles"]:
                print("✗ 의존 사이클(다운스트림 재참조):")
                for c in res["cycles"]:
                    print(f"  - {c}")
            if not res["shacl_conforms"]:
                print("✗ SHACL 로컬 shape 위반:")
                print(res["shacl_report"])
            if res.get("scaffold_warnings"):
                print("⚠ scaffold 교차-스킬(directories.path):")
                for w in res["scaffold_warnings"]:
                    print(f"  - {w}")
            if res["ok"]:
                tail = " (scaffold 경고 있음)" if res.get("scaffold_warnings") else ""
                print("✓ DAG 비순환 + 로컬 shape 통과" + tail)
        return 0 if res["ok"] else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
