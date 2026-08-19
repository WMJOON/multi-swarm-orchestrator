#!/usr/bin/env python3
"""UserPromptSubmit hook — workflow cursor 가 가리키는 node 의 work-memory
context pack 을 컨텍스트에 주입한다 (UD-0015).

에이전트가 workflow node 에 진입할 때 `wm_context.py cursor set <node> [--ttl ...]`
로 커서를 남기면, 이후 매 발화마다 이 훅이 그 node 의 연관 기억을 주입한다.
즉 검색 키는 사용자 발화가 아니라 **workflow 실행 위치**다.

전달 의미론: UserPromptSubmit 의 plain stdout 은 모델 컨텍스트에 주입된다
(_reference/claude-code/hook-stdout-delivery.md). PreToolUse 는 stdout 이 모델에
닿지 않아(차단 경로로만 전달) provisioning 에 부적합 — AR-0002 에서 기각.

커서가 없거나(=workflow 레일 밖 작업) wm_context.py 를 못 찾거나 결과가 비면
**무출력·exit 0**. 절대 프롬프트를 막지 않는다.

환경변수:
  MSO_WORKFLOW_CONTEXT_DISABLED=1   훅 비활성화
  MSO_WORKFLOW_CONTEXT_TOP_K        주입할 entry 수 (기본 3 — 매 턴 주입이라 보수적)
  WORKMEM_DIR                       work-memory 루트 (미설정 시 프로젝트 기본 경로)
  CLAUDE_PROJECT_DIR                현재 레포 절대경로 (Claude Code 가 주입)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_TOP_K = "3"


def _find_wm_context() -> Path | None:
    """copy-form(훅 옆) 우선, 스킬 레이아웃(../scripts/) 폴백."""
    here = Path(__file__).resolve().parent
    for cand in (here / "wm_context.py", here.parent / "scripts" / "wm_context.py"):
        if cand.exists():
            return cand
    return None


def main() -> None:
    if os.environ.get("MSO_WORKFLOW_CONTEXT_DISABLED") == "1":
        return

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("PROJECT_DIR") or ".")
    cursor_file = project_dir / ".claude" / "state" / "workflow-cursor.json"
    if not cursor_file.exists():
        return  # workflow 레일 밖 — 침묵

    try:
        cursor = json.loads(cursor_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    node = (cursor or {}).get("node") if isinstance(cursor, dict) else None
    if not node:
        return

    script = _find_wm_context()
    if script is None:
        return

    workmem = os.environ.get("WORKMEM_DIR") or str(project_dir / "agent-context" / "work-memory")
    if not Path(workmem).exists():
        return

    cmd = [sys.executable, str(script), "node", "--node", str(node),
           "--top-k", os.environ.get("MSO_WORKFLOW_CONTEXT_TOP_K", DEFAULT_TOP_K)]
    ttl = cursor.get("ttl")
    if ttl and Path(ttl).exists():
        cmd += ["--ttl", str(ttl)]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            env={**os.environ, "WORKMEM_DIR": workmem},
        )
    except Exception:
        return
    if result.returncode != 0:
        return

    output = (result.stdout or "").strip()
    if output:
        print(output)


if __name__ == "__main__":
    main()
