#!/usr/bin/env bash
# release-context.sh  (mso-work-memory v0.7.0)
# SessionStart 에서 현재 릴리스 버전 + 유효성 상태를 컨텍스트로 주입한다 (항상 exit 0).
#
# 무엇을 주입하나 — wm_release.py context 의 derived view:
#   current 릴리스 (version/RN id/released_at),
#   invalidated(active) 교훈 목록 (이 릴리스 체계에서 더 이상 동작하지 않는 UD/AD/TS/PT/PR),
#   재유효 후보 (target RN 이 롤백된 invalidated-by — 재검토 필요).
# 프로젝트에 release-note(RN) entry 가 하나도 없으면 아무것도 출력하지 않는다
# (RN 미사용 프로젝트에 잡음 금지).
#
# ── 전달 의미론 ─────────────────────────────────────────────────────────
# plain stdout 이 모델 컨텍스트에 도달하는 건 SessionStart(+UserPromptSubmit)뿐이다
# (work-memory-check.sh 와 동일 근거). startup 을 포함한 SessionStart 전 matcher 에
# 등록한다 — 릴리스 상태는 세션 최초 시작 시점에 가장 가치가 크다.
set -uo pipefail

HOOK_EVENT=""
if [ ! -t 0 ]; then
  HOOK_EVENT=$(cat 2>/dev/null | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("hook_event_name", ""))
except Exception:
    print("")
' 2>/dev/null || true)
fi

case "$HOOK_EVENT" in
  SessionStart|"") : ;;
  *) exit 0 ;;
esac

ROOT="${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-${PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}}}"
cd "$ROOT" 2>/dev/null || exit 0

WORKMEM="${WORKMEM_DIR:-$ROOT/agent-context/work-memory}"
[ -d "$WORKMEM" ] || exit 0

# wm_release.py 탐색: copy-form 배포(같은 디렉토리) 우선, 스킬 레이아웃(../scripts) 폴백
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WM_RELEASE=""
for cand in "$SELF_DIR/wm_release.py" "$SELF_DIR/../scripts/wm_release.py"; do
  if [ -f "$cand" ]; then WM_RELEASE="$cand"; break; fi
done
[ -n "$WM_RELEASE" ] || exit 0

WORKMEM_DIR="$WORKMEM" python3 "$WM_RELEASE" context 2>/dev/null || true
exit 0
