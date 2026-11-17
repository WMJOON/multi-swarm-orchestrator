#!/usr/bin/env python3
"""wm_gen_vocab.py — references/metadata-spec.yaml 에서 metadata TBox 와 SHACL shapes 를 생성한다 (v0.16.0).

  references/tbox/work-memory-metadata-tbox.ttl      클래스(Agent/User/SoftwareAgent/BackgroundAgent/Module/통제 어휘),
                                                     통제 어휘 individual, metadata 프로퍼티(ObjectProperty/DatatypeProperty)
  references/shapes/work-memory-metadata-shapes.ttl  타입별 값 제약(sh:class/sh:datatype/maxCount) +
                                                     enforce_from 이후 기록의 필수 metadata(sh:sparql)

생성 파일은 직접 편집하지 않는다. `--check` 는 생성 결과가 디스크의 파일과 같은지 검사한다(CI/테스트용).
표기: Class = UpperCamelCase, property·individual = lowerCamelCase.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wm_metadata  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
TBOX_OUT = SKILL_DIR / "references" / "tbox" / "work-memory-metadata-tbox.ttl"
SHAPES_OUT = SKILL_DIR / "references" / "shapes" / "work-memory-metadata-shapes.ttl"
SPEC_JSON_OUT = SKILL_DIR / "references" / "metadata-spec.json"  # stdlib 전용 소비자(복사되는 훅, wm_store)용 — YAML 을 못 읽는다

WM_NS = "https://mso.dev/ontology/work-memory#"
VOCAB_NS = "https://mso.dev/id/vocab/"
HEADER = "# ⚠ GENERATED — 직접 편집 금지.\n# 소스: references/metadata-spec.yaml  (생성: scripts/wm_gen_vocab.py)\n"

XSD = {"string": "xsd:string", "boolean": "xsd:boolean", "integer": "xsd:integer",
       "dateTime": "xsd:dateTime", "json": "xsd:string"}


def _prop_range(defn: dict, spec: dict) -> str:
    if defn["kind"] == "datatype":
        return XSD[defn["datatype"]]
    if "vocab" in defn:
        return "wm:" + spec["vocabularies"][defn["vocab"]]["class"]
    if defn["range"] in (spec.get("structures") or {}):
        return "wm:" + spec["structures"][defn["range"]]["class"]
    return "wm:" + {"Agent": "Agent", "Module": "Module", "Entry": "Entry"}[defn["range"]]


def _collect_properties(spec: dict) -> dict[str, dict]:
    """프로퍼티 이름 → 정의. 같은 이름이 여러 타입에 나오면 정의가 같아야 한다."""
    props: dict[str, dict] = {}

    def add(defn: dict, where: str):
        name = defn["property"]
        if wm_metadata.is_external(name):
            return  # 외부 어휘 프로퍼티(skos:scopeNote 등)는 wm: 에 선언하지 않는다
        shape = {"kind": defn["kind"], "range": _prop_range(defn, spec)}
        if name in props and props[name] != shape:
            raise SystemExit(f"[ERROR] 프로퍼티 {name} 의 정의가 타입마다 다르다 ({where}): {props[name]} vs {shape}")
        props[name] = shape

    for key, defn in (spec.get("common") or {}).items():
        add(defn, f"common.{key}")
    for tname, t in spec["types"].items():
        for key, defn in (t.get("metadata") or {}).items():
            add(defn, f"{tname}.{key}")
    return props


def gen_tbox(spec: dict) -> str:
    out = [HEADER,
           "@prefix wm: <https://mso.dev/ontology/work-memory#> .",
           "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
           "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
           "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
           "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .", ""]
    cls = spec["agents"]["classes"]
    out += [
        "# ── 주체(Agent): 소속(계정 주인)과 백그라운드 에이전트를 구분한다 ──",
        "wm:Agent a owl:Class ; rdfs:label \"Agent\"@ko ;",
        "    rdfs:comment \"기록을 쓰거나 보고한 주체.\"@ko .",
        f"wm:{cls['user']} a owl:Class ; rdfs:subClassOf wm:Agent ; rdfs:label \"{cls['user']}\"@ko ;",
        "    rdfs:comment \"사람(계정 주인).\"@ko .",
        f"wm:{cls['softwareAgent']} a owl:Class ; rdfs:subClassOf wm:Agent ; rdfs:label \"{cls['softwareAgent']}\"@ko ;",
        "    rdfs:comment \"사용자를 대신해 일하는 에이전트. onBehalfOf 로 계정 주인(User)을 가리킨다.\"@ko .",
        f"wm:{cls['backgroundAgent']} a owl:Class ; rdfs:subClassOf wm:{cls['softwareAgent']} ; rdfs:label \"{cls['backgroundAgent']}\"@ko ;",
        "    rdfs:comment \"사용자 턴 밖에서 도는 에이전트(훅, 예약 작업, 자동 커밋 등). trigger 로 구분한다.\"@ko .",
        "wm:agentId a owl:DatatypeProperty ; rdfs:domain wm:Agent ; rdfs:range xsd:string .",
        f"wm:onBehalfOf a owl:ObjectProperty ; rdfs:domain wm:{cls['softwareAgent']} ; rdfs:range wm:{cls['user']} ;",
        "    rdfs:comment \"이 에이전트가 소속된 계정 주인.\"@ko .",
        f"wm:trigger a owl:DatatypeProperty ; rdfs:domain wm:{cls['backgroundAgent']} ; rdfs:range xsd:string ;",
        "    rdfs:comment \"백그라운드 에이전트를 띄운 요인 (예: hook, schedule).\"@ko .",
        "",
        "wm:Module a owl:Class ; rdfs:label \"Module\"@ko ;",
        "    rdfs:comment \"스캐폴드 index 의 module id(modules[].id, index.abox.ttl 의 wf:moduleId 에 대응). IRI 는 https://mso.dev/id/module/<id>.\"@ko .",
        "wm:moduleId a owl:DatatypeProperty ; rdfs:domain wm:Module ; rdfs:range xsd:string .",
        "",
        "# ── 통제 어휘 (Class = UpperCamelCase, individual = lowerCamelCase) ──",
    ]
    for vname, v in spec["vocabularies"].items():
        out.append(f"wm:{v['class']} a owl:Class ; rdfs:label \"{v['class']}\"@ko .")
        for item in v["values"]:
            iri = f"<{VOCAB_NS}{vname}/{item['id']}>"
            out.append(f"{iri} a wm:{v['class']} ; rdfs:label \"{item['value']}\"@ko .")
        out.append("")
    out.append("# ── 구조화 값(노드) ──")
    for sname, st in (spec.get("structures") or {}).items():
        out.append(f"wm:{st['class']} a owl:Class ; rdfs:label \"{st['class']}\"@ko ;")
        out.append(f"    rdfs:comment \"구조화된 metadata 값. IRI 는 <entry IRI>/{st['class'].lower()}/<{st['key']}>.\"@ko .")
        for k, pd in st["properties"].items():
            out.append(f"wm:{pd['property']} a owl:DatatypeProperty ; rdfs:domain wm:{st['class']} ; rdfs:range {XSD[pd['datatype']]} .")
    out.append("")
    out.append("# 외부 어휘 프로퍼티: 적용 범위 서술(scope 류)은 skos:scopeNote 를 쓴다(주석 프로퍼티).")
    out.append("skos:scopeNote a owl:AnnotationProperty .")
    out.append("")
    out.append("# ── metadata 프로퍼티 (lowerCamelCase). object = 개체/통제 어휘, datatype = 자유 서술·숫자·날짜·버전 ──")
    for name, p in sorted(_collect_properties(spec).items()):
        kind = "owl:ObjectProperty" if p["kind"] == "object" else "owl:DatatypeProperty"
        out.append(f"wm:{name} a {kind} ; rdfs:domain wm:Entry ; rdfs:range {p['range']} .")
    return "\n".join(out) + "\n"


def gen_shapes(spec: dict) -> str:
    out = [HEADER,
           "@prefix wm: <https://mso.dev/ontology/work-memory#> .",
           "@prefix sh: <http://www.w3.org/ns/shacl#> .",
           "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
           "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .", ""]
    cls = spec["agents"]["classes"]
    cutoff = wm_metadata._iso_prefix(spec["enforce_from"])
    out += [
        f"wm:SoftwareAgentOwnerShape a sh:NodeShape ; sh:targetClass wm:{cls['softwareAgent']} ;",
        "    sh:property [ sh:path wm:onBehalfOf ; sh:class wm:" + cls["user"] + " ; sh:minCount 1 ; sh:maxCount 1 ;",
        "        sh:severity sh:Warning ; sh:message \"SoftwareAgent 는 소속(계정 주인, onBehalfOf)을 가져야 한다\" ] .",
        "",
    ]
    for sname, st in (spec.get("structures") or {}).items():
        parts = []
        for k, pd in st["properties"].items():
            parts.append(f"    sh:property [ sh:path wm:{pd['property']} ; sh:datatype {XSD[pd['datatype']]} ; sh:maxCount 1 ]")
        # key 만 SHACL 로 필수(IRI 를 만드는 값). 나머지 필수는 wm_node validate 가 새 기록에서만 강제한다(옛 기록 tolerant).
        key_prop = st["properties"][st["key"]]["property"]
        parts.append(f"    sh:property [ sh:path wm:{key_prop} ; sh:minCount 1 ]")
        out.append(f"wm:{st['class']}Shape a sh:NodeShape ; sh:targetClass wm:{st['class']} ;")
        out.append(" ;\n".join(parts) + " .")
        out.append("")
    for tname, t in spec["types"].items():
        defs = wm_metadata.type_metadata(spec, tname)
        out.append(f"wm:{t['class']}MetadataShape a sh:NodeShape ; sh:targetClass wm:{t['class']} ;")
        parts = []
        for key, d in defs.items():
            rng = _prop_range(d, spec)
            prop = d["property"] if wm_metadata.is_external(d["property"]) else f"wm:{d['property']}"
            if d["kind"] == "datatype":
                constraint = f"sh:datatype {rng}"
            else:
                constraint = f"sh:class {rng}"
            max_count = "" if d.get("multiple") else " ; sh:maxCount 1"
            parts.append(f"    sh:property [ sh:path {prop} ; {constraint}{max_count} ]")
        for key, d in defs.items():
            if not d.get("required"):
                continue
            prop = f"{WM_NS}{d['property']}"
            msg = f"metadata.{key} 필수 ({tname}, {cutoff} 이후 기록)"
            parts.append(
                "    sh:sparql [ a sh:SPARQLConstraint ;\n"
                f"        sh:message \"{msg}\" ;\n"
                "        sh:select \"\"\"\n"
                "            SELECT $this WHERE {\n"
                f"              $this <{WM_NS}createdAt> ?c .\n"
                f"              FILTER(SUBSTR(STR(?c), 1, 19) >= \"{cutoff}\")\n"
                f"              FILTER NOT EXISTS {{ $this <{WM_NS}needsReview> true }}\n"
                f"              FILTER NOT EXISTS {{ $this <{prop}> ?v }}\n"
                "            }\"\"\" ]")
        out.append(" ;\n".join(parts) + " .")
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="디스크의 생성 파일이 명세와 같은지만 검사(쓰지 않음)")
    args = ap.parse_args(argv)
    spec = wm_metadata.load_spec()
    import json
    outputs = {TBOX_OUT: gen_tbox(spec), SHAPES_OUT: gen_shapes(spec),
               SPEC_JSON_OUT: json.dumps(spec, ensure_ascii=False, indent=1, sort_keys=False) + "\n"}
    if args.check:
        stale = [str(p) for p, text in outputs.items() if not p.is_file() or p.read_text(encoding="utf-8") != text]
        if stale:
            print("[STALE] 명세와 다름 — wm_gen_vocab.py 를 실행하세요: " + ", ".join(stale), file=sys.stderr)
            return 1
        print("✓ 생성 파일이 명세와 같다")
        return 0
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
        print(f"생성: {path.relative_to(SKILL_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
