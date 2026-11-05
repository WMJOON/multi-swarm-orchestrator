"""index 로더: index.abox.ttl(정본) 또는 index.yaml(전환기 폴백)을 같은 dict 모양으로 읽는다.

dict 모양(index.yaml 과 동일):
  project: {id, name, description, owner, updated, version, root_offset, status, remote, source_policy}
  modules: [{id, path, role?, description?, status?, data_type?, artifact_type?, subdirs?: [{path, description?}]}]
  root_files: [..], exclusions: [..]

사용:
  from index_ttl import load_index_any, find_index
  d = load_index_any(find_index(root))   # .ttl 이면 TTL, .yaml 이면 yaml
"""
from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_TTL = "agent-context/index/index.abox.ttl"
DEFAULT_YAML = "agent-context/index/index.yaml"


def find_index(root: str | Path) -> Path | None:
    """정본 TTL 을 먼저 찾고, 없으면 전환기 yaml 을 쓴다."""
    root = Path(root)
    for rel in (DEFAULT_TTL, DEFAULT_YAML):
        p = root / rel
        if p.is_file():
            return p
    return None


def load_index(path: str | Path) -> dict:
    """index.abox.ttl 을 index.yaml 과 같은 dict 모양으로 읽는다."""
    from rdflib import RDF, Graph, Namespace

    WF = Namespace("https://mso.dev/ontology/workflow#")
    g = Graph()
    g.parse(str(path), format="turtle")

    def val(node, prop):
        v = g.value(node, WF[prop])
        return None if v is None else str(v)

    dirs = list(g.subjects(RDF.type, WF.Directory))
    by_kind = {}
    for d in dirs:
        by_kind.setdefault(val(d, "dirKind"), []).append(d)
    roots = by_kind.get("root", [])
    if len(roots) != 1:
        raise ValueError(f"루트 디렉터리(dirKind root)가 정확히 하나여야 한다: {len(roots)}개")
    root = roots[0]

    project = {}
    for key, prop in (("id", "projectId"), ("name", "projectName"), ("description", "description"),
                      ("owner", "owner"), ("updated", "updated"), ("version", "version"),
                      ("root_offset", "rootOffset"), ("status", "status"), ("remote", "remote"),
                      ("source_policy", "sourcePolicy")):
        v = val(root, prop)
        if v is not None:
            project[key] = v

    modules = []
    for m in sorted(by_kind.get("module", []), key=lambda d: str(g.value(d, WF.path))):
        entry = {"id": val(m, "moduleId"), "path": val(m, "path")}
        for key, prop in (("role", "role"), ("description", "description"), ("status", "status"),
                          ("data_type", "dataType"), ("artifact_type", "artifactType")):
            v = val(m, prop)
            if v is not None:
                entry[key] = v
        subs = []
        for s in by_kind.get("subdir", []):
            if val(s, "moduleId") == entry["id"]:
                sub = {"path": val(s, "subdirPath")}
                if val(s, "description"):
                    sub["description"] = val(s, "description")
                subs.append(sub)
        if subs:
            entry["subdirs"] = sorted(subs, key=lambda x: x["path"])
        modules.append(entry)

    root_files = sorted(str(o) for o in g.objects(root, WF.rootFile))
    exclusions = sorted(str(o) for o in g.objects(root, WF.exclusion))
    out = {"project": project, "modules": modules}
    if root_files:
        out["root_files"] = root_files
    if exclusions:
        out["exclusions"] = exclusions
    return out


def load_index_any(path: str | Path) -> dict:
    """확장자로 고른다: .ttl → load_index, 그 밖 → yaml."""
    p = Path(path)
    if p.suffix == ".ttl":
        return load_index(p)
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
