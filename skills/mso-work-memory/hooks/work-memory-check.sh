#!/usr/bin/env bash
# work-memory-check.sh  (mso-work-memory)
# 비차단 기록 판단 넛지 (항상 exit 0).
#
# MSO 약점 보완: auditlog/worklog 는 자동 로깅이지만, "track-record/insight-record
# entry 를 언제 남길지"에 대한 판단 트리거가 없었다. 이 훅이 그 넛지를 제공한다.
#
# ── 전달 의미론 (중요) ──────────────────────────────────────────────────
# Provider별 훅 stdout 의미론이 다르므로 work-memory-check 는 컨텍스트 도달이
# 확인된 SessionStart(compact/resume) 에서만 plain stdout 으로 넛지를 전달한다.
# Stop / PreCompact / SessionEnd 에서는 출력이 사용자에게 잡음처럼 보이거나
# 모델에 도달하지 않을 수 있으므로 조용히 종료한다.
#
# ── 판단 ────────────────────────────────────────────────────────────────
#  (1)  track 넛지 — "결정 가치 있는" 변경이 WM 최신 기록보다 앞서면 UD/AD/IN/TS 권유.
#  (1b) IN/TS 넛지 — fix/revert 성격 커밋이 WM 최신 기록 이후 있으면 IN+TS 권유.
#  (2)  insight 넛지 — 종결된 TS 뒤 EP(회고)가 없으면 회고 권유.
#  (4)  세션 회고 — 미커밋 소스 변경이 남아 있으면 세션 통째 IN/TS 점검 권유.
#       [SessionStart 전용] — Stop(매 턴)에 두면 기능 작업 도중에도 반복 나그가 된다.
#
# 환경변수:
#   WM_WORTHY_PATHS  공백 구분 경로 목록. 프로젝트가 "결정 가치 있는" 경로를 지정.
#   WORKMEM_DIR      work-memory 루트 (미설정 시 agent-context/work-memory, repo-relative)
#   CLAUDE_PROJECT_DIR  Claude 프로젝트 루트
#   CODEX_PROJECT_DIR   Codex 프로젝트 루트
#   PROJECT_DIR         provider wrapper 가 넘긴 프로젝트 루트
set -uo pipefail

# stdin payload 파싱 (파이프일 때만 읽어 수동 실행 차단 방지).
# python3 로 파싱 — BSD/GNU sed 차이(예: \| 교대 미지원)에 의존하지 않기 위함.
HOOK_EVENT=""
STOP_ACTIVE=""
if [ ! -t 0 ]; then
  _parsed=$(cat 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
print(d.get("hook_event_name", ""))
print("true" if d.get("stop_hook_active") else "false")
' 2>/dev/null || true)
  HOOK_EVENT=$(printf '%s\n' "$_parsed" | sed -n '1p')
  STOP_ACTIVE=$(printf '%s\n' "$_parsed" | sed -n '2p')
fi

# 출력이 모델에 도달하지 않거나 잡음이 되는 이벤트는 일찍 종료한다.
case "$HOOK_EVENT" in
  SessionStart|"") : ;;
  *) exit 0 ;;
esac

# Stop 루프 방지 필드는 Claude 계열 입력 호환용으로만 유지한다.
[ "$STOP_ACTIVE" = "true" ] && exit 0

ROOT="${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-${PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}}}"
cd "$ROOT" 2>/dev/null || exit 0

# WORKMEM_DIR 가 절대경로면 repo-relative 로 변환 (git log/status 는 상대경로 필요)
WM_DEFAULT="agent-context/work-memory"
if [ -n "${WORKMEM_DIR:-}" ]; then
  case "$WORKMEM_DIR" in
    /*) WM="${WORKMEM_DIR#$ROOT/}" ;;   # 절대 → 상대
    *)  WM="$WORKMEM_DIR" ;;
  esac
else
  WM="$WM_DEFAULT"
fi
[ -d "$WM" ] || exit 0

# 결정 가치 있는 경로. work-memory 자체와 worklog 는 제외 (자동 스냅샷 오탐 방지).
WORTHY_PATHS="${WM_WORTHY_PATHS:-agent-context/workflow agent-context/index .claude .gitmodules CLAUDE.md}"

# 넛지 메시지를 모은다 (이벤트별로 한 번에 전달).
MSGS=""
add_msg() { MSGS="${MSGS:+$MSGS$'\n\n'}$1"; }

# ── (1) track-record 넛지 ──────────────────────────────────────────────
worthy_commit=$(git log -1 --format=%ct -- $WORTHY_PATHS 2>/dev/null || echo 0)
wm_commit=$(git log -1 --format=%ct -- "$WM" 2>/dev/null || echo 0)
worthy_commit="${worthy_commit:-0}"; wm_commit="${wm_commit:-0}"

worthy_dirty=$(git status --porcelain -- $WORTHY_PATHS 2>/dev/null | grep -c . || true)
wm_dirty=$(git status --porcelain -- "$WM" 2>/dev/null | grep -c . || true)
worthy_dirty="${worthy_dirty:-0}"; wm_dirty="${wm_dirty:-0}"

track_remind=0
if [ "$worthy_commit" -gt "$wm_commit" ] && [ "$wm_dirty" -eq 0 ]; then
  track_remind=1
fi
if [ "$worthy_dirty" -gt 0 ] && [ "$wm_dirty" -eq 0 ]; then
  track_remind=1
fi

if [ "$track_remind" -eq 1 ]; then
  add_msg "[work-memory] 결정 가치 있는 변경이 $WM 의 최신 기록보다 앞서 있습니다. 이번 세션의 의사결정을 UD/AD/IN/TS 로 기록하세요 — 스키마: $WM/schema.yaml, 도구: wm_node.py."
fi

# ── (1b) IN/TS 넛지 ────────────────────────────────────────────────────
# UD 는 사용자 발화 트리거가 있어 잘 남지만, IN/TS 는 에이전트 내부 작업에서만
# 촉발돼 누락되기 쉽다. 버그 수정은 WORTHY_PATHS 밖 평범한 소스에서도 나므로,
# track 넛지(track_remind)와 독립적으로 fix/revert 커밋(WM 최신 기록 이후)을 본다.
# 신호원: 커밋 메시지(의도 판별 가능). working-tree 는 파일명만 보여 의도 불명 → 제외.
wm_commit_iso=$(git log -1 --format=%cI -- "$WM" 2>/dev/null || true)
since_arg=""
[ -n "$wm_commit_iso" ] && since_arg="--since=$wm_commit_iso"
fix_commits=$(git log $since_arg --regexp-ignore-case \
  --grep='^fix' --grep='^revert' --grep='bug' --grep='regression' --grep='회귀' --grep='버그' \
  --format=%h 2>/dev/null | grep -c . || true)
fix_commits="${fix_commits:-0}"
# IN/TS 디렉토리에 working-tree 대기분이 있으면 이미 기록 중 → 생략
# aggregate <type>.jsonl (v1.2.0) + 구버전 per-entry 디렉토리 둘 다 pathspec 으로 (호환)
ts_dirty=$(git status --porcelain -- \
  "$WM/track-record/trouble-shooting.jsonl" "$WM/track-record/issue-note.jsonl" \
  "$WM/track-record/trouble-shooting" "$WM/track-record/issue-note" 2>/dev/null | grep -c . || true)
ts_dirty="${ts_dirty:-0}"

if [ "$fix_commits" -gt 0 ] && [ "$ts_dirty" -eq 0 ]; then
  add_msg "[work-memory] fix/revert 성격의 커밋이 $WM 최신 기록 이후 있는데 issue-note(IN)/trouble-shooting(TS) 기록이 없습니다. 같은 턴에 발견+해결했더라도 IN+TS 를 함께 회고로 남기세요 (TS 단독 금지 — IN 으로 원인을 잇습니다). 회고 기록은 늦어도 정상입니다."
fi

# ── (4) 세션 회고 점검 — SessionStart(compact/resume 직후) 전용 ─────────
# 미커밋 작업의 의도(버그/기능)는 git 으로 알 수 없어 Stop(매 턴)에 두면 나그가 된다.
# 대신 세션 경계(컴팩트/재개 직후, 드물게 1회)에서 회고 행동으로 점검한다.
# SessionStart 의 plain stdout 은 모델 컨텍스트로 주입되므로 실제 도달한다.
if [ "$HOOK_EVENT" = "SessionStart" ]; then
  src_dirty=$(git status --porcelain 2>/dev/null | grep -v "$WM" | grep -c . || true)
  src_dirty="${src_dirty:-0}"
  if [ "$src_dirty" -gt 0 ] && [ "$ts_dirty" -eq 0 ]; then
    add_msg "[work-memory] (세션 회고) 커밋 전 소스 변경이 남아 있습니다. 직전 세션을 통틀어 막힌 시도·디버깅·버그 수정이 있었다면 issue-note(IN)+trouble-shooting(TS) 로 회고 기록하세요 — 단순 기능 추가/리팩터뿐이면 건너뜁니다."
  fi
fi

# ── (2) insight-record 넛지 ────────────────────────────────────────────
# 종결된 TS 이후 EP 회고가 없으면 권유 (회고는 작성 단계가 길어 git 시각 대신 mtime).
# aggregate <type>.jsonl (v1.2.0) 우선, 구버전 per-entry 파일도 함께 (mtime 비교)
newest_ts=$(ls -t "$WM"/track-record/trouble-shooting.jsonl "$WM"/track-record/trouble-shooting/TS-*.jsonl 2>/dev/null | head -1)
newest_ep=$(ls -t "$WM"/insight-record/episode.jsonl "$WM"/insight-record/episodes/EP-*.jsonl 2>/dev/null | head -1)

if [ -n "$newest_ts" ] && { [ -z "$newest_ep" ] || [ "$newest_ts" -nt "$newest_ep" ]; }; then
  add_msg "[work-memory] 종결된 trouble-shooting(TS) 이후 회고(EP)가 없습니다. 사건이 일단락됐다면 episode 로 회고하세요 — EP 가 누적되면 pattern(PT) → principle(PR) 로 추상화할 수 있습니다."
fi

# ── 전달 ────────────────────────────────────────────────────────────────
[ -z "$MSGS" ] && exit 0

# SessionStart(또는 수동 실행): plain stdout 이 주입되거나 디버그로 표시된다.
printf '%s\n' "$MSGS"

exit 0
