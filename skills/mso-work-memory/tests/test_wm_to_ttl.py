import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "wm_to_ttl.py"


def _write_entry(root: Path, rel_dir: str, entry: dict):
    target = root / rel_dir / f"{entry['id']}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def test_wm_to_ttl_validates_lifecycle_and_external_reference(tmp_path):
    workmem = tmp_path / "work-memory"
    issue = {
        "id": "IN-0001",
        "type": "issue-note",
        "title": "Issue",
        "text": "Something broke.",
        "tags": ["test"],
        "created_at": "2026-06-27T00:00:00Z",
        "relations": [
            {"type": "resolved-by", "target": "TS-0001"},
            {"type": "references", "target": "docs/spec.md"},
        ],
        "metadata": {"severity": "major"},
    }
    fix = {
        "id": "TS-0001",
        "type": "trouble-shooting",
        "title": "Fix",
        "text": "Fixed it.",
        "tags": ["test"],
        "created_at": "2026-06-27T00:01:00Z",
        "relations": [{"type": "caused-by", "target": "IN-0001"}],
        "metadata": {"resolution": "patched", "root_cause": "bug", "prevention": "test"},
    }
    _write_entry(workmem, "track-record/issue-note", issue)
    _write_entry(workmem, "track-record/trouble-shooting", fix)

    ttl_out = tmp_path / "work-memory.abox.ttl"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(workmem), "--ttl-out", str(ttl_out)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    ttl = ttl_out.read_text(encoding="utf-8")
    assert "wm:IssueNote" in ttl
    assert "wm:TroubleShooting" in ttl
    assert "wm:ExternalReference" in ttl
    assert "resolvedBy" in ttl


def test_wm_to_ttl_validates_release_lifecycle(tmp_path):
    workmem = tmp_path / "work-memory"
    fix = {
        "id": "TS-0001",
        "type": "trouble-shooting",
        "title": "Fix",
        "text": "Fixed it.",
        "tags": [],
        "created_at": "2026-07-17T00:00:00Z",
        "relations": [{"type": "released-in", "target": "RN-0001"}],
        "metadata": {"resolution": "patched", "root_cause": "bug", "prevention": "test"},
    }
    principle = {
        "id": "PR-0001",
        "type": "principle",
        "title": "Old rule",
        "text": "No longer holds after v0.7.0.",
        "tags": [],
        "created_at": "2026-07-17T00:00:00Z",
        "relations": [{"type": "invalidated-by", "target": "RN-0001"}],
        "metadata": {"statement": "old rule", "scope": "project", "status": "deprecated"},
    }
    release = {
        "id": "RN-0001",
        "type": "release-note",
        "title": "v0.7.0 release",
        "text": "Shipped the fix.",
        "tags": ["release"],
        "created_at": "2026-07-17T00:01:00Z",
        "relations": [],
        "metadata": {"version": "0.7.0", "released_at": "2026-07-17T00:01:00Z", "kind": "release", "scope": "project"},
    }
    rollback = {
        "id": "RN-0002",
        "type": "release-note",
        "title": "rollback v0.7.0",
        "text": "Rolled back.",
        "tags": ["release", "rollback"],
        "created_at": "2026-07-17T01:00:00Z",
        "relations": [{"type": "rolls-back", "target": "RN-0001"}],
        "metadata": {"version": "0.7.0-rollback", "released_at": "2026-07-17T01:00:00Z", "kind": "rollback", "scope": "project"},
    }
    _write_entry(workmem, "track-record/trouble-shooting", fix)
    _write_entry(workmem, "insight-record/principle", principle)
    _write_entry(workmem, "release-record/release-note", release)
    _write_entry(workmem, "release-record/release-note", rollback)

    ttl_out = tmp_path / "work-memory.abox.ttl"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(workmem), "--ttl-out", str(ttl_out)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    ttl = ttl_out.read_text(encoding="utf-8")
    assert "wm:ReleaseNote" in ttl
    assert "releasedIn" in ttl
    assert "invalidatedBy" in ttl
    assert "rollsBack" in ttl


def test_wm_to_ttl_rejects_rolls_back_from_non_release_note(tmp_path):
    workmem = tmp_path / "work-memory"
    fix = {
        "id": "TS-0001",
        "type": "trouble-shooting",
        "title": "Fix",
        "text": "Fixed it.",
        "tags": [],
        "created_at": "2026-07-17T00:00:00Z",
        "relations": [{"type": "rolls-back", "target": "RN-0001"}],
        "metadata": {"resolution": "patched", "root_cause": "bug", "prevention": "test"},
    }
    release = {
        "id": "RN-0001",
        "type": "release-note",
        "title": "v0.7.0 release",
        "text": "Shipped.",
        "tags": [],
        "created_at": "2026-07-17T00:01:00Z",
        "relations": [],
        "metadata": {"version": "0.7.0", "released_at": "2026-07-17T00:01:00Z", "kind": "release", "scope": "project"},
    }
    _write_entry(workmem, "track-record/trouble-shooting", fix)
    _write_entry(workmem, "release-record/release-note", release)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(workmem)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "TS-0001" in result.stdout
    assert "ReleaseNote" in result.stdout


def test_wm_to_ttl_rejects_wrong_invalidated_by_target_type(tmp_path):
    workmem = tmp_path / "work-memory"
    principle = {
        "id": "PR-0001",
        "type": "principle",
        "title": "Rule",
        "text": "Invalidated by a non-release target (invalid).",
        "tags": [],
        "created_at": "2026-07-17T00:00:00Z",
        "relations": [{"type": "invalidated-by", "target": "TS-0001"}],
        "metadata": {"statement": "rule", "scope": "project", "status": "accepted"},
    }
    fix = {
        "id": "TS-0001",
        "type": "trouble-shooting",
        "title": "Fix",
        "text": "Fixed it.",
        "tags": [],
        "created_at": "2026-07-17T00:01:00Z",
        "relations": [],
        "metadata": {"resolution": "patched", "root_cause": "bug", "prevention": "test"},
    }
    _write_entry(workmem, "insight-record/principle", principle)
    _write_entry(workmem, "track-record/trouble-shooting", fix)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(workmem)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "invalidatedBy" in result.stdout


def test_wm_to_ttl_rejects_wrong_resolved_by_target_type(tmp_path):
    workmem = tmp_path / "work-memory"
    issue = {
        "id": "IN-0001",
        "type": "issue-note",
        "title": "Issue",
        "text": "Something broke.",
        "tags": [],
        "created_at": "2026-06-27T00:00:00Z",
        "relations": [{"type": "resolved-by", "target": "AD-0001"}],
        "metadata": {},
    }
    decision = {
        "id": "AD-0001",
        "type": "agent-decision",
        "title": "Decision",
        "text": "Chose a path.",
        "tags": [],
        "created_at": "2026-06-27T00:01:00Z",
        "relations": [],
        "metadata": {"rationale": "fast", "alternatives": ["a"], "confidence": "high"},
    }
    _write_entry(workmem, "track-record/issue-note", issue)
    _write_entry(workmem, "track-record/agent-decision", decision)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(workmem)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "resolvedBy" in result.stdout
