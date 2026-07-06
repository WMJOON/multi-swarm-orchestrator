#!/usr/bin/env python3
"""
mso-hermes-bridge/scripts/hermes_bridge.py

MSO에서 Hermes Agent를 호출하는 Python 브리지.
bridge.sh의 Python 버전 ― JSON 처리와 에러 핸들링이 더 견고하다.

Usage:
    # Runs API (비동기, 폴링)
    python3 hermes_bridge.py run "<task>" [--conversation <id>] [--timeout <sec>]

    # Chat Completions (동기, 단순 Q&A)
    python3 hermes_bridge.py sync "<task>" [--system "<system prompt>"]

Exit codes: 0=성공, 1=Hermes 미실행, 2=timeout, 3=run 실패, 4=인증 실패
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


BASE = os.environ.get("HERMES_BASE", "http://127.0.0.1:8642")
KEY = os.environ.get("HERMES_API_KEY", "")


def _req(method: str, path: str, body: dict | None = None, *, key: str = KEY) -> dict:
    """단순 HTTP 요청. urllib만 사용 (외부 의존성 없음)."""
    url = BASE.rstrip("/") + path
    data = json.dumps(body).encode() if body else None
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("[hermes-bridge] ERROR: 인증 실패 (401). HERMES_API_KEY 확인", file=sys.stderr)
            sys.exit(4)
        raise


def health_check() -> bool:
    try:
        _req("GET", "/v1/health")
        return True
    except Exception:
        return False


def run_mode(task: str, conversation: str | None, timeout: int) -> int:
    """Runs API ― POST /v1/runs → 폴링 → output 출력."""
    if not health_check():
        print(f"[hermes-bridge] ERROR: Hermes 미실행 ({BASE}/v1/health 응답 없음)", file=sys.stderr)
        print("[hermes-bridge] 'hermes gateway' 를 실행하세요", file=sys.stderr)
        return 1

    payload: dict = {"input": task}
    if conversation:
        payload["conversation"] = conversation

    resp = _req("POST", "/v1/runs", payload)
    run_id = resp["run_id"]
    print(f"[hermes-bridge] run 시작: {run_id}", file=sys.stderr)

    elapsed = 0
    interval = 5
    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval

        state = _req("GET", f"/v1/runs/{run_id}")
        status = state.get("status", "")

        if status == "completed":
            print(f"[hermes-bridge] 완료 ({elapsed}s)", file=sys.stderr)
            print(state.get("output", ""))
            return 0
        elif status in ("failed", "cancelled"):
            print(f"[hermes-bridge] ERROR: run {status}", file=sys.stderr)
            print(state.get("output", ""), file=sys.stderr)
            return 3
        else:
            print(f"[hermes-bridge] 대기 중... ({elapsed}s / status={status})", file=sys.stderr)

    print(f"[hermes-bridge] ERROR: timeout ({timeout}s). run_id={run_id}", file=sys.stderr)
    print(f"[hermes-bridge] 수동 확인: curl {BASE}/v1/runs/{run_id}", file=sys.stderr)
    return 2


def sync_mode(task: str, system_prompt: str | None) -> int:
    """Chat Completions (동기). 단순 Q&A, 짧은 태스크용."""
    if not health_check():
        print(f"[hermes-bridge] ERROR: Hermes 미실행 ({BASE}/v1/health)", file=sys.stderr)
        return 1

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": task})

    resp = _req("POST", "/v1/chat/completions", {
        "model": "hermes-agent",
        "messages": messages,
        "stream": False,
    })
    content = resp["choices"][0]["message"]["content"]
    print(content)
    return 0


def main():
    if not KEY:
        print("[hermes-bridge] ERROR: HERMES_API_KEY 환경변수 미설정", file=sys.stderr)
        sys.exit(4)

    parser = argparse.ArgumentParser(description="MSO Hermes Bridge")
    sub = parser.add_subparsers(dest="mode", required=True)

    run_p = sub.add_parser("run", help="Runs API (비동기 폴링)")
    run_p.add_argument("task", help="위임할 태스크 설명")
    run_p.add_argument("--conversation", default=None, help="세션 ID (ex: mso-proj-analysis)")
    run_p.add_argument("--timeout", type=int, default=300, help="폴링 최대 대기 시간(초)")

    sync_p = sub.add_parser("sync", help="Chat Completions (동기)")
    sync_p.add_argument("task", help="질문 또는 단순 태스크")
    sync_p.add_argument("--system", default=None, help="시스템 프롬프트")

    args = parser.parse_args()

    if args.mode == "run":
        sys.exit(run_mode(args.task, args.conversation, args.timeout))
    elif args.mode == "sync":
        sys.exit(sync_mode(args.task, args.system))


if __name__ == "__main__":
    main()
