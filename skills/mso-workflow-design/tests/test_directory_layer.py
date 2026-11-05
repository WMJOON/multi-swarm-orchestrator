"""디렉터리 층(wf:Directory, wf:storedIn) SHACL 반례 테스트 (2026-11-05, 계획 승인).

실제 레지스트리(index.abox.ttl)를 기준으로 한 줄씩 깨뜨려 해당 제약이 잡히는지 확인한다.
레지스트리 경로는 환경변수 MSO_INDEX_TTL 로 지정하고, 없으면 건너뛴다(저장소 밖 픽스처에 의존하지 않도록).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
VALIDATOR = SKILL / "scripts" / "validate_artifact_layer.py"
REG = os.environ.get("MSO_INDEX_TTL")
pytestmark = pytest.mark.skipif(not REG or not Path(REG).is_file(), reason="MSO_INDEX_TTL 미지정")


def _run(text: str, tmp_path: Path) -> str:
    p = tmp_path / "index.abox.ttl"
    p.write_text(text, encoding="utf-8")
    out = subprocess.run([sys.executable, str(VALIDATOR), "--root", str(tmp_path), "--registry", str(p),
                          "--workflow-dir", str(tmp_path / "none"), "--no-history-check"],
                         capture_output=True, text=True)
    return out.stdout


def _src() -> str:
    return Path(REG).read_text(encoding="utf-8")


def test_real_registry_is_clean(tmp_path):
    out = _run(_src(), tmp_path)
    assert "Violation 0건" in out, out


def test_directory_path_without_trailing_slash_fails(tmp_path):
    text = _src().replace('wf:path "01.planning/"^^xsd:string', 'wf:path "01.planning"^^xsd:string', 1)
    assert "path 는 정확히 하나, 상대 경로이며 '/' 로 끝나야 한다" in _run(text, tmp_path)


def test_duplicate_directory_path_fails(tmp_path):
    dup = ('\n<https://mso.dev/id/chatbot-1.5/directory/dupe000000000001> '
           '<http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://mso.dev/ontology/workflow#Directory> ; '
           '<https://mso.dev/ontology/workflow#path> "01.planning/"^^<http://www.w3.org/2001/XMLSchema#string> .\n')
    assert "같은 path 를 가진 디렉터리가 둘 이상" in _run(_src() + dup, tmp_path)


def test_artifact_without_storedin_fails(tmp_path):
    src = _src()
    # storedIn 이 문장의 마지막 트리플이면(' .') 앞 줄의 ';' 를 '.' 로 바꿔 문장을 닫는다.
    text, n = re.subn(r";\s*\n\s*wf:storedIn dir:[0-9a-f]+ \.", " .", src, count=1)
    if n == 0:
        text, n = re.subn(r"\n\s*wf:storedIn dir:[0-9a-f]+ ;", "", src, count=1)
    assert n == 1, "storedIn 줄을 찾지 못함"
    out = _run(text, tmp_path)
    assert "정확히 하나의 저장 디렉터리" in out, out
