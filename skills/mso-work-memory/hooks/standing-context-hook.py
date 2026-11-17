#!/usr/bin/env python3
"""SessionStart hook — 노드와 무관하게 항상 적용되는 교훈(standing context)을 세션 시작·압축·재개 때 한 번 주입한다.

기본 대상: scope 가 repository/global 인 accepted principle(폐기·대체된 것은 제외). 요약 목록(id [type] description)만 넣고
본문은 `wm_context.py show <id>` 로 펼친다. 워크플로우 커서가 없는 작업(레일 밖)에서도 원칙이 보이게 하는 것이 목적이다 —
노드별 주입(workflow-context-hook.py)은 노드에 매핑된 기록만 넣기 때문이다.

없거나 결과가 비면 **무출력·exit 0**. 절대 세션을 막지 않는다.

환경변수:
  MSO_STANDING_CONTEXT_DISABLED=1   훅 비활성화
  MSO_STANDING_TOP_K                주입할 entry 수 상한 (기본 5)
  MSO_STANDING_MAX_CHARS            요약 목록 총량 예산(글자, 기본 900)
  MSO_STANDING_TYPES                대상 타입 (기본 principle)
  MSO_STANDING_SCOPES               대상 scope (기본 repository,global)
  WORKMEM_DIR                       work-memory 루트 (미설정 시 프로젝트 기본 경로)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _find_wm_context() -> Path | None:
    here = Path(__file__).resolve().parent
    for cand in (here / "wm_context.py", here.parent / "scripts" / "wm_context.py"):
        if cand.exists():
            return cand
    return None


def main() -> None:
    if os.environ.get("MSO_STANDING_CONTEXT_DISABLED") == "1":
        return
    project_dir = Path(os.environ.get("PROJECT_DIR") or os.environ.get("CODEX_PROJECT_DIR")
                       or os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    script = _find_wm_context()
    if script is None:
        return
    workmem = os.environ.get("WORKMEM_DIR") or str(project_dir / "agent-context" / "work-memory")
    if not Path(workmem).exists():
        return
    cmd = [sys.executable, str(script), "standing",
           "--top-k", os.environ.get("MSO_STANDING_TOP_K", "5"),
           "--max-chars", os.environ.get("MSO_STANDING_MAX_CHARS", "900"),
           "--types", os.environ.get("MSO_STANDING_TYPES", "principle"),
           "--scopes", os.environ.get("MSO_STANDING_SCOPES", "repository,global")]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env={**os.environ, "WORKMEM_DIR": workmem})
    except Exception:  # noqa: BLE001
        return
    output = (result.stdout or "").strip() if result.returncode == 0 else ""
    if output:
        print(output)


if __name__ == "__main__":
    main()
