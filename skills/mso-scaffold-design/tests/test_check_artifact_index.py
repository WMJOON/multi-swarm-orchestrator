"""check_artifact_index.py: workflow artifact 참조 대 index 매핑 점검."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_artifact_index.py"

TTL = '''@prefix wf: <https://mso.dev/ontology/workflow#> .
<#A> a wf:Node, wf:Artifact ; wf:locator "Firestore:queue" .
<#B> a wf:Node, wf:Artifact ; wf:locator "reg-target/data.csv" .
<#C> a wf:Node, wf:Artifact ; wf:locator "content/draft/{id}.md" .
<#D> a wf:Node, wf:Artifact ; wf:locator "nowhere/file.md" .
<#E> a wf:Node, wf:Execution ; wf:dirPath "content/" .
'''
INDEX = '''project: {name: p, id: p, description: d, owner: o, updated: "2026-10-05"}
modules:
- id: content
  path: content/
  description: c
  status: active
data_registry:
- id: queue-db
  data_type: database
  locator: "Firestore:queue"
- id: reg-file
  data_type: local_file
  locator: "reg-target/data.csv"
'''


def project(tmp: Path, ttl: str = TTL) -> Path:
    (tmp / "agent-context/index").mkdir(parents=True); (tmp / "agent-context/workflow").mkdir(parents=True)
    (tmp / "agent-context/index/index.yaml").write_text(INDEX, encoding="utf-8")
    (tmp / "agent-context/workflow/w.abox.ttl").write_text(ttl, encoding="utf-8")
    return tmp


def run(root: Path, *a: str):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *a], text=True, capture_output=True)


def test_classifies_each_reference(tmp_path):
    out = run(project(tmp_path)).stdout
    assert "mapped-registry" in out and "index:queue-db" in out and "index:reg-file" in out
    rows = [l for l in out.splitlines() if l.startswith("mapped-module")]
    assert len(rows) == 2                            # content/draft/{id}.md, dirPath content/
    assert "unmapped-path" in out and "nowhere/file.md" in out


def test_strict_exit_code_and_suggest(tmp_path):
    root = project(tmp_path)
    assert run(root).returncode == 0
    assert run(root, "--strict").returncode == 1


def test_all_mapped_passes_strict(tmp_path):
    ttl = '@prefix wf: <https://mso.dev/ontology/workflow#> .\n<#A> a wf:Artifact ; wf:locator "Firestore:queue" .\n'
    assert run(project(tmp_path, ttl), "--strict").returncode == 0


def test_suggest_emits_registry_stub_for_external_only(tmp_path):
    ttl = '@prefix wf: <https://mso.dev/ontology/workflow#> .\n<#A> a wf:Artifact ; wf:locator "Storage:drafts/{id}.md" .\n'
    out = run(project(tmp_path, ttl), "--suggest").stdout
    assert "data_type: object_store" in out and 'locator: "Storage:drafts/{id}.md"' in out


def test_ttl_registry_maps_by_directory_prefix_and_id(tmp_path):
    root = project(tmp_path, ('@prefix wf: <https://mso.dev/ontology/workflow#> .\n'
                              '<#A> a wf:Artifact ; wf:locator "alpha/data/" .\n<#B> a wf:Artifact ; wf:locator "a-data" .\n'))
    (root / "agent-context/index/artifacts.abox.ttl").write_text(
        '@prefix wf: <https://mso.dev/ontology/workflow#> .\n@prefix art: <https://mso.dev/id/p/artifact/> .\n'
        'art:a-data a wf:Artifact, wf:RegisteredArtifact ; wf:hasConvention art:a-data_c1 .\n'
        'art:a-data_c1 a wf:ArtifactConvention ; wf:directoryTemplate "alpha/data/[date]/" .\n', encoding="utf-8")
    out = run(root).stdout
    assert len([l for l in out.splitlines() if l.startswith("mapped-registry")]) == 2
