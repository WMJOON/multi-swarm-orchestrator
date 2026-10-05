#!/usr/bin/env python3
"""check_artifact_index.py — workflow TTL 의 artifact/경로 참조가 index.yaml 에 매핑되는지 점검 (읽기 전용).

SKILL.md 의존 규칙 2("artifact stream 의 경로가 index 또는 data_registry 에 연결되는지 확인")를 도구로 만든 것.

참조로 보는 것 (workflow ABox 의 literal 값):
  wf:locator, wf:directory, wf:dirPath, wf:deliverables, wf:targetArtifact, wf:orderArtifact
판정:
  mapped-registry  data_registry[].locator 와 일치 (-> index:<id>)
  mapped-module    modules[]/subdirs[] 경로 아래의 local path
  external         Firestore:/Storage:/http(s)/mcp:// 등 외부 locator 인데 data_registry 에 없음
  unmapped-path    local path 인데 어느 module 아래도 아님

사용법:
  check_artifact_index.py [--root R] [--index agent-context/index/index.yaml] [--workflow-dir agent-context/workflow]
                          [--suggest] [--strict]
  --suggest  미등록 외부 locator 의 data_registry 항목 초안을 출력(파일은 수정하지 않는다)
  --strict   매핑 안 된 참조가 있으면 종료 코드 1
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

WF = "https://mso.dev/ontology/workflow#"
PROPS = ["locator", "directory", "dirPath", "deliverables", "targetArtifact", "orderArtifact"]
EXTERNAL = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*://|[A-Za-z][A-Za-z0-9_-]*:(?!/))")


def load_index(path: Path, seen: set | None = None) -> dict:
    """index.yaml 과 sub_index 를 펼쳐 {modules: [path], registry: {locator: id}} 로 만든다."""
    seen = seen or set()
    path = path.resolve()
    if path in seen or not path.is_file():
        return {"modules": [], "registry": {}}
    seen.add(path)
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {"modules": [], "registry": {}}
    for m in d.get("modules") or []:
        p = str(m.get("path", "")).strip("/")
        if p:
            out["modules"].append(p)
        for s in m.get("subdirs") or []:
            sp = str(s.get("path", "")).strip("/")
            if sp:
                out["modules"].append(f"{p}/{sp}".strip("/"))
        if m.get("sub_index"):
            sub = load_index(path.parent / p / m["sub_index"] if p else path.parent / m["sub_index"], seen)
            out["modules"] += [f"{p}/{x}".strip("/") for x in sub["modules"]]
            out["registry"].update(sub["registry"])
    for r in d.get("data_registry") or []:
        if r.get("locator") and r.get("id"):
            out["registry"][str(r["locator"])] = str(r["id"])
    return out


def load_registry_file(path: Path) -> dict:
    """artifact 층 TTL registry(artifacts.abox.ttl)의 {디렉토리 템플릿의 고정 접두부 또는 id: id}. 디렉토리 층(index.yaml)과 분리된 정본이다."""
    out = {}
    if not path.is_file():
        return out
    try:
        from rdflib import Graph, Namespace
        from rdflib.namespace import RDF
    except ImportError:  # rdflib 없으면 registry 매핑은 건너뛴다
        return out
    WFN = Namespace(WF)
    g = Graph()
    g.parse(path, format="turtle")
    for s in g.subjects(RDF.type, WFN.RegisteredArtifact):
        aid = str(s).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        out[aid] = aid
        for conv in g.objects(s, WFN.hasConvention):             # 규약 버전마다 디렉토리 접두부를 매핑
            for dtmpl in g.objects(conv, WFN.directoryTemplate):
                pre = str(dtmpl).split("[", 1)[0]
                pre = pre[: pre.rfind("/") + 1]    # 첫 변수 앞의 완전한 디렉토리
                if pre:
                    out[pre] = aid
    return out


def references(workflow_dir: Path) -> list[dict]:
    from rdflib import Graph, Literal, URIRef
    from rdflib.namespace import RDF

    refs = []
    for ttl in sorted(workflow_dir.glob("*.ttl")):
        g = Graph()
        try:
            g.parse(ttl, format="turtle")
        except Exception as e:  # noqa: BLE001
            refs.append({"file": ttl.name, "node": "-", "prop": "-", "value": f"(TTL 파싱 실패: {e})", "kind": "parse-error"})
            continue
        for prop in PROPS:
            for s, _, o in g.triples((None, URIRef(WF + prop), None)):
                if isinstance(o, Literal):
                    types = {t.split("#")[-1] for t in g.objects(s, RDF.type)}
                    refs.append({"file": ttl.name, "node": str(s).split("#")[-1] or str(s), "prop": prop, "value": str(o), "types": sorted(types)})
    return refs


def classify(value: str, idx: dict) -> tuple[str, str]:
    if value in idx["registry"]:
        return "mapped-registry", f"index:{idx['registry'][value]}"
    if value in set(idx["registry"].values()):   # workflow 가 locator 가 아니라 artifact id 로 참조
        return "mapped-registry", f"index:{value}"
    if EXTERNAL.match(value):
        return "external", ""
    v = value.strip("/").split("{")[0].rstrip("/")  # {content_id} 같은 템플릿 이전까지
    for m in sorted(idx["modules"], key=len, reverse=True):
        if v == m or v.startswith(m + "/"):
            return "mapped-module", m
    return "unmapped-path", ""


def guess_type(value: str) -> str:
    low = value.lower()
    if low.startswith(("firestore", "bigquery", "postgres", "mysql", "sqlite")):
        return "database"
    if low.startswith(("storage", "s3", "gcs", "gs://")):
        return "object_store"
    if low.startswith("mcp://"):
        return "mcp"
    if low.startswith(("http://", "https://")):
        return "api"
    return "external_url"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--index", default="agent-context/index/index.yaml")
    ap.add_argument("--workflow-dir", default="agent-context/workflow")
    ap.add_argument("--registry", default="agent-context/index/artifacts.abox.ttl", help="artifact 층 TTL registry(없으면 건너뜀)")
    ap.add_argument("--suggest", action="store_true")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    idx = load_index(root / a.index)
    idx["registry"].update(load_registry_file(root / a.registry))
    wdir = root / a.workflow_dir
    if not wdir.is_dir():
        print(f"workflow 디렉토리가 없습니다: {wdir}")
        return 2
    refs = references(wdir)
    counts: dict[str, int] = {}
    rows = []
    for r in refs:
        if r.get("kind") == "parse-error":
            status, where = "parse-error", ""
        else:
            status, where = classify(r["value"], idx)
        counts[status] = counts.get(status, 0) + 1
        rows.append({**r, "status": status, "where": where})
    print(f"index: {root / a.index} (module 경로 {len(idx['modules'])}개, data_registry {len(idx['registry'])}개)")
    print(f"workflow 참조 {len(rows)}건: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + "\n")
    if rows:
        print(f"{'상태':17}{'노드':16}{'속성':14}값")
        for r in rows:
            print(f"{r['status']:17}{r['node'][:15]:16}{r['prop']:14}{r['value']}" + (f"  -> {r['where']}" if r["where"] else ""))
    bad = [r for r in rows if r["status"] in ("external", "unmapped-path", "parse-error")]
    if a.suggest and bad:
        print("\n# data_registry 초안 (자동 수정하지 않음, 검토 후 index.yaml 에 직접 추가)")
        seen = set()
        for r in bad:
            if r["status"] != "external" or r["value"] in seen:
                continue
            seen.add(r["value"])
            slug = re.sub(r"[^a-z0-9]+", "-", r["value"].lower()).strip("-")[:40]
            print(f"  - id: {slug}\n    data_type: {guess_type(r['value'])}\n    locator: \"{r['value']}\"")
    if not rows:
        print("workflow 에 artifact/경로 참조가 없습니다.")
    return 1 if (a.strict and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
