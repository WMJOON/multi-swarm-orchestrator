"""pattern_to_workflow_draft.py: 절차형 패턴에서만 draft workflow 를 만든다."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
GEN = SKILL / "scripts" / "pattern_to_workflow_draft.py"
VALIDATE = SKILL / "scripts" / "validate_abox.py"

TEXT = "두 에피소드의 공통 흐름. 패턴: 1. 측정 우선: 규모를 먼저 잰다. 2. 파일럿: 1개를 round-trip 으로 증명한 뒤 복제. 3. 가드: 없는 것을 만들지 않는다."


def wm(tmp: Path, text: str = TEXT, rels=("EP-0001", "EP-0002")) -> Path:
    d = tmp / "agent-context" / "work-memory" / "insight-record"; d.mkdir(parents=True)
    (d / "pattern.jsonl").write_text(json.dumps({"id": "PT-0001", "title": "T", "text": text, "relations": [{"type": "generalized-in", "target": r} for r in rels]}, ensure_ascii=False) + "\n", encoding="utf-8")
    return tmp


def run(root: Path, *a):
    return subprocess.run([sys.executable, str(GEN), "--pattern", "PT-0001", "--root", str(root), *a], text=True, capture_output=True)


def test_generates_valid_draft_chain(tmp_path):
    r = run(wm(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    out = tmp_path / "agent-context/workflow/drafts/workflow-pt-0001.abox.ttl"
    ttl = out.read_text(encoding="utf-8")
    assert ttl.count("wf:Task") == 3 and 'wf:status "draft"' in ttl and "Gate candidates" in ttl
    v = subprocess.run([sys.executable, str(VALIDATE), str(out.parent)], text=True, capture_output=True)
    assert v.returncode == 0, v.stdout + v.stderr


def test_insufficient_episodes_exit_3(tmp_path):
    r = run(wm(tmp_path, rels=("EP-0001",)))
    assert r.returncode == 3 and not (tmp_path / "agent-context/workflow/drafts").exists()


def test_non_procedural_pattern_exit_2(tmp_path):
    assert run(wm(tmp_path, text="원칙만 있고 번호 단계가 없다.")).returncode == 2


def test_dry_run_writes_nothing(tmp_path):
    r = run(wm(tmp_path), "--dry-run")
    assert r.returncode == 0 and "wf:Workflow" in r.stdout and not (tmp_path / "agent-context/workflow/drafts").exists()


def test_unknown_pattern_exit_2(tmp_path):
    root = wm(tmp_path)
    r = subprocess.run([sys.executable, str(GEN), "--pattern", "PT-9999", "--root", str(root)], text=True, capture_output=True)
    assert r.returncode == 2
