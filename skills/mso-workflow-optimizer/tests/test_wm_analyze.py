import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_work_memory as awm  # noqa: E402
import wm_analyze as wa  # noqa: E402

NOW = dt.datetime(2026, 10, 7, tzinfo=dt.timezone.utc)
NOW_ISO = NOW.isoformat()
OLD = "2026-07-01T00:00:00Z"


def entry(id_, type_, title="t", text="", tags=None, meta=None, rel=None, created="2026-09-01T00:00:00Z"):
    return {"id": id_, "type": type_, "title": title, "text": text, "tags": tags or [], "created_at": created,
            "author": "agent", "metadata": meta or {}, "relations": rel or []}


def write(root: Path, rows: list[dict]) -> Path:
    wm = root / "agent-context" / "work-memory"
    dirs = {"issue-note": "track-record", "agent-decision": "track-record", "user-decision": "track-record",
            "trouble-shooting": "track-record", "release-note": "release-record",
            "episode": "insight-record", "pattern": "insight-record", "principle": "insight-record"}
    files: dict[Path, list[str]] = {}
    for row in rows:
        files.setdefault(wm / dirs[row["type"]] / f"{row['type']}.jsonl", []).append(json.dumps(row, ensure_ascii=False))
    for path, lines in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return wm


def ids(proposals):
    return {p["id"] for p in proposals}


def test_load_skips_broken_lines_and_reports_them(tmp_path):
    wm = write(tmp_path, [entry("IN-0001", "issue-note")])
    with (wm / "track-record" / "issue-note.jsonl").open("a") as f:
        f.write("{not json}\n")
    loaded = wa.load_entries(wm)
    assert [e["id"] for e in loaded["entries"]] == ["IN-0001"] and loaded["broken_lines"] == ["issue-note.jsonl:2"]


def test_quality_flags_integrity_and_missing_fields(tmp_path):
    rows = [
        entry("IN-0001", "issue-note", meta={"status": "open", "severity": "major", "module": "m"}, rel=[{"type": "resolved-by", "target": "TS-0001"}]),
        entry("IN-0002", "issue-note", meta={"status": "resolved", "severity": "low"}),
        entry("IN-0003", "issue-note", meta={}),
        entry("TS-0001", "trouble-shooting", meta={}, rel=[{"type": "resolved-by", "target": "IN-9999"}]),
        entry("AD-0001", "agent-decision", meta={"rationale": "x"}),
        entry("AD-0001", "agent-decision", meta={"rationale": "x"}),
        entry("IN-0004", "issue-note", tags=["korean_tax", "Korean-Tax"], meta={"status": "open", "severity": "low"}),
    ]
    found = ids(wa.analyze_quality(wa.load_entries(write(tmp_path, rows))["entries"], now=NOW))
    assert {"quality:duplicate-ids", "quality:dangling-relations", "quality:issue-missing-fields", "quality:vocab-drift",
            "quality:resolved-without-ts", "quality:open-but-resolved", "quality:ts-missing-fields", "quality:ad-missing-fields",
            "quality:tag-drift"} <= found


def test_promotion_suggests_ep_for_uncovered_cluster_but_not_for_covered_ones(tmp_path):
    same = "등록 순서를 지키지 않아 라벨 스크립트가 신규 개체를 읽지 못했다 abox compile 이후 inject 실행 순서 오류"
    rows = [entry(f"TS-000{i}", "trouble-shooting", title=same, meta={"root_cause": same}) for i in range(1, 5)]
    rows.append(entry("TS-0009", "trouble-shooting", title="전혀 다른 주제 환율 계산 반올림", meta={"root_cause": "반올림 규칙"}))
    entries = wa.load_entries(write(tmp_path, rows))["entries"]
    found = wa.analyze_promotion(entries, now=NOW)
    ep = [p for p in found if p["id"].startswith("promotion:EP")]
    assert len(ep) == 1 and set(ep[0]["evidence"]) == {"TS-0001", "TS-0002", "TS-0003", "TS-0004"}
    covered = entries + [entry("EP-0001", "episode", rel=[{"type": "references", "target": f"TS-000{i}"} for i in range(1, 5)])]
    assert not [p for p in wa.analyze_promotion(covered, now=NOW) if p["id"].startswith("promotion:EP")]


def test_promotion_suggests_pr_for_stable_pattern_and_pt_for_similar_episodes(tmp_path):
    ep_text = "게이트 없이 수동으로 등록해 누락이 반복됐다 검증 순서 자동화 필요"
    rows = [entry("PT-0001", "pattern", meta={"instances": ["EP-0001", "EP-0002", "EP-0003"]}),
            entry("EP-0001", "episode"), entry("EP-0002", "episode"), entry("EP-0003", "episode"),
            entry("EP-0010", "episode", title=ep_text, meta={"what_happened": ep_text}),
            entry("EP-0011", "episode", title=ep_text, meta={"what_happened": ep_text})]
    found = ids(wa.analyze_promotion(wa.load_entries(write(tmp_path, rows))["entries"], now=NOW))
    assert "promotion:PR:PT-0001" in found and any(i.startswith("promotion:PT:EP-0010") for i in found)


def test_workflow_flags_recurring_root_cause_and_module_hotspot(tmp_path):
    cause = "SHACL VALUES 금지 제약을 몰라 검증이 실패했다 pySHACL conforms False 원인 확인 누락"
    rows = [entry("TS-0001", "trouble-shooting", meta={"root_cause": cause, "module": "shacl"}),
            entry("TS-0002", "trouble-shooting", meta={"root_cause": cause + " 재발", "module": "shacl"})]
    rows += [entry(f"IN-000{i}", "issue-note", title=f"서로 다른 문제 {i} 항목{i}", meta={"status": "open", "severity": "high", "module": "korean_tax"}) for i in range(1, 4)]
    rows += [entry(f"IN-001{i}", "issue-note", title=f"또 다른 이슈 {i} 건{i}", meta={"status": "open", "severity": "low", "module": "korean-tax"}) for i in range(1, 3)]
    found = ids(wa.analyze_workflow(wa.load_entries(write(tmp_path, rows))["entries"], now=NOW))
    assert "workflow:cause:TS-0001" in found
    assert "workflow:hotspot:korean-tax" in found  # korean_tax 와 korean-tax 를 하나로 센다


def test_stale_flags_missing_paths_only_inside_existing_top_dirs(tmp_path):
    (tmp_path / "ontology").mkdir()
    (tmp_path / "ontology" / "alive.ttl").write_text("x")
    rows = [entry("UD-0001", "user-decision", text="정본은 ontology/gone.ttl 이다"),
            entry("UD-0002", "user-decision", text="ontology/alive.ttl 이 정본"),
            entry("UD-0003", "user-decision", text="모델 qwen/qwen3-1.7b 와 other/place/x.py 는 외부")]
    found = wa.analyze_stale(wa.load_entries(write(tmp_path, rows))["entries"], now=NOW, project_root=tmp_path)
    paths = next(p for p in found if p["id"] == "stale:missing-paths")
    assert paths["evidence"] == ["UD-0001"]


def test_stale_unverified_after_latest_release_and_low_confidence(tmp_path):
    rows = [entry("UD-0001", "user-decision", meta={"scope": "structural"}, created="2026-08-01T00:00:00Z"),
            entry("UD-0002", "user-decision", meta={"scope": "structural"}, created="2026-08-01T00:00:00Z", rel=[{"type": "verified-in", "target": "RN-0001"}]),
            entry("RN-0001", "release-note", created="2026-09-01T00:00:00Z"),
            entry("AD-0001", "agent-decision", meta={"confidence": 0.4}, created=OLD)]
    found = wa.analyze_stale(wa.load_entries(write(tmp_path, rows))["entries"], now=NOW, project_root=None)
    unver = next(p for p in found if p["id"].startswith("stale:unverified-after"))
    assert "UD-0001" in unver["evidence"] and "UD-0002" not in unver["evidence"]
    assert "stale:low-confidence-ad" in ids(found)


def _rows_for_graph():
    same = "순서 오류로 신규 개체 라벨이 주입되지 않았다 abox compile inject 실행 순서"
    return [entry(f"TS-000{i}", "trouble-shooting", title=same, meta={"root_cause": same, "fix_summary": "f"}, rel=[{"type": "resolved-by", "target": "IN-9"}]) for i in range(1, 4)]


def test_run_writes_report_without_touching_work_memory_and_is_deterministic(tmp_path):
    wm = write(tmp_path, _rows_for_graph())
    snapshot = lambda: {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(wm.rglob("*.jsonl"))}
    before = snapshot()
    a = awm.run(wm, tmp_path / "out-a", now=NOW_ISO)
    b = awm.run(wm, tmp_path / "out-b", now=NOW_ISO)
    assert snapshot() == before
    report_a = json.loads(Path(a["report_paths"]["json"]).read_text())
    report_b = json.loads(Path(b["report_paths"]["json"]).read_text())
    assert report_a["proposals"] == report_b["proposals"] and report_a["proposals"]
    md = Path(a["report_paths"]["markdown"]).read_text()
    assert "work-memory 는 수정하지 않았다" in md and "근거:" in md


def test_max_per_kind_limits_proposals(tmp_path):
    rows = [entry(f"IN-00{i}", "issue-note", meta={}) for i in range(1, 8)]
    wm = write(tmp_path, rows)
    full = awm.run(wm, tmp_path / "o1", now=NOW_ISO, max_per_kind=None)["ranked"]
    one = awm.run(wm, tmp_path / "o2", now=NOW_ISO, max_per_kind=1)["ranked"]
    assert len([p for p in full if p["kind"] == "quality"]) > 1 and len([p for p in one if p["kind"] == "quality"]) == 1


def test_draft_pauses_for_control_plane_and_resume_merges_narrative(tmp_path):
    pytest.importorskip("langgraph.checkpoint.sqlite")
    wm = write(tmp_path, _rows_for_graph())
    saver = awm.sqlite_checkpointer(str(tmp_path / "ck.sqlite"))
    params = awm.make_params(wm, tmp_path / "out", now=NOW_ISO)
    paused = awm.start("t", params, saver)
    value = paused["__interrupt__"][0].value
    assert value["reason"] == "awaiting_draft" and Path(value["pack"]).exists()
    pack = json.loads(Path(value["pack"]).read_text())
    assert pack["proposals"] and "expects" in pack
    pid = pack["proposals"][0]["id"]
    done = awm.resume("t", {"summary": "먼저 볼 것: 등록 순서", "proposals": {pid: {"rewrite": "다시 쓴 설명"}}}, saver)
    md = Path(done["report_paths"]["markdown"]).read_text()
    assert "먼저 볼 것: 등록 순서" in md and "다시 쓴 설명" in md and "모델 요약" in md


def test_linear_fallback_without_langgraph_still_writes_report(tmp_path, monkeypatch):
    monkeypatch.setattr(awm, "LANGGRAPH_AVAILABLE", False)
    wm = write(tmp_path, _rows_for_graph())
    result = awm.run(wm, tmp_path / "out", now=NOW_ISO)
    assert Path(result["report_paths"]["json"]).exists() and result["ranked"]
