"""wm_node.py validate 의 필수 필드 검사 — new 산출물 왕복 보장 (IN-0004)."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import wm_store  # noqa: E402


def _nt_entries(workmem, type_dir, type_name):
    """new 가 만든 큐레이션 기록(.nt)을 읽는다."""
    return wm_store.load_nt_entries(workmem / type_dir / f"{type_name}.nt")[0]


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "wm_node.py"


def _run(workmem: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "WORKMEM_DIR": str(workmem)},
    )


def _write(workmem: Path, entry: dict) -> None:
    path = workmem / "track-record" / "issue-note.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _base(**over) -> dict:
    entry = {
        "id": "IN-0001",
        "type": "issue-note",
        "description": "t",
        "content": "body",
        "tags": [],
        "created_at": "2026-06-01T00:00:00Z",
        "relations": [],
        "metadata": {},
    }
    entry.update(over)
    return entry


def test_new_output_passes_validate_without_tags(tmp_path):
    """new 가 만든 entry 는 --tags 없이도 자기 validate 를 통과해야 한다 (왕복 불변)."""
    workmem = tmp_path / "work-memory"
    created = _run(workmem, "new", "issue-note", "--description", "no tags", "--meta", "severity=minor", "--scope", "repository")
    assert created.returncode == 0, created.stderr

    result = _run(workmem, "validate", str(workmem))
    assert result.returncode == 0, result.stdout
    assert "모든 entry 가 스키마를 준수합니다" in result.stdout


def test_new_hints_when_tags_missing(tmp_path):
    workmem = tmp_path / "work-memory"
    result = _run(workmem, "new", "issue-note", "--description", "no tags", "--meta", "severity=minor", "--scope", "repository")
    assert "tags 없음" in result.stderr


def test_empty_tags_is_valid_but_non_list_is_not(tmp_path):
    workmem = tmp_path / "work-memory"
    _write(workmem, _base(id="IN-0001", tags=[]))
    assert _run(workmem, "validate", str(workmem)).returncode == 0

    _write(workmem, _base(id="IN-0002", tags="not-a-list"))
    result = _run(workmem, "validate", str(workmem))
    assert result.returncode != 0
    assert "tags 는 list 여야 함" in result.stdout


def test_missing_tags_key_is_reported(tmp_path):
    workmem = tmp_path / "work-memory"
    entry = _base()
    del entry["tags"]
    _write(workmem, entry)

    result = _run(workmem, "validate", str(workmem))
    assert result.returncode != 0
    assert "tags 는 list 여야 함" in result.stdout


def test_scalar_required_fields_still_reject_empty(tmp_path):
    """list 완화가 스칼라 필드 탐지력을 약화시키면 안 된다."""
    workmem = tmp_path / "work-memory"
    _write(workmem, _base(id="IN-0001", description=""))
    _write(workmem, _base(id="IN-0002", content=""))
    _write(workmem, _base(id="IN-0003", created_at=""))

    result = _run(workmem, "validate", str(workmem))
    assert result.returncode != 0
    out = result.stdout
    assert "[MISSING] issue-note.jsonl:1: description" in out
    assert "[MISSING] issue-note.jsonl:2: content" in out
    assert "[MISSING] issue-note.jsonl:3: created_at" in out


# ── v0.16.0 (schema v1.4.0): description/content, 길이 상한, node ──

def test_legacy_title_text_still_validate(tmp_path):
    """옛 title/text entry 는 폴백으로 통과한다 (이행 전 기록을 깨뜨리지 않는다)."""
    workmem = tmp_path / "work-memory"
    entry = _base()
    entry.pop("description"); entry.pop("content")
    entry.update(title="옛 제목", text="옛 본문")
    _write(workmem, entry)
    result = _run(workmem, "validate", str(workmem))
    assert result.returncode == 0, result.stdout


def test_description_over_200_is_flagged(tmp_path):
    workmem = tmp_path / "work-memory"
    _write(workmem, _base(id="IN-0001", description="가" * 200))
    _write(workmem, _base(id="IN-0002", description="가" * 201))
    result = _run(workmem, "validate", str(workmem))
    assert result.returncode != 0
    assert "[LEN] issue-note.jsonl:2: description 201자 > 200자" in result.stdout
    assert "[LEN] issue-note.jsonl:1" not in result.stdout  # 200자는 통과(옛 기록의 metadata 누락은 경고라 [META] 줄이 있을 수 있다)


def test_new_with_description_content_and_node(tmp_path):
    workmem = tmp_path / "work-memory"
    created = _run(workmem, "new", "user-decision", "--description", "요약", "--content", "본문", "--meta", "rationale=이유", "--scope", "repository",
                   "--node", "discovery-s-001", "--node", "discovery-v-001", "--node", "discovery-s-001")
    assert created.returncode == 0, created.stderr
    entry = _nt_entries(workmem, "track-record", "user-decision")[0]
    assert entry["description"] == "요약" and entry["content"] == "본문"
    assert "title" not in entry and "text" not in entry
    assert entry["node"] == ["discovery-s-001", "discovery-v-001"]  # 중복 제거, 순서 유지
    assert _run(workmem, "validate", str(workmem)).returncode == 0


def test_new_rejects_description_over_limit(tmp_path):
    workmem = tmp_path / "work-memory"
    result = _run(workmem, "new", "issue-note", "--description", "x" * 201)
    assert result.returncode != 0
    assert "200자" in result.stderr or "200자" in result.stdout
    assert not (workmem / "track-record").exists()


def test_new_deprecated_title_text_alias_warns_and_maps(tmp_path):
    workmem = tmp_path / "work-memory"
    created = _run(workmem, "new", "issue-note", "--title", "옛 인자", "--text", "옛 본문", "--meta", "severity=minor", "--scope", "repository")
    assert created.returncode == 0, created.stderr
    assert "deprecated" in created.stderr
    entry = _nt_entries(workmem, "track-record", "issue-note")[0]
    assert entry["description"] == "옛 인자" and entry["content"] == "옛 본문"


def test_node_must_be_list_of_strings(tmp_path):
    workmem = tmp_path / "work-memory"
    _write(workmem, _base(node="discovery-s-001"))
    result = _run(workmem, "validate", str(workmem))
    assert result.returncode != 0
    assert "node 는 list[str]" in result.stdout


def test_map_node_adds_removes_and_is_idempotent(tmp_path):
    """기존 기록에 related 매핑(node)을 제자리에서 붙이고 뗀다."""
    workmem = tmp_path / "work-memory"
    _write(workmem, _base(id="IN-0001"))
    path = workmem / "track-record" / "issue-note.jsonl"

    added = _run(workmem, "map-node", "IN-0001", "--node", "discovery-s-001", "--node", "discovery-v-001")
    assert added.returncode == 0, added.stderr
    entry = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert entry["node"] == ["discovery-s-001", "discovery-v-001"]
    assert entry["description"] == "t"                              # 다른 필드는 그대로

    again = _run(workmem, "map-node", "IN-0001", "--node", "discovery-s-001")
    assert "변경 없음" in again.stdout

    removed = _run(workmem, "map-node", "IN-0001", "--node", "discovery-s-001", "--node", "discovery-v-001", "--remove")
    assert removed.returncode == 0
    assert "node" not in json.loads(path.read_text(encoding="utf-8").splitlines()[0])  # 비면 필드를 지운다

    assert _run(workmem, "map-node", "IN-9999", "--node", "x").returncode != 0
    assert _run(workmem, "validate", str(workmem)).returncode == 0


# ── v0.16.0: 밀리초 hex id ──

def _new_id(workmem, type_name="issue-note"):
    created = _run(workmem, "new", type_name, "--description", "d", "--meta", "severity=minor", "--scope", "repository")
    assert created.returncode == 0, created.stderr
    return _nt_entries(workmem, "track-record", type_name)[-1]["id"]


def test_new_id_is_prefix_plus_12_hex_millis_and_decodes_to_creation_time(tmp_path):
    import datetime as dt, importlib.util, re
    workmem = tmp_path / "work-memory"
    before = dt.datetime.now(dt.timezone.utc)
    new_id = _new_id(workmem)
    after = dt.datetime.now(dt.timezone.utc)
    assert re.fullmatch(r"IN-[0-9a-f]{12}", new_id), new_id
    spec = importlib.util.spec_from_file_location("wm_node_idtest", SCRIPT)
    mod = importlib.util.module_from_spec(spec); sys.modules["wm_node_idtest"] = mod; spec.loader.exec_module(mod)
    created = mod.id_time(new_id)
    assert before - dt.timedelta(seconds=1) <= created <= after + dt.timedelta(seconds=1)  # id 가 발생 시각을 담는다
    assert mod.id_time("IN-0012") is None                                                   # 옛 십진 id 는 시각 없음


def test_new_ids_are_unique_and_time_ordered(tmp_path):
    workmem = tmp_path / "work-memory"
    ids = [_new_id(workmem) for _ in range(5)]
    assert len(set(ids)) == 5
    assert ids == sorted(ids)                       # 같은 길이 hex 라 사전순 = 시간순
    assert _run(workmem, "validate", str(workmem)).returncode == 0


def test_millisecond_collision_is_avoided(tmp_path):
    """같은 밀리초에 기존 id 가 있으면 +1ms 로 비켜 간다."""
    import importlib.util, time
    workmem = tmp_path / "work-memory"
    spec = importlib.util.spec_from_file_location("wm_node_coll", SCRIPT)
    mod = importlib.util.module_from_spec(spec); sys.modules["wm_node_coll"] = mod; spec.loader.exec_module(mod)
    os.environ["WORKMEM_DIR"] = str(workmem)
    try:
        ms = int(time.time() * 1000)
        taken = [f"IN-{ms + k:012x}" for k in range(0, 3000)]  # 앞으로 3초 분을 모두 점유
        for tid in taken:
            _write(workmem, _base(id=tid))
        new_id = mod.next_id("issue-note")
        assert new_id not in set(taken)
    finally:
        os.environ.pop("WORKMEM_DIR", None)


def test_legacy_decimal_ids_coexist_and_no_9999_overflow(tmp_path):
    workmem = tmp_path / "work-memory"
    _write(workmem, _base(id="IN-9999"))
    _write(workmem, _base(id="IN-10000"))           # 옛 방식이면 다음 id 가 IN-10000 으로 중복됐다
    new_id = _new_id(workmem)
    assert new_id not in ("IN-9999", "IN-10000")
    result = _run(workmem, "validate", str(workmem))
    assert result.returncode == 0, result.stdout   # 십진과 hex 가 섞여도 DUP-ID 없음
