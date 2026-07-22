#!/usr/bin/env bash
# commit-work-memory.sh  (mso-work-memory)
# work-memory 변경분(auditlog, 수동 worklog, track/insight)을 커밋한다. 항상 exit 0 (non-blocking).
#
# ── 존재 이유 ────────────────────────────────────────────────────────────
# auditlog 는 PostToolUse(Bash|Edit|Write) 에서 append 된다. 따라서 에이전트가
# `git commit` 을 Bash 로 실행하면 그 커밋 행위 자체가 다시 auditlog 를 남겨
# 트리가 영구히 dirty 해진다 — 손으로는 절대 못 끊는 루프. 커밋을 "훅" 안에서
# 하면 그것은 Tool 호출이 아니라 PostToolUse 를 재트리거하지 않으므로, 커밋이
# 새 로그를 남기지 않는다. 즉 "로그 저장 → (훅)커밋 → 커밋은 로그 안 남김".
#
# ── 배치 ────────────────────────────────────────────────────────────────
# Stop / PreCompact 에서 호출한다. Stop hook 은 worklog 를 생성하지 않는다.
# worklog 는 workflow TTL node 실행을 명시할 수 있을 때 수동으로 남긴다.
#
# ── 경계 ────────────────────────────────────────────────────────────────
#  - 커밋 대상은 WORKMEM_DIR 경로뿐 — 코드/문서 변경은 절대 자동 커밋하지 않는다.
#  - push 는 하지 않는다 (원격 반영은 수동/별도 정책).
#  - git repo 가 아니거나 변경이 없으면 조용히 종료.
#
# 환경변수:
#   WORKMEM_DIR         work-memory 루트 (미설정 시 <root>/agent-context/work-memory)
#   CLAUDE_PROJECT_DIR / CODEX_PROJECT_DIR / PROJECT_DIR  프로젝트 루트
#   MSO_WM_AUTOCOMMIT=0 으로 비활성화 가능 (기본 활성).
set -uo pipefail

[ "${MSO_WM_AUTOCOMMIT:-1}" = "0" ] && exit 0

ROOT="${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-${PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}}"
WM="${WORKMEM_DIR:-$ROOT/agent-context/work-memory}"

[ -d "$WM" ] || exit 0

# work-memory가 프로젝트 루트와 다른 중첩 저장소에 있을 수 있다. 이 경우
# 루트 저장소에는 해당 경로가 gitlink/비추적 경로로만 보이므로, 실제 소유
# 저장소를 기준으로 stage/commit 해야 한다.
WM_REPO=$(git -C "$WM" rev-parse --show-toplevel 2>/dev/null) || exit 0
git -C "$WM_REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# work-memory 경로를 repo 루트 상대 pathspec 으로 변환 (절대경로 박지 않음).
REL=$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$WM" "$WM_REPO" 2>/dev/null) || REL="work-memory"

git -C "$WM_REPO" add -- "$REL" 2>/dev/null || exit 0
if ! git -C "$WM_REPO" diff --cached --quiet -- "$REL" 2>/dev/null; then
  git -C "$WM_REPO" commit -q -m "chore(work-memory): auto log trail [hook]" -- "$REL" 2>/dev/null || true
fi
exit 0
