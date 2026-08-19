"""wm_node.py relate 테스트 — 사후 라이프사이클 엣지 확정 (IN-0005)."""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "wm_node.py"


def _run(workmem: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "WORKMEM_DIR": str(workmem)},
    )


def _seed(workmem: Path, rel_dir: str, type_name: str, entry_id: str, **extra) -> None:
    path = workmem / rel_dir / f"{type_name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": entry_id,
        "type": type_name,
        "title": f"{entry_id} title",
        "text": "body",
        "tags": ["seed"],
        "created_at": "2026-06-01T00:00:00Z",
        "relations": [],
        "metadata": {},
    }
    entry.update(extra)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _entry(workmem: Path, rel_path: str, entry_id: str) -> dict:
    for line in (workmem / rel_path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            if e["id"] == entry_id:
                return e
    raise AssertionError(f"{entry_id} not found")


def _seed_ar_ud(workmem: Path) -> None:
    _seed(workmem, "track-record", "alternatives-record", "AR-0001")
    _seed(workmem, "track-record", "user-decision", "UD-0001")


def test_relate_adds_edge_to_existing_entry(tmp_path):
    workmem = tmp_path / "work-memory"
    _seed_ar_ud(workmem)

    result = _run(workmem, "relate", "AR-0001", "followed-by", "UD-0001")
    assert result.returncode == 0, result.stderr

    ar = _entry(workmem, "track-record/alternatives-record.jsonl", "AR-0001")
    assert ar["relations"] == [{"type": "followed-by", "target": "UD-0001"}]


def test_relate_preserves_other_lines_in_aggregate_file(tmp_path):
    """aggregate JSONL 의 다른 entry 줄이 손상되면 안 된다."""
    workmem = tmp_path / "work-memory"
    _seed(workmem, "track-record", "issue-note", "IN-0001")
    _seed(workmem, "track-record", "issue-note", "IN-0002")
    _seed(workmem, "track-record", "issue-note", "IN-0003")
    _seed(workmem, "track-record", "trouble-shooting", "TS-0001")

    assert _run(workmem, "relate", "IN-0002", "resolved-by", "TS-0001").returncode == 0

    lines = [l for l in (workmem / "track-record" / "issue-note.jsonl")
             .read_text(encoding="utf-8").splitlines() if l.strip()]
    assert [json.loads(l)["id"] for l in lines] == ["IN-0001", "IN-0002", "IN-0003"]
    assert json.loads(lines[0])["relations"] == []
    assert json.loads(lines[1])["relations"] == [{"type": "resolved-by", "target": "TS-0001"}]
    assert json.loads(lines[2])["relations"] == []


def test_relate_appends_to_existing_relations(tmp_path):
    workmem = tmp_path / "work-memory"
    _seed(workmem, "track-record", "user-decision", "UD-0001",
          relations=[{"type": "references", "target": "IN-0001"}])
    _seed(workmem, "release-record", "release-note", "RN-0001")

    assert _run(workmem, "relate", "UD-0001", "verified-in", "RN-0001").returncode == 0

    ud = _entry(workmem, "track-record/user-decision.jsonl", "UD-0001")
    assert ud["relations"] == [
        {"type": "references", "target": "IN-0001"},
        {"type": "verified-in", "target": "RN-0001"},
    ]


def test_relate_is_idempotent(tmp_path):
    workmem = tmp_path / "work-memory"
    _seed_ar_ud(workmem)

    assert _run(workmem, "relate", "AR-0001", "followed-by", "UD-0001").returncode == 0
    second = _run(workmem, "relate", "AR-0001", "followed-by", "UD-0001")
    assert second.returncode == 0
    assert "이미 존재" in second.stdout

    ar = _entry(workmem, "track-record/alternatives-record.jsonl", "AR-0001")
    assert len(ar["relations"]) == 1


def test_relate_missing_source_fails_loud(tmp_path):
    workmem = tmp_path / "work-memory"
    _seed_ar_ud(workmem)

    result = _run(workmem, "relate", "AR-9999", "followed-by", "UD-0001")
    assert result.returncode != 0
    assert "source entry 를 찾지 못함" in result.stdout + result.stderr


def test_relate_warns_on_dangling_target_but_records(tmp_path):
    """target 이 아직 없어도 기록은 남긴다 — 순서 의존을 강제하지 않는다."""
    workmem = tmp_path / "work-memory"
    _seed_ar_ud(workmem)

    result = _run(workmem, "relate", "AR-0001", "followed-by", "UD-9999")
    assert result.returncode == 0
    assert "dangling" in result.stderr

    ar = _entry(workmem, "track-record/alternatives-record.jsonl", "AR-0001")
    assert ar["relations"] == [{"type": "followed-by", "target": "UD-9999"}]


def test_relate_warns_on_unknown_relation_type(tmp_path):
    workmem = tmp_path / "work-memory"
    _seed_ar_ud(workmem)

    result = _run(workmem, "relate", "AR-0001", "bogus-relation", "UD-0001")
    assert "알 수 없는 relation" in result.stderr


def test_related_entries_pass_validate_and_appear_in_graph(tmp_path):
    workmem = tmp_path / "work-memory"
    _seed_ar_ud(workmem)
    assert _run(workmem, "relate", "AR-0001", "followed-by", "UD-0001").returncode == 0

    validated = _run(workmem, "validate", str(workmem))
    assert validated.returncode == 0, validated.stdout
    assert "모든 entry 가 스키마를 준수합니다" in validated.stdout

    graphed = _run(workmem, "graph", "AR-0001")
    assert graphed.returncode == 0
    assert "UD-0001" in graphed.stdout
