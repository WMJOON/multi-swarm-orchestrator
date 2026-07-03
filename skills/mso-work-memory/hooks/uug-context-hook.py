#!/usr/bin/env python3
"""UserPromptSubmit hook — UUG가 grounding한 target_project 가 현재 레포와 다르면
그 프로젝트의 agent-context 위치를 1줄 넛지로 주입한다.

값-전달 레이어(uug-context-hook): UUG의 `ug.py dispatch --json` 을 read-only
subprocess 로 호출해 intent_id/target_project 를 읽어온다. 이는 uug-grounding
SKILL.md "Hook 경계" 문서의 "MSO는 UUG를 모른다(단방향)" 원칙에 대한 의도적 예외이며,
user-decision 으로 승인됨(agent-toolkit-forge work-on-project 세션, 2026-07-03).
ug.py 부재/오류/timeout 시 조용히 통과 — UUG 자신의 훅과 동일한 degrade 원칙.
절대 프롬프트를 막지 않는다(exit 0). 기록·dispatch·worklog side effect 없음(순수 넛지).

등록은 mso-repository-setup 의 init.py --hook 이 담당한다(copy-form, Claude Code
provider 한정 — Codex 는 SessionStart 밖 stdout 전달 의미론이 미검증이라 보류).

환경변수:
  MSO_UUG_CONTEXT_DISABLED=1   훅 비활성화
  MSO_UUG_CONTEXT_INTENTS      게이팅할 intent_id 콤마 목록 (기본: work-on-project)
  CLAUDE_PROJECT_DIR           현재 레포 절대경로(Claude Code 가 주입) — target_path 와
                                같으면 자기 자신이므로 넛지 생략
"""
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_INTENTS = {"work-on-project"}

UG_CANDIDATES = [
    Path.home() / ".claude" / "skills" / "uug-grounding" / "scripts" / "ug.py",
    Path.home() / ".codex" / "skills" / "uug-grounding" / "scripts" / "ug.py",
]


def _find_ug():
    return next((p for p in UG_CANDIDATES if p.exists()), None)


def main():
    if os.environ.get("MSO_UUG_CONTEXT_DISABLED") == "1":
        return
    ug = _find_ug()
    if ug is None:
        return

    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return

    intents_env = os.environ.get("MSO_UUG_CONTEXT_INTENTS")
    allowed = {s.strip() for s in intents_env.split(",") if s.strip()} if intents_env else DEFAULT_INTENTS

    try:
        r = subprocess.run(
            [sys.executable, str(ug), "dispatch", "--json", prompt],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return
    if r.returncode != 0:
        return
    try:
        grounded = json.loads((r.stdout or "").strip())
    except ValueError:
        return

    intent_id = grounded.get("intent_id")
    target_project = grounded.get("target_project") or (grounded.get("slots") or {}).get("target_project")
    if intent_id not in allowed or not target_project:
        return

    try:
        rp = subprocess.run(
            [sys.executable, str(ug), "resolve", target_project],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return
    if rp.returncode != 0:
        return
    target_path_str = (rp.stdout or "").strip()
    if not target_path_str:
        return
    target_path = Path(target_path_str)

    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("PROJECT_DIR")
    if cwd:
        try:
            if Path(cwd).resolve() == target_path.resolve():
                return  # 현재 작업 레포와 동일 — 넛지 불필요
        except Exception:
            pass

    agent_context = target_path / "agent-context"
    if not agent_context.is_dir():
        return  # MSO 미스캐폴딩 프로젝트 — 참조할 게 없음

    print(f"[mso-context] target_project={target_project} (intent={intent_id}) — "
          f"현재 레포와 다른 프로젝트입니다. agent-context 확인: {agent_context}")


if __name__ == "__main__":
    main()
