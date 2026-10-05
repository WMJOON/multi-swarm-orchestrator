"""validate_artifact_layer.py: 개념(안정 IRI) + 규약 버전(유효 구간) 구조의 SHACL/SPARQL 검증, 규약 불변, 파일 스캔."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_artifact_layer.py"
HEAD = ('@prefix wf: <https://mso.dev/ontology/workflow#> .\n@prefix art: <https://mso.dev/id/p/artifact/> .\n'
        '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n')
INDEX = 'project: {name: p, id: p, description: d, owner: o, updated: "2026-10-05"}\nmodules:\n- id: alpha\n  path: alpha/\n  description: a\n  status: active\n'
PARAMS = '[ wf:paramName "date" ; wf:paramType wf:DateYmd ], [ wf:paramName "title" ; wf:paramType wf:Slug ]'


def concept(iri="a", convs=("a_c1",), consumer="Hybrid", typ="Document", module="alpha", comment='rdfs:comment "d"@ko ;', extra="") -> str:
    c = f"wf:consumerType wf:{consumer} ;" if consumer else ""
    t = f"wf:hasArtifactType wf:{typ} ;" if typ else ""
    hc = ("wf:hasConvention " + ", ".join(f"art:{x}" for x in convs) + " .") if convs else "."
    return f'art:{iri} a wf:Artifact, wf:RegisteredArtifact ; {comment} {t} {c} wf:inModule "{module}" ; {extra}\n  {hc}\n'


def conv(cid="a_c1", dirt="alpha/docs/[date]/", name="[date]-note-[title]", fmt="md", params=PARAMS, extra="") -> str:
    return (f'art:{cid} a wf:ArtifactConvention ; wf:directoryTemplate "{dirt}" ; wf:namingConvention "{name}" ; wf:fileFormat "{fmt}" ;\n'
            f'  {extra} wf:hasParam {params} .\n')


def reg(**kw) -> str:
    return concept(**kw.pop("c", {})) + conv(**kw)


def project(tmp: Path, registry: str, workflow: str | None = None) -> Path:
    (tmp / "agent-context/index").mkdir(parents=True); (tmp / "alpha/docs").mkdir(parents=True)
    (tmp / "agent-context/index/index.yaml").write_text(INDEX, encoding="utf-8")
    (tmp / "agent-context/index/artifacts.abox.ttl").write_text(HEAD + registry, encoding="utf-8")
    if workflow is not None:
        (tmp / "agent-context/workflow").mkdir(parents=True)
        (tmp / "agent-context/workflow/w.abox.ttl").write_text(HEAD + workflow, encoding="utf-8")
    return tmp


def run(root: Path, *a: str):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *a], text=True, capture_output=True)


def flow(producer=True, consumer=True, consumer_subject="model", target="art:a"):
    w = '<#P> a wf:Node, wf:Execution, wf:Task ; wf:hasSubject "model" .\n'
    w += f'<#C> a wf:Node, wf:Execution, wf:Task ; wf:hasSubject "{consumer_subject}" .\n'
    if producer:
        w += f'<#s1> a wf:Edge, wf:Stream ; wf:from <#P> ; wf:to {target} ; wf:streamType "produces_to" .\n'
    if consumer:
        w += f'<#s2> a wf:Edge, wf:Stream ; wf:from {target} ; wf:to <#C> ; wf:streamType "consumed_by" .\n'
    return w


def sub(tmp: Path, name: str) -> Path:
    (tmp / name).mkdir()
    return tmp / name


def test_valid_concept_with_convention_and_flow_is_clean(tmp_path):
    r = run(project(tmp_path, reg(), flow()))
    assert r.returncode == 0 and "Violation 0건, Warning 0건" in r.stdout, r.stdout
    assert "개념 1개, 규약 버전 1개" in r.stdout


def test_concept_requires_identity_and_a_convention(tmp_path):
    for i, (bad, key) in enumerate([(concept(consumer=None) + conv(), "consumerType"), (concept(typ=None) + conv(), "ArtifactType"),
                                    (concept(comment="") + conv(), "description"), (concept(convs=()) + conv(), "규약 버전")]):
        r = run(project(sub(tmp_path, f"c{i}"), bad, flow()))
        assert r.returncode == 1 and key in r.stdout, (key, r.stdout)


def test_convention_has_exactly_three_elements_and_declared_params(tmp_path):
    assert "선언되지 않음" in run(project(sub(tmp_path, "p"), concept() + conv(params='[ wf:paramName "date" ; wf:paramType wf:DateYmd ]'), flow())).stdout
    both = '[ wf:paramName "date" ; wf:paramType wf:DateYmd ; wf:paramRegex "x" ], [ wf:paramName "title" ; wf:paramType wf:Slug ]'
    assert "정확히 하나" in run(project(sub(tmp_path, "b"), concept() + conv(params=both), flow())).stdout


def test_same_triple_in_different_concepts_is_violation(tmp_path):
    two = concept("a", ("a_c1",)) + conv("a_c1") + concept("b", ("b_c1",)) + conv("b_c1")
    r = run(project(tmp_path, two, flow()))
    assert r.returncode == 1 and "서로 다른 개념에 있음" in r.stdout
    other = concept("a", ("a_c1",)) + conv("a_c1") + concept("b", ("b_c1",)) + conv("b_c1", fmt="txt")
    assert "서로 다른 개념에 있음" not in run(project(sub(tmp_path, "ok"), other, flow())).stdout


def test_convention_belongs_to_exactly_one_concept(tmp_path):
    orphan = concept() + conv() + conv("lonely", dirt="alpha/other/[date]/")
    assert "어느 개념" in run(project(tmp_path, orphan, flow())).stdout
    shared = concept("a", ("a_c1",)) + concept("b", ("a_c1",)) + conv("a_c1")
    assert "둘 이상의 개념" in run(project(sub(tmp_path, "s"), shared, flow("a"))).stdout


def versioned(c1_extra='wf:validUntil "2026-06-01"^^xsd:date ; wf:supersededBy art:a_c2 ; wf:changeKind "metadataChange" ;',
              c2_extra='wf:validFrom "2026-06-01"^^xsd:date ;', c2_dir="alpha/docs/[date]/") -> str:
    return concept(convs=("a_c1", "a_c2")) + conv("a_c1", extra=c1_extra) + conv("a_c2", dirt=c2_dir, extra=c2_extra)


def test_successive_versions_are_clean(tmp_path):
    r = run(project(tmp_path, versioned(), flow()))
    assert r.returncode == 0 and "Violation 0건, Warning 0건" in r.stdout, r.stdout


def test_overlapping_windows_are_violation(tmp_path):
    r = run(project(tmp_path, versioned(c2_extra='wf:validFrom "2026-05-01"^^xsd:date ;'), flow()))
    assert r.returncode == 1 and "유효 구간이 겹침" in r.stdout
    two_current = concept(convs=("a_c1", "a_c2")) + conv("a_c1") + conv("a_c2", dirt="alpha/docs/v2/[date]/")
    assert "유효 구간이 겹침" in run(project(sub(tmp_path, "t"), two_current, flow())).stdout


def test_closed_without_successor_and_no_current_warn(tmp_path):
    only_old = concept() + conv(extra='wf:validUntil "2026-06-01"^^xsd:date ;')
    out = run(project(tmp_path, only_old, flow())).stdout
    assert "supersededBy(후속 규약)가 없음" in out and "현행(validUntil 없는) 규약이 하나도 없음" in out


def test_superseded_must_be_same_concept(tmp_path):
    bad = (concept("a", ("a_c1",)) + conv("a_c1", extra='wf:validUntil "2026-06-01"^^xsd:date ; wf:supersededBy art:b_c1 ;') +
           concept("b", ("b_c1",)) + conv("b_c1", fmt="txt"))
    assert "같은 개념의 규약이 아님" in run(project(tmp_path, bad, flow())).stdout


def test_window_without_date_param_warns(tmp_path):
    only_title = '[ wf:paramName "title" ; wf:paramType wf:Slug ], [ wf:paramName "date" ; wf:paramType wf:DateYmd ]'
    r = run(project(tmp_path, concept() + conv(extra='wf:validFrom "2026-06-01"^^xsd:date ;', params=only_title.replace('"date"', '"day"').replace("[date]", "[day]"),
                                              dirt="alpha/docs/[day]/", name="[day]-note-[title]"), flow()))
    assert "date 또는 month 변수" in r.stdout


def test_format_outside_type_is_warning_only(tmp_path):
    r = run(project(tmp_path, concept() + conv(fmt="pdf"), flow()))
    assert r.returncode == 0 and "allowedFormat" in r.stdout
    assert run(tmp_path, "--strict").returncode == 1


def test_cross_layer_module_and_prefix(tmp_path):
    assert "교차 층" in run(project(tmp_path, concept(module="ghost") + conv(), flow())).stdout
    assert "아래에 없습니다" in run(project(sub(tmp_path, "y"), concept() + conv(dirt="elsewhere/[date]/"), flow())).stdout


def test_producer_consumer_derived_from_streams(tmp_path):
    assert "producerExecution min 1" in run(project(tmp_path, reg(), flow(producer=False))).stdout
    ext = concept(extra="wf:externalSource true ;") + conv()
    assert "producerExecution min 1" not in run(project(sub(tmp_path, "e"), ext, flow(producer=False))).stdout
    assert "consumerExecution min 1" in run(project(sub(tmp_path, "c"), reg(), flow(consumer=False))).stdout


def test_consumer_type_cross_checks_subject(tmp_path):
    assert "전부 hasSubject human" in run(project(tmp_path, concept(consumer="Machine") + conv(), flow(consumer_subject="human"))).stdout
    assert "human 인 소비 Execution 이 없음" in run(project(sub(tmp_path, "h"), concept(consumer="Human") + conv(), flow(consumer_subject="model"))).stdout


def test_stream_to_unregistered_and_unused_artifact_warn(tmp_path):
    wf = ('<#E> a wf:Node, wf:Execution, wf:Task .\n<#X> a wf:Node, wf:Artifact ; wf:locator "somewhere" .\n'
          '<#s1> a wf:Edge, wf:Stream ; wf:from <#E> ; wf:to <#X> ; wf:streamType "produces_to" .\n')
    out = run(project(tmp_path, reg(), wf)).stdout
    assert "registry 에 없는 artifact" in out and "쓰지 않음" in out


def git(root: Path, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_committed_convention_is_immutable(tmp_path):
    root = project(tmp_path, reg(), flow())
    git(root, "init", "-q"); git(root, "config", "user.email", "t@x.invalid"); git(root, "config", "user.name", "T")
    git(root, "add", "-A"); git(root, "commit", "-qm", "init")
    assert run(root).returncode == 0
    regfile = root / "agent-context/index/artifacts.abox.ttl"
    regfile.write_text(regfile.read_text(encoding="utf-8").replace("[date]-note-[title]", "[date]_note_[title]"), encoding="utf-8")
    r = run(root)
    assert r.returncode == 1 and "namingConvention 이 바뀜" in r.stdout and "새 규약 + supersededBy" in r.stdout
    assert run(root, "--no-history-check").returncode == 0
    regfile.write_text(HEAD + concept() + "\n", encoding="utf-8")                          # 규약 삭제
    assert "삭제됨" in run(root).stdout


def test_closing_a_convention_with_successor_is_allowed_after_commit(tmp_path):
    root = project(tmp_path, reg(), flow())
    git(root, "init", "-q"); git(root, "config", "user.email", "t@x.invalid"); git(root, "config", "user.name", "T")
    git(root, "add", "-A"); git(root, "commit", "-qm", "init")
    (root / "agent-context/index/artifacts.abox.ttl").write_text(HEAD + versioned(c2_dir="alpha/docs2/[date]/"), encoding="utf-8")
    (root / "alpha/docs2").mkdir()
    r = run(root)
    assert r.returncode == 0 and "Violation 0건" in r.stdout, r.stdout


def test_template_compiles_with_backreference_and_param_regex():
    spec = importlib.util.spec_from_file_location("val", SCRIPT)
    mod = importlib.util.module_from_spec(spec); sys.modules["val"] = mod; spec.loader.exec_module(mod)
    rx = mod.compile_template("p/blog/[date]/", "[date]-post-[title]", "md", {"date": r"\d{4}-\d{2}-\d{2}", "title": r"[^/\s]+"})
    assert rx.match("p/blog/2026-10-05/2026-10-05-post-hello.md")
    assert not rx.match("p/blog/2026-10-05/2026-10-06-post-hello.md")
    assert mod.literal_prefix("[project]/x/") == "" and mod.literal_prefix("a/b/[d]/c/") == "a/b/"
    c = {"valid_from": "2026-06-01", "valid_until": None}
    assert mod.valid_at(c, "2026-06-01") and not mod.valid_at(c, "2026-05-31") and mod.valid_at(c, None)
    c2 = {"valid_from": None, "valid_until": "2026-06-01"}
    assert mod.valid_at(c2, "2026-05-31") and not mod.valid_at(c2, "2026-06-01")


def test_scan_picks_convention_by_item_date_and_reports_migration_gap(tmp_path):
    meta = '[ a wf:MetadataField ; wf:fieldName "title" ; wf:fieldType "string" ; wf:fieldRequired true ]'
    old = conv("a_c1", extra='wf:validUntil "2026-06-01"^^xsd:date ; wf:supersededBy art:a_c2 ;')
    new = conv("a_c2", extra=f'wf:validFrom "2026-06-01"^^xsd:date ; wf:hasMetadata {meta} ;')
    root = project(tmp_path, concept(convs=("a_c1", "a_c2")) + old + new, flow())
    def put(day, name, body):
        d = root / "alpha/docs" / day; d.mkdir(parents=True, exist_ok=True); (d / name).write_text(body, encoding="utf-8")
    put("2026-07-01", "2026-07-01-note-new.md", "---\ntitle: x\n---\n")        # 현행, 메타 OK
    put("2026-07-02", "2026-07-02-note-nometa.md", "plain")                      # 현행, 메타 누락
    put("2026-04-01", "2026-04-01-note-old.md", "plain")                         # 옛 규약(메타 요구 없음), 현행 대비 갭
    put("2026-04-02", "stray.txt", "x")                                          # 레거시 미분류
    put("2026-08-01", "stray.txt", "x")                                          # 현행 미분류
    (root / "alpha/docs/undated.txt").write_text("x", encoding="utf-8")          # 날짜 불명
    out = run(root, "--scan").stdout
    assert "분류됨 3" in out and "레거시 1" in out and "날짜 불명 1" in out and "현행 미분류 1" in out
    assert "적용 규약 기준 누락 1/2" in out and "현행 규약 대비 갭 1/1" in out
    run(root, "--scan", "--json", str(tmp_path / "s.json"))
    res = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert res["roots"][0]["matched"] == 3 and res["roots"][0]["legacy_before"] == "2026-06-01"
    assert res["artifacts"]["a"]["conventions"] == ["a_c1", "a_c2"]


def test_scan_counts_stale_when_only_an_ended_convention_matches(tmp_path):
    old = conv("a_c1", dirt="alpha/legacy/[date]/", extra='wf:validUntil "2026-06-01"^^xsd:date ; wf:supersededBy art:a_c2 ;')
    new = conv("a_c2", extra='wf:validFrom "2026-06-01"^^xsd:date ;')
    root = project(tmp_path, concept(convs=("a_c1", "a_c2")) + old + new, flow())
    (root / "alpha/legacy/2026-07-01").mkdir(parents=True)
    (root / "alpha/legacy/2026-07-01/2026-07-01-note-late.md").write_text("x", encoding="utf-8")   # 끝난 규약 경로를 구간 밖에 사용
    out = run(root, "--scan").stdout
    assert "기간 밖 1" in out


def test_artifact_lineage_query_follows_executions():
    from rdflib import Graph
    qfile = Path(__file__).resolve().parents[1] / "references" / "queries" / "artifact-lineage.rq"
    g = Graph()
    g.parse(data=HEAD + concept("main", ("main_c1",)) + conv("main_c1") + concept("mainV", ("mainV_c1",)) + conv("mainV_c1", fmt="txt") + (
        '<#R> a wf:Node, wf:Execution, wf:Task ; rdfs:label "Refine" .\n'
        '<#s1> a wf:Edge, wf:Stream ; wf:from art:main ; wf:to <#R> ; wf:streamType "consumed_by" .\n'
        '<#s2> a wf:Edge, wf:Stream ; wf:from <#R> ; wf:to art:mainV ; wf:streamType "produces_to" .\n'), format="turtle")
    rows = [(str(r.source).rsplit("/", 1)[-1], str(r.execution), str(r.produced).rsplit("/", 1)[-1]) for r in g.query(qfile.read_text(encoding="utf-8"))]
    assert rows == [("main", "Refine", "mainV")]
