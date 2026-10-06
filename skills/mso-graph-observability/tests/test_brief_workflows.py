import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import brief_workflows as bw  # noqa: E402

HEAD = """\
@prefix wf: <https://mso.dev/ontology/workflow#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix art: <https://example.org/art#> .
"""


def flow_a():
    return HEAD + """
@prefix a: <https://example.org/a#> .
a:workflow a wf:Workflow ; wf:label "수집" ; wf:description "원문을 모아 정리한다. 두 번째 문장." ; wf:workflowType "base" ;
    wf:has a:start, a:end, a:collect, a:review, a:approve .
a:start a wf:Node, wf:Start .
a:end a wf:Node, wf:End .
a:collect a wf:Node, wf:Execution, wf:Task ; wf:label "수집하기" ; wf:inWorkflow a:workflow ; wf:hasSubject "system" ; wf:instruction "원문을 받는다" ; wf:method "script" .
a:review a wf:Node, wf:Execution, wf:Task ; wf:label "검토하기" ; wf:inWorkflow a:workflow ; wf:hasSubject "model" .
a:approve a wf:Node, wf:Execution, wf:Decision ; wf:label "승인" ; wf:inWorkflow a:workflow ; wf:hasSubject "human" .
a:r0 a wf:Edge, wf:Rail ; wf:railType "default" ; wf:from a:start ; wf:to a:collect .
a:r1 a wf:Edge, wf:Rail ; wf:railType "default" ; wf:from a:collect ; wf:to a:review .
a:r2 a wf:Edge, wf:Rail ; wf:railType "default" ; wf:from a:review ; wf:to a:approve .
a:r3 a wf:Edge, wf:Rail ; wf:railType "default" ; wf:from a:approve ; wf:to a:end ; wf:on "approved" .
a:r4 a wf:Edge, wf:Rail ; wf:railType "default" ; wf:from a:approve ; wf:to a:review ; wf:on "rejected" .
a:s1 a wf:Edge, wf:Stream ; wf:streamType "consumed_by" ; wf:from art:source ; wf:to a:collect .
a:s2 a wf:Edge, wf:Stream ; wf:streamType "produces_to" ; wf:from a:collect ; wf:to art:docs .
a:s3 a wf:Edge, wf:Stream ; wf:streamType "produces_to" ; wf:from a:review ; wf:to art:notes .
"""


def flow_b():
    return HEAD + """
@prefix b: <https://example.org/b#> .
b:workflow a wf:Workflow ; wf:label "정리" ; wf:workflowType "base" ; wf:has b:start, b:end, b:tidy .
b:start a wf:Node, wf:Start .
b:end a wf:Node, wf:End .
b:tidy a wf:Node, wf:Execution, wf:Task ; wf:label "정리하기" ; wf:inWorkflow b:workflow ; wf:hasSubject "system" ; wf:instruction "정리한다" .
b:r0 a wf:Edge, wf:Rail ; wf:railType "default" ; wf:from b:start ; wf:to b:tidy .
b:r1 a wf:Edge, wf:Rail ; wf:railType "default" ; wf:from b:tidy ; wf:to b:end .
b:s1 a wf:Edge, wf:Stream ; wf:streamType "consumed_by" ; wf:from art:docs ; wf:to b:tidy .
"""


def project(tmp_path: Path) -> Path:
    wf = tmp_path / "agent-context" / "workflow"
    wf.mkdir(parents=True)
    (wf / "workflow-a.abox.ttl").write_text(flow_a(), encoding="utf-8")
    (wf / "workflow-b.abox.ttl").write_text(flow_b(), encoding="utf-8")
    return tmp_path


def test_brief_extracts_flow_gates_loops_and_artifacts(tmp_path):
    root = project(tmp_path)
    result = bw.run(root, today="2026-10-07")
    brief = json.loads((Path(result["out"]) / "workflow-a.brief.json").read_text(encoding="utf-8"))
    assert [n["label"] for n in brief["flow"]][:3] == ["수집하기", "검토하기", "승인"]
    assert brief["counts"]["steps"] == 3 and "사람 승인 1곳" in brief["summary"] and "되돌림 1개" in brief["summary"]
    gate = brief["human_gates"][0]
    assert gate["label"] == "승인" and {o["on"] for o in gate["outcomes"]} == {"approved", "rejected"}
    assert brief["loops"] == [{"from": "승인", "to": "검토하기", "on": "rejected"}]
    art = brief["artifacts"]
    assert art["inputs"] == ["source"] and set(art["outputs"]) == {"docs", "notes"}
    assert art["external_inputs"] == ["source"]  # 어떤 workflow 도 만들지 않는 입력
    assert art["unconsumed_outputs"] == ["notes"]  # 아무도 쓰지 않는 산출
    assert art["to_other_workflows"] == [{"artifact": "docs", "to": ["workflow-b"]}]
    other = json.loads((Path(result["out"]) / "workflow-b.brief.json").read_text(encoding="utf-8"))
    assert other["artifacts"]["from_other_workflows"] == [{"artifact": "docs", "from": ["workflow-a"]}]


def test_human_report_is_plain_korean_and_flags_blind_human_gate(tmp_path):
    root = project(tmp_path)
    report = (Path(bw.run(root, today="2026-10-07")["out"]) / "report.md").read_text(encoding="utf-8")
    assert report.startswith(f"# {root.name} workflow 현황 (2026-10-07)")
    assert "## 사람이 결정해야 하는 곳" in report and "**수집 · 승인**" in report
    assert "판단 기준이 적혀 있지 않습니다" in report  # 사람 승인 지점에 기준이 없는 것을 짚는다
    assert "**수집** 이(가) 만든 *docs* 을(를) 정리 이(가) 이어서 씁니다." in report
    assert "원문을 모아 정리한다" in report and "두 번째 문장" not in report.split("## 각 workflow")[0]  # 표에는 첫 문장만


def test_shared_store_is_separated_from_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr(bw, "SHARED_MIN", 2)
    root = project(tmp_path)
    out = Path(bw.run(root, today="2026-10-07")["out"])
    agent = json.loads((out / "workflow-a.brief.json").read_text(encoding="utf-8"))
    assert agent["artifacts"]["to_other_workflows"] == [] and agent["artifacts"]["shared_stores"] == ["docs"]
    assert "## 여러 workflow가 함께 쓰는 자료" in (out / "report.md").read_text(encoding="utf-8")


def test_read_only_and_deterministic(tmp_path):
    root = project(tmp_path)
    ttls = sorted((root / "agent-context" / "workflow").glob("*.ttl"))
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in ttls]
    first = Path(bw.run(root, out=tmp_path / "o1", today="2026-10-07")["out"])
    second = Path(bw.run(root, out=tmp_path / "o2", today="2026-10-07")["out"])
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in ttls] == before
    for name in ("workflow-a.brief.json", "project-brief.md", "report.md"):
        assert (first / name).read_text(encoding="utf-8") == (second / name).read_text(encoding="utf-8")


def test_no_workflow_files_returns_failure(tmp_path):
    assert bw.main(["--root", str(tmp_path)]) == 1
