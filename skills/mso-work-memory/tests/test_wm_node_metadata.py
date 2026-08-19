"""wm_node.py new 의 metadata 플래그 테스트 (--metadata / --meta) — IN-0003."""
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


def _new(workmem: Path, entry_type: str, *args: str) -> subprocess.CompletedProcess:
    return _run(workmem, "new", entry_type, "--title", "t", *args)


def _last_entry(workmem: Path, rel_path: str) -> dict:
    lines = [l for l in (workmem / rel_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(lines[-1])


def test_metadata_json_populates_entry(tmp_path):
    workmem = tmp_path / "work-memory"
    result = _new(workmem, "release-note",
                  "--metadata", json.dumps({
                      "version": "0.10.0",
                      "kind": "release",
                      "scope": "00_multi-swarm-orchestrator",
                  }))
    assert result.returncode == 0, result.stderr

    entry = _last_entry(workmem, "release-record/release-note.jsonl")
    assert entry["metadata"] == {
        "version": "0.10.0",
        "kind": "release",
        "scope": "00_multi-swarm-orchestrator",
    }


def test_metadata_json_supports_nested_structures(tmp_path):
    """AR 의 options 처럼 리스트/객체 중첩이 손실 없이 들어가야 한다."""
    workmem = tmp_path / "work-memory"
    options = [{"n": 1, "name": "A", "trade_off": "x"}, {"n": 2, "name": "B", "trade_off": "y"}]
    result = _new(workmem, "alternatives-record",
                  "--metadata", json.dumps({"provided_by": "agent", "options": options, "recommended": 1}))
    assert result.returncode == 0, result.stderr

    entry = _last_entry(workmem, "track-record/alternatives-record.jsonl")
    assert entry["metadata"]["options"] == options
    assert entry["metadata"]["recommended"] == 1


def test_meta_pairs_keep_strings_including_semver(tmp_path):
    workmem = tmp_path / "work-memory"
    result = _new(workmem, "release-note", "--meta", "version=0.10.0", "--meta", "kind=release")
    assert result.returncode == 0, result.stderr

    entry = _last_entry(workmem, "release-record/release-note.jsonl")
    # semver 는 숫자로 강제 변환되면 안 된다
    assert entry["metadata"]["version"] == "0.10.0"
    assert isinstance(entry["metadata"]["version"], str)
    assert entry["metadata"]["kind"] == "release"


def test_meta_coerces_only_bool_and_null_literals(tmp_path):
    workmem = tmp_path / "work-memory"
    result = _new(workmem, "user-decision",
                  "--meta", "structural=true", "--meta", "draft=false",
                  "--meta", "boundary=null", "--meta", "criterion=1.5")
    assert result.returncode == 0, result.stderr

    md = _last_entry(workmem, "track-record/user-decision.jsonl")["metadata"]
    assert md["structural"] is True
    assert md["draft"] is False
    assert md["boundary"] is None
    assert md["criterion"] == "1.5"  # 숫자처럼 보여도 문자열 유지


def test_meta_value_may_contain_equals_sign(tmp_path):
    workmem = tmp_path / "work-memory"
    result = _new(workmem, "issue-note", "--meta", "query=a=b")
    assert result.returncode == 0, result.stderr
    assert _last_entry(workmem, "track-record/issue-note.jsonl")["metadata"]["query"] == "a=b"


def test_layering_module_then_metadata_then_meta(tmp_path):
    workmem = tmp_path / "work-memory"
    result = _new(workmem, "issue-note",
                  "--module", "mod-from-shorthand",
                  "--metadata", json.dumps({"module": "mod-from-json", "severity": "minor"}),
                  "--meta", "severity=critical")
    assert result.returncode == 0, result.stderr

    md = _last_entry(workmem, "track-record/issue-note.jsonl")["metadata"]
    assert md["module"] == "mod-from-json"     # --metadata 가 --module 단축을 덮음
    assert md["severity"] == "critical"        # --meta 가 --metadata 를 덮음


def test_invalid_metadata_json_fails_loud(tmp_path):
    workmem = tmp_path / "work-memory"
    result = _new(workmem, "issue-note", "--metadata", "{not json}")
    assert result.returncode != 0
    assert "유효한 JSON" in result.stdout + result.stderr
    assert not (workmem / "track-record" / "issue-note.jsonl").exists()


def test_non_object_metadata_json_fails_loud(tmp_path):
    workmem = tmp_path / "work-memory"
    result = _new(workmem, "issue-note", "--metadata", '["a", "b"]')
    assert result.returncode != 0
    assert "JSON 객체" in result.stdout + result.stderr


def test_malformed_meta_pair_fails_loud(tmp_path):
    """metadata 는 스키마 필수 payload 라 조용히 유실되면 안 된다 (relation 과 달리 hard error)."""
    workmem = tmp_path / "work-memory"
    result = _new(workmem, "issue-note", "--meta", "kind-release")
    assert result.returncode != 0
    assert "--meta 형식" in result.stdout + result.stderr
    assert not (workmem / "track-record" / "issue-note.jsonl").exists()


def test_backward_compat_no_flags_and_module_only(tmp_path):
    workmem = tmp_path / "work-memory"
    assert _new(workmem, "issue-note").returncode == 0
    assert _last_entry(workmem, "track-record/issue-note.jsonl")["metadata"] == {}

    assert _new(workmem, "issue-note", "--module", "m1").returncode == 0
    entry = _last_entry(workmem, "track-record/issue-note.jsonl")
    assert entry["metadata"] == {"module": "m1"}
    assert "m1" in entry["tags"]  # --module 의 기존 태그 동작 유지


def test_created_entry_passes_validate(tmp_path):
    workmem = tmp_path / "work-memory"
    _new(workmem, "release-note", "--tags", "release",
         "--meta", "version=0.10.0", "--meta", "kind=release")
    result = _run(workmem, "validate", str(workmem))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "모든 entry 가 스키마를 준수합니다" in result.stdout
