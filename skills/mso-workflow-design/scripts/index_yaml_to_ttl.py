#!/usr/bin/env python3
"""index.yaml + artifacts.abox.ttl → index.abox.ttl (디렉터리 층, Phase B 확장).

- 레지스트리(개념·규약, 기본 index.abox.ttl)의 모든 트리플을 그대로 옮긴다. 같은 파일을 입력과 출력으로 써도 된다(멱등).
- 루트 디렉터리(path "./", dirKind root): 프로젝트 정보(project), root_files, exclusions.
- 최상위 모듈 디렉터리(dirKind module): moduleId, role, description, status, dataType, artifactType.
- 모듈의 subdirs 디렉터리(dirKind subdir): description, subdirPath, moduleId.
- 규약 directoryTemplate 의 리터럴 접두어 디렉터리(dirKind convention): 부모는 가장 긴 상위 경로.
- 아티팩트마다 wf:storedIn. 규약 여러 개가 서로 다른 디렉터리를 가리키면 실패한다.

사용: python3 index_yaml_to_ttl.py --root <루트> [--yaml agent-context/index/index.yaml]
        [--registry agent-context/index/index.abox.ttl] [--out agent-context/index/index.abox.ttl] [--check]
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

import yaml
from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef

WF = Namespace("https://mso.dev/ontology/workflow#")
DIR = Namespace("https://mso.dev/id/chatbot-1.5/directory/")
VAR = re.compile(r"\[[A-Za-z_][A-Za-z0-9_]*\]")
ROOT_PATH = "./"


def literal_dir(template: str) -> str:
    """directoryTemplate 의 첫 변수 앞부분(마지막 '/' 까지). 변수가 없으면 템플릿 전체(끝 '/')."""
    m = VAR.search(template)
    head = template if m is None else template[: m.start()]
    if m is None:
        return head if head.endswith("/") else head + "/"
    return head[: head.rfind("/") + 1] if "/" in head else ""


def dir_iri(path: str) -> URIRef:
    return DIR[hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]]


def _lit(v) -> Literal:
    return Literal(str(v), datatype=XSD.string)


def build(root: Path, yaml_path: Path, registry: Path, out: Path, check: bool) -> int:
    idx = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    g = Graph()
    g.parse(registry, format="turtle")
    g.bind("wf", WF)
    g.bind("dir", DIR)

    # path → 속성 dict. 모듈과 하위 폴더는 yaml 원본 속성을 그대로 싣는다.
    info: dict[str, dict] = {ROOT_PATH: {"dirKind": "root"}}
    modules = []
    for m in idx.get("modules") or []:
        base = m["path"].rstrip("/") + "/"
        modules.append((base, m["id"]))
        attrs = {"dirKind": "module", "moduleId": m["id"]}
        for key in ("role", "description", "status", "data_type", "artifact_type"):
            if m.get(key) is not None:
                attrs[{"data_type": "dataType", "artifact_type": "artifactType"}.get(key, key)] = m[key]
        info[base] = {**info.get(base, {}), **attrs}
        for sd in m.get("subdirs") or []:
            sub = base + sd["path"].rstrip("/") + "/"
            modules.append((sub, m["id"]))
            info[sub] = {"dirKind": "subdir", "moduleId": m["id"], "subdirPath": sd["path"],
                         **({"description": sd["description"]} if sd.get("description") else {})}

    def module_of(path):
        best = None
        for p, mid in modules:
            if path.startswith(p) and (best is None or len(p) > len(best[0])):
                best = (p, mid)
        return best[1] if best else None

    conv_dirs: dict[URIRef, set[str]] = {}
    for art in set(g.subjects(RDF.type, WF.RegisteredArtifact)):
        for conv in g.objects(art, WF.hasConvention):
            d = literal_dir(str(g.value(conv, WF.directoryTemplate) or ""))
            conv_dirs.setdefault(art, set()).add(d)
            if d and d not in info:
                info[d] = {"dirKind": "convention", "moduleId": module_of(d)}

    errors = []
    for art, ds in conv_dirs.items():
        ds = {d for d in ds if d}
        if len(ds) != 1:
            errors.append(f"{art.split('#')[-1]}: 규약 디렉터리가 {len(ds)}개 — 하나여야 한다 {sorted(ds)}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    paths = sorted(info, key=len)
    project = idx.get("project") or {}
    root_props = {"projectId": project.get("id"), "projectName": project.get("name"),
                  "owner": project.get("owner"), "updated": project.get("updated"),
                  "version": project.get("version"), "rootOffset": project.get("root_offset"),
                  "remote": project.get("remote"), "sourcePolicy": project.get("source_policy"),
                  "description": project.get("description"), "status": project.get("status")}
    for path in paths:
        node = dir_iri(path)
        g.add((node, RDF.type, WF.Directory))
        g.add((node, WF.path, _lit(path)))
        g.add((node, RDFS.label, _lit(path)))
        for k, v in info[path].items():
            if k == "dirKind" or v is None:
                g.add((node, WF.dirKind, _lit(v))) if k == "dirKind" else None
                continue
            g.add((node, WF[k], _lit(v)))
        if path == ROOT_PATH:
            for k, v in root_props.items():
                if v is not None:
                    g.add((node, WF[k], _lit(v)))
            for rf in idx.get("root_files") or []:
                g.add((node, WF.rootFile, _lit(rf)))
            for ex in idx.get("exclusions") or []:
                g.add((node, WF.exclusion, _lit(ex)))
            continue
        parents = [p for p in paths if p not in (path, ROOT_PATH) and path.startswith(p)]
        if parents:
            g.add((node, WF.parentDirectory, dir_iri(max(parents, key=len))))

    for art, ds in conv_dirs.items():
        ds = {d for d in ds if d}
        g.add((art, WF.storedIn, dir_iri(next(iter(ds)))))

    if check:
        print(f"디렉터리 {len(paths)}개(루트 포함), storedIn {len(conv_dirs)}개 (검사만)")
        return 0
    header = ("# 생성 파일(index_yaml_to_ttl.py). 직접 고치지 말 것.\n"
              f"# 원천: {yaml_path.name} + {registry.name}. 디렉터리 층(루트·모듈·하위 폴더·규약 폴더)과 wf:storedIn.\n")
    out.write_text(header + g.serialize(format="turtle"), encoding="utf-8")
    print(f"작성: {out} (디렉터리 {len(paths)}개, storedIn {len(conv_dirs)}개)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--yaml", default="agent-context/index/index.yaml")
    ap.add_argument("--registry", default="agent-context/index/index.abox.ttl")
    ap.add_argument("--out", default="agent-context/index/index.abox.ttl")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    return build(root, root / a.yaml, root / a.registry, root / a.out, a.check)


if __name__ == "__main__":
    sys.exit(main())
