#!/usr/bin/env python3
"""validate_artifact_layer.py — artifact 층(TTL registry)과 workflow Stream 을 SHACL/SPARQL 로 검증한다.

두 층: 개념(wf:RegisteredArtifact, 안정된 IRI)과 규약 버전(wf:ArtifactConvention). 규약 버전 하나는
(namingConvention, fileFormat, directoryTemplate) + 변수(hasParam) + 메타데이터 스키마(hasMetadata) + 유효 구간
(validFrom 포함, validUntil 제외)이다. 템플릿 변수는 [name] 이고 정규식으로 컴파일되어 파일 규약 검사에 쓰인다.

데이터 그래프 = artifact registry(artifacts.abox.ttl) + workflow ABox(*.abox.ttl, drafts/ 제외).
형상 = references/shapes/workflow-artifact-layer-shapes.ttl, 어휘 = references/tbox/workflow-artifact-layer-tbox.ttl.
SHACL 이 못 보는 것은 파이썬이 보조한다:
  (1) 디렉토리 층(index.yaml) 교차 점검,
  (2) 규약 불변: git HEAD 에 이미 커밋된 규약의 세 요소가 바뀌었거나 삭제됐으면 Violation(바꾸려면 새 규약 + supersededBy),
  (3) --scan: 파일이 규약에 맞는지(항목 날짜로 유효 규약을 골라 검사), 필수 메타데이터 누락(적용 규약 기준과 현행 규약 대비 갭).

사용법:
  validate_artifact_layer.py [--root R] [--registry P] [--workflow-dir D] [--index P] [--scan] [--json P] [--strict] [--no-history-check]
종료 코드: Violation 또는 교차 층 오류가 있으면 1 (--strict 는 Warning 도)
필요: rdflib, pyshacl, PyYAML
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

REFS = Path(__file__).resolve().parent.parent / "references"
SH = "http://www.w3.org/ns/shacl#"
VAR = re.compile(r"\[([A-Za-z_][A-Za-z0-9_]*)\]")
DATE_IN_PATH = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")


def compile_template(directory: str, name: str, fmt: str, params: dict[str, str]) -> re.Pattern:
    """[var] 를 변수별 정규식 그룹으로 바꿔 전체 경로(상대) 정규식을 만든다. 같은 변수는 같은 값(역참조)."""
    seen: set[str] = set()

    def part(text: str) -> str:
        out, pos = [], 0
        for m in VAR.finditer(text):
            out.append(re.escape(text[pos:m.start()]))
            v = m.group(1)
            if v in seen:
                out.append(f"(?P={v})")
            else:
                seen.add(v)
                out.append(f"(?P<{v}>{params.get(v, '[^/]+')})")
            pos = m.end()
        out.append(re.escape(text[pos:]))
        return "".join(out)

    return re.compile("^" + part(directory) + part(name) + re.escape("." + fmt) + "$")


def literal_prefix(directory: str) -> str:
    """첫 변수가 나오기 전까지의 완전한 디렉토리 부분. 변수로 시작하면 빈 문자열."""
    head = directory.split("[", 1)[0]
    return head[: head.rfind("/") + 1]


def index_modules(index: Path) -> dict[str, str]:
    if not index.is_file():
        return {}
    d = yaml.safe_load(index.read_text(encoding="utf-8")) or {}
    return {str(m["id"]): str(m.get("path", "")).strip("/") for m in d.get("modules") or [] if m.get("id")}


def frontmatter_keys(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:6000]
    except OSError:
        return set()
    m = re.match(r"\A---\n(.*?)\n---", text, re.S)
    return set(re.findall(r"^([A-Za-z_][\w-]*):", m.group(1), re.M)) if m else set()


def item_date(rel: str) -> str | None:
    """경로에서 항목 날짜를 읽는다(첫 날짜 표기). 월만 있으면 그 달 1일. 없으면 None."""
    m = DATE_IN_PATH.search(rel)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3) or '01'}" if m else None


def shape_of(rel: str) -> str:
    """분류되지 않은 파일의 형태(군집용): 날짜, 버전 번호, 파일 이름 뒷부분을 뭉갠다."""
    parts = rel.split("/")
    out = []
    for seg in parts[:-1]:
        seg = re.sub(r"^\d{4}-\d{2}-\d{2}_.*", "DATE_slug", seg)
        seg = re.sub(r"^\d{4}-\d{2}_.*", "MONTH_slug", seg)
        seg = re.sub(r"^\d{4}-\d{2}$", "MONTH", seg)
        out.append(seg)
    stem, _, ext = parts[-1].rpartition(".")
    lead = re.match(r"[A-Za-z][A-Za-z-]*", stem)
    out.append(f"{lead.group(0) if lead else '*'}*.{ext}" if stem else parts[-1])
    return "/".join(out)


def short(s) -> str:
    return str(s).rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def conventions(data, WF) -> list[dict]:
    """registry 의 모든 규약 버전. 한 규약은 정확히 한 개념에 속한다(어긋나면 SHACL 이 잡는다)."""
    from rdflib.namespace import RDF
    out = []
    for concept in sorted(data.subjects(RDF.type, WF.RegisteredArtifact), key=str):
        for c in sorted(data.objects(concept, WF.hasConvention), key=str):
            d, n, f = data.value(c, WF.directoryTemplate), data.value(c, WF.namingConvention), data.value(c, WF.fileFormat)
            if d is None or n is None or f is None:
                continue
            params: dict[str, str] = {}
            for p in data.objects(c, WF.hasParam):
                nm = data.value(p, WF.paramName)
                rx = data.value(p, WF.paramRegex) or data.value(data.value(p, WF.paramType), WF.paramRegex)
                if nm is not None and rx is not None:
                    params[str(nm)] = str(rx)
            vf, vu = data.value(c, WF.validFrom), data.value(c, WF.validUntil)
            required = [str(data.value(m, WF.fieldName)) for m in data.objects(c, WF.hasMetadata)
                        if data.value(m, WF.fieldRequired) is not None and bool(data.value(m, WF.fieldRequired).toPython())]
            out.append({"concept": short(concept), "concept_iri": concept, "conv": short(c), "conv_iri": c,
                        "dir": str(d), "naming": str(n), "fmt": str(f), "prefix": literal_prefix(str(d)),
                        "rx": compile_template(str(d), str(n), str(f), params), "required": required,
                        "valid_from": str(vf) if vf is not None else None, "valid_until": str(vu) if vu is not None else None,
                        "module": str(data.value(concept, WF.inModule)) if data.value(concept, WF.inModule) is not None else None})
    return out


def valid_at(conv: dict, dt: str | None) -> bool:
    """항목 날짜가 규약의 유효 구간(validFrom 포함, validUntil 제외)에 드는가. 날짜를 모르면 구간을 따지지 않는다."""
    if dt is None:
        return True
    return (conv["valid_from"] is None or dt >= conv["valid_from"]) and (conv["valid_until"] is None or dt < conv["valid_until"])


def scan_registry(data, WF, root: Path, cap: int = 60000) -> dict:
    """registry 전체 기준으로 파일을 분류한다. 항목 날짜로 유효 규약을 고르고, 맞으면 분류됨, 규약은 맞지만 기간 밖이면 stale,
    어느 규약에도 안 맞으면 미분류(날짜가 가장 늦은 validUntil 이전이면 legacy, 날짜 불명이면 undated, 그 외 현행 미분류)."""
    convs = conventions(data, WF)
    stats = {}
    for c in convs:
        stats.setdefault(c["concept"], {"matched": 0, "stale": 0, "meta_checked": 0, "meta_missing": 0, "gap_checked": 0, "gap_missing": 0,
                                        "conventions": []})["conventions"].append(c["conv"])
    result = {"roots": [], "artifacts": stats, "skipped": sorted({c["concept"] for c in convs if not c["prefix"]})}
    prefixes = sorted({c["prefix"] for c in convs if c["prefix"]})
    roots = [p for p in prefixes if not any(q != p and p.startswith(q) for q in prefixes)]
    for pre in roots:
        if not (root / pre).is_dir():
            continue
        cover = [c for c in convs if c["prefix"].startswith(pre)]
        cuts = [c["valid_until"] for c in cover if c["valid_until"]]
        legacy_cut = max(cuts) if cuts else None
        total = matched = stale = legacy = undated = violation = 0
        shapes: dict[str, dict] = {}
        for dp, _, fns in os.walk(root / pre):
            for fn in fns:
                if fn.startswith("."):
                    continue
                rel = str(Path(dp, fn).relative_to(root)); total += 1
                cand = [c for c in cover if rel.startswith(c["prefix"]) and c["rx"].match(rel)]
                dt = item_date(rel[len(pre):])
                valid = [c for c in cand if valid_at(c, dt)]
                if valid:
                    matched += 1
                    done = set()
                    for c in valid:
                        if c["concept"] in done:
                            continue
                        done.add(c["concept"])
                        st = stats[c["concept"]]; st["matched"] += 1
                        if c["fmt"] != "md":
                            continue
                        keys = None
                        if c["required"] and st["meta_checked"] < 400:
                            keys = frontmatter_keys(root / rel)
                            st["meta_checked"] += 1
                            st["meta_missing"] += not set(c["required"]) <= keys
                        cur = next((x for x in convs if x["concept"] == c["concept"] and x["valid_until"] is None), None)
                        if cur and cur is not c and cur["required"] and st["gap_checked"] < 400:   # 옛 규약 항목이 현행 규약을 충족하는가
                            keys = keys if keys is not None else frontmatter_keys(root / rel)
                            st["gap_checked"] += 1
                            st["gap_missing"] += not set(cur["required"]) <= keys
                elif cand:
                    stale += 1
                    for c in cand:
                        stats[c["concept"]]["stale"] += 1
                else:
                    kind = "legacy" if (legacy_cut and dt and dt < legacy_cut) else ("undated" if dt is None else "violation")
                    legacy += kind == "legacy"; undated += kind == "undated"; violation += kind == "violation"
                    sh = shapes.setdefault(shape_of(rel[len(pre):]), {"n": 0, "kind": kind, "example": rel})
                    sh["n"] += 1
            if total >= cap:
                break
        top = sorted(shapes.items(), key=lambda kv: -kv[1]["n"])[:12]
        result["roots"].append({"prefix": pre, "total": total, "matched": matched, "stale": stale, "legacy": legacy, "undated": undated,
                                "violation": violation, "legacy_before": legacy_cut,
                                "unclassified_shapes": [{"shape": k, **v} for k, v in top]})
    return result


def print_scan(res: dict) -> None:
    print("\n[파일 규약 스캔] registry 전체 기준 분류 (분류됨 / 기간 밖 규약 / 레거시 / 날짜 불명 / 현행 미분류)\n"
          "  현행 미분류 = 정의되지 않은 파일 종류이거나 규약 이탈. 둘의 구분은 형태 목록과 프로젝트 규칙으로 판단한다.")
    for r in res["roots"]:
        pct = 100 * r["matched"] / r["total"] if r["total"] else 0
        cut = f", 마지막 종료 규약 {r['legacy_before']}" if r["legacy_before"] else ""
        print(f"  {r['prefix']}  파일 {r['total']}: 분류됨 {r['matched']} ({pct:.0f}%), 기간 밖 {r['stale']}, 레거시 {r['legacy']}, 날짜 불명 {r['undated']}, 현행 미분류 {r['violation']}{cut}")
        for s in r["unclassified_shapes"][:6]:
            print(f"      미분류 {({'violation': '현행'}.get(s['kind'], s['kind'])):7}{s['n']:5}  {s['shape']}")
    for n, a in res["artifacts"].items():
        parts = []
        if a["meta_checked"]:
            parts.append(f"적용 규약 기준 누락 {a['meta_missing']}/{a['meta_checked']}")
        if a["gap_checked"]:
            parts.append(f"현행 규약 대비 갭 {a['gap_missing']}/{a['gap_checked']}")
        if parts:
            print(f"  메타데이터 {n}: " + ", ".join(parts))
    if res["skipped"]:
        print(f"  (디렉토리가 변수로 시작해 건너뜀: {', '.join(res['skipped'])})")


def history_violations(root: Path, reg: Path, data, WF) -> list[str] | None:
    """git HEAD 의 registry 와 비교해, 이미 커밋된 규약의 세 요소가 바뀌었거나 삭제됐으면 보고한다. git 이력이 없으면 None."""
    from rdflib import Graph
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()
        rel = os.path.relpath(reg.resolve(), Path(top).resolve())
        old_ttl = subprocess.run(["git", "-C", top, "show", f"HEAD:{rel}"], capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    old = Graph(); old.parse(data=old_ttl, format="turtle")
    out = []
    for c in sorted(old.objects(None, WF.hasConvention), key=str):
        name = short(c)
        if (c, None, None) not in data:
            out.append(f"{name}: 이미 커밋된 규약이 삭제됨(삭제 대신 validUntil + supersededBy)")
            continue
        for prop, label in ((WF.directoryTemplate, "directoryTemplate"), (WF.namingConvention, "namingConvention"), (WF.fileFormat, "fileFormat")):
            if old.value(c, prop) != data.value(c, prop):
                out.append(f"{name}: 이미 커밋된 규약의 {label} 이 바뀜 '{old.value(c, prop)}' → '{data.value(c, prop)}' (새 규약 + supersededBy 로 바꿀 것)")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--registry", default="agent-context/index/artifacts.abox.ttl")
    ap.add_argument("--workflow-dir", default="agent-context/workflow")
    ap.add_argument("--index", default="agent-context/index/index.yaml")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--json", help="--scan 결과를 JSON 으로 저장할 경로")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--no-history-check", action="store_true", help="git HEAD 와의 규약 불변 비교를 건너뛴다")
    a = ap.parse_args(argv)
    try:
        from pyshacl import validate
        from rdflib import Graph, Namespace, URIRef
        from rdflib.namespace import RDF
    except ImportError as e:  # pragma: no cover
        print(f"필요한 패키지가 없습니다: {e} (rdflib, pyshacl)"); return 2
    WF = Namespace("https://mso.dev/ontology/workflow#")
    root = Path(a.root).resolve()
    reg = root / a.registry
    if not reg.is_file():
        print(f"artifact registry 가 없습니다: {reg}"); return 2

    data = Graph(); data.parse(reg, format="turtle")
    wdir = root / a.workflow_dir
    wf_files = sorted(wdir.glob("*.abox.ttl")) if wdir.is_dir() else []
    for f in wf_files:
        data.parse(f, format="turtle")
    shapes = Graph(); shapes.parse(REFS / "shapes" / "workflow-artifact-layer-shapes.ttl", format="turtle")
    tbox = Graph(); tbox.parse(REFS / "tbox" / "workflow-artifact-layer-tbox.ttl", format="turtle")
    data += tbox   # 유형·변수형식 개체를 데이터 쪽에서도 읽을 수 있어야 SPARQL 이 동작한다

    conforms, results, _ = validate(data, shacl_graph=shapes, ont_graph=tbox, inference="none", advanced=True, allow_warnings=True)
    items = []
    for r in results.subjects(RDF.type, URIRef(SH + "ValidationResult")):
        sev = str(results.value(r, URIRef(SH + "resultSeverity"))).split("#")[-1]
        items.append((sev, str(results.value(r, URIRef(SH + "focusNode"))), str(results.value(r, URIRef(SH + "resultMessage")))))
    concepts = sorted(data.subjects(RDF.type, WF.RegisteredArtifact), key=str)
    convs = conventions(data, WF)
    print(f"registry: {reg}\nworkflow ABox {len(wf_files)}개, 개념 {len(concepts)}개, 규약 버전 {len(convs)}개\n")

    cross = []
    mods = index_modules(root / a.index)
    for c in convs:
        mod = c["module"]
        if mods and mod is not None and mod not in mods:
            cross.append(f"{c['conv']}: inModule '{mod}' 가 index.yaml 에 없습니다(교차 층)")
        pre = c["prefix"]
        if mods and mod in mods and pre:
            mp = mods[mod]
            if not (pre.strip("/") == mp or pre.startswith(mp + "/")):
                cross.append(f"{c['conv']}: directoryTemplate '{c['dir']}' 가 module '{mod}'({mp}/) 아래에 없습니다(교차 층)")
        if pre and not (root / pre).is_dir():
            items.append(("Warning", str(c["conv_iri"]), f"디렉토리가 존재하지 않습니다: {pre}"))
    if not a.no_history_check:
        hv = history_violations(root, reg, data, WF)
        for h in hv or []:
            cross.append(h)

    order = {"Violation": 0, "Warning": 1, "Info": 2}
    for sev, node, msg in sorted(items, key=lambda x: (order.get(x[0], 3), x[1])):
        print(f"{sev.upper():10}{short(node):30}{msg}")
    for c in cross:
        print(f"{'VIOLATION':10}{c}")

    if a.scan:
        res = scan_registry(data, WF, root)
        print_scan(res)
        if a.json:
            import json
            Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    nv = sum(1 for i in items if i[0] == "Violation") + len(cross)
    nw = sum(1 for i in items if i[0] == "Warning")
    print(f"\n결과: Violation {nv}건, Warning {nw}건")
    return 1 if nv or (a.strict and nw) else 0


if __name__ == "__main__":
    sys.exit(main())
