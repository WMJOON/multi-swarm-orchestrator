#!/usr/bin/env python3
"""Antigravity hooks.json adapter — MSO의 provider-neutral hook 스크립트(auditlog.py,
scaffold-check.sh, stop-check.sh, commit-work-memory.sh, work-memory-check.sh,
release-context.sh, workflow-context-hook.py, uug-context-hook.py)는 모두
Claude Code/Codex 식 snake_case stdin(JSON)·plain stdout 계약으로 작성돼 있다.
Antigravity는 camelCase stdin/stdout 에 5개 이벤트(PreToolUse/PostToolUse/
PreInvocation/PostInvocation/Stop)만 제공하고 SessionStart/UserPromptSubmit/
PreCompact 에 대응하는 이벤트가 없다 (antigravity.google/docs/hooks/, 확인: 2026-08-28).
이 어댑터가 그 간극을 메운다:

  posttooluse  → PostToolUse                     (그대로 대응)
  stop         → Stop                            (그대로 대응)
  session      → PreInvocation, invocationNum==0 에서만 실행 (SessionStart 대용)
  turn         → PreInvocation, 매 호출마다 실행 (UserPromptSubmit 대용)

미검증 가정(최초 실사용 시 확인 필요 — mso-PLAN-antigravity-provider-support.md 참조):
  - hook 프로세스의 cwd 가 workspace root 라고 가정한다 (Claude/Codex 관례를 따름).
    아니라면 hooks.json 의 command 를 절대경로로 교체해야 한다.
  - PreToolUse/PostToolUse/PreInvocation/Stop 의 비-JSON stdout·비정상 종료 코드
    처리(공식 문서 미기재)는 항상 유효한 JSON + exit 0 으로 방어적으로만 다룬다.
  - PreInvocation 입력에 사용자 발화 원문 필드가 없어 transcriptPath 의 마지막
    user 턴으로 근사한다 (uug-context-hook.py 전용).

사용법:
  adapter_antigravity.py <posttooluse|stop|session|turn> -- <script> [script-args...]
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """일부 훅(stop-check.sh 등)은 터미널 렌더링을 가정해 ANSI 색상 코드를 찍는다.
    Antigravity 의 reason/ephemeralMessage 는 터미널이 아니므로 제거한다."""
    return _ANSI_RE.sub("", text)

# Antigravity 도구명 -> 기존 훅이 기대하는 Claude 스타일 tool_name.
# auditlog.py/scaffold-check.sh 는 굵은 카테고리(명령 실행 vs 파일쓰기)만 구분한다.
TOOL_NAME_MAP = {
    "run_command": "Bash",
    "write_to_file": "Write",
    "replace_file_content": "Edit",
    "multi_replace_file_content": "MultiEdit",
}


def _read_stdin_json() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def _last_user_message(transcript_path: str) -> str:
    if not transcript_path:
        return ""
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        role = entry.get("role") or entry.get("type")
        if role in ("user", "user_message"):
            content = entry.get("content") or entry.get("text") or ""
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            return str(content)
    return ""


def _project_dir(agy: dict) -> str:
    paths = agy.get("workspacePaths") or []
    if paths:
        return str(paths[0])
    return os.environ.get("PROJECT_DIR", os.getcwd())


def build_legacy_input(mode: str, agy: dict) -> dict:
    session_id = agy.get("conversationId", "")
    if mode == "posttooluse":
        tool_call = agy.get("toolCall") or {}
        name = tool_call.get("name", "")
        return {
            "hook_event_name": "PostToolUse",
            "session_id": session_id,
            "tool_name": TOOL_NAME_MAP.get(name, name),
            "tool_input": tool_call.get("args") or {},
        }
    if mode == "stop":
        return {
            "hook_event_name": "Stop",
            "session_id": session_id,
            "stop_hook_active": False,
        }
    if mode == "session":
        return {"hook_event_name": "SessionStart", "session_id": session_id}
    if mode == "turn":
        prompt = _last_user_message(agy.get("transcriptPath", ""))
        return {"hook_event_name": "UserPromptSubmit", "session_id": session_id, "prompt": prompt}
    return {}


def build_output(mode: str, stdout: str) -> dict:
    text = _strip_ansi((stdout or "").strip()).strip()
    if mode == "posttooluse":
        # antigravity.google/docs/hooks/: PostToolUse expects an empty object.
        return {}
    if mode == "stop":
        if text:
            return {"decision": "continue", "reason": text}
        return {"decision": ""}
    if mode in ("session", "turn"):
        if text:
            return {"injectSteps": [{"ephemeralMessage": text}]}
        return {}
    return {}


def _run_target(script_args: list[str], legacy_input: dict, env: dict) -> str:
    script = Path(script_args[0])
    if script.suffix == ".sh":
        runner = ["bash", str(script), *script_args[1:]]
    else:
        runner = [sys.executable, str(script), *script_args[1:]]
    try:
        result = subprocess.run(
            runner,
            input=json.dumps(legacy_input),
            capture_output=True,
            text=True,
            timeout=25,
            env=env,
        )
    except Exception:
        return ""
    return result.stdout


def main() -> None:
    args = sys.argv[1:]
    if not args or "--" not in args:
        print("usage: adapter_antigravity.py <posttooluse|stop|session|turn> -- <script> [args...]",
              file=sys.stderr)
        print("{}")
        return

    sep = args.index("--")
    mode = args[0]
    script_args = args[sep + 1:]
    if not script_args:
        print("{}")
        return

    agy = _read_stdin_json()

    if mode == "session" and agy.get("invocationNum", 0) != 0:
        print("{}")
        return

    legacy_input = build_legacy_input(mode, agy)

    project_dir = _project_dir(agy)
    env = dict(os.environ)
    env.setdefault("PROJECT_DIR", project_dir)
    env.setdefault("WORKMEM_DIR", str(Path(project_dir) / "agent-context" / "work-memory"))

    stdout = _run_target(script_args, legacy_input, env)
    print(json.dumps(build_output(mode, stdout), ensure_ascii=False))


if __name__ == "__main__":
    main()
