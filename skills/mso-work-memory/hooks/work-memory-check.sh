#!/usr/bin/env bash
# work-memory-check.sh  (mso-work-memory)
# Stop / PreCompact 시점 호출. 비차단 기록 판단 넛지 (항상 exit 0).
#
# MSO 약점 보완: auditlog/worklog 는 자동 로깅이지만, "track-record/insight-record
# entry 를 언제 남길지"에 대한 판단 트리거가 없었다. 이 훅이 그 넛지를 제공한다.
#
# 두 가지 판단:
#  (1) track-record 넛지 — "결정 가치 있는" 변경이 work-memory 최신 기록보다 앞서면
#      UD/AD/IN/TS 를 남기라고 알림.
#  (2) insight-record 넛지 — 종결된 TS 가 있는데 그 뒤 EP(회고)가 없으면 회고를 권유.
#
# 환경변수:
#   WM_WORTHY_PATHS  공백 구분 경로 목록. 프로젝트가 "결정 가치 있는" 경로를 지정.
#                    (미설정 시 아래 제네릭 기본값)
#   WORKMEM_DIR      work-memory 루트 (미설정 시 agent-context/work-memory, repo-relative)
#   CLAUDE_PROJECT_DIR  프로젝트 루트 (미설정 시 git toplevel)
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
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
# 프로젝트별 커스터마이즈는 WM_WORTHY_PATHS 로. 기본값은 오케스트레이션 레이어.
WORTHY_PATHS="${WM_WORTHY_PATHS:-agent-context/workflow agent-context/index .claude .gitmodules CLAUDE.md}"

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
  echo "[work-memory] 결정 가치 있는 변경이 $WM 의 최신 기록보다 앞서 있습니다. 이번 세션의 의사결정을 UD/AD/IN/TS 로 기록하세요 — 스키마: $WM/schema.yaml, 도구: wm_node.py."
fi

# ── (1b) IN/TS 넛지 ────────────────────────────────────────────────────
# UD 는 사용자 발화 트리거가 있어 잘 남지만, IN/TS 는 에이전트 내부 작업에서만
# 촉발돼 누락되기 쉽다. fix 성격의 커밋/변경이 WM 최신 기록보다 앞서면 별도로 환기.
# (working tree 변경도 포함 — Stop 시점엔 아직 커밋 전일 수 있다.)
wm_commit_iso=$(git log -1 --format=%cI -- "$WM" 2>/dev/null || true)
since_arg=""
[ -n "$wm_commit_iso" ] && since_arg="--since=$wm_commit_iso"
fix_commits=$(git log $since_arg --regexp-ignore-case \
  --grep='^fix' --grep='^revert' --grep='bug' --grep='regression' --grep='회귀' --grep='버그' \
  --format=%h 2>/dev/null | grep -c . || true)
fix_dirty=$(git status --porcelain 2>/dev/null | grep -ciE 'fix|revert' || true)
fix_commits="${fix_commits:-0}"; fix_dirty="${fix_dirty:-0}"
# IN/TS 디렉토리에 working-tree 대기분이 있으면 이미 기록 중 → 생략
ts_dirty=$(git status --porcelain -- "$WM/track-record/trouble-shooting" "$WM/track-record/issue-note" 2>/dev/null | grep -c . || true)
ts_dirty="${ts_dirty:-0}"

if [ "$track_remind" -eq 1 ] && [ "$ts_dirty" -eq 0 ] && { [ "$fix_commits" -gt 0 ] || [ "$fix_dirty" -gt 0 ]; }; then
  echo "[work-memory] fix 성격의 변경이 있었는데 issue-note(IN)/trouble-shooting(TS) 기록이 없습니다. 같은 턴에 발견+해결했더라도 IN+TS 를 함께 회고로 남기세요 (TS 단독 금지 — IN 으로 원인을 잇습니다). 회고 기록은 늦어도 정상입니다."
fi

# ── (2) insight-record 넛지 ────────────────────────────────────────────
# 종결된 TS 이후 EP 회고가 없으면 권유 (회고는 작성 단계가 길어 git 시각 대신 mtime).
newest_ts=$(ls -t "$WM"/track-record/trouble-shooting/TS-*.jsonl 2>/dev/null | head -1)
newest_ep=$(ls -t "$WM"/insight-record/episodes/EP-*.jsonl 2>/dev/null | head -1)

if [ -n "$newest_ts" ] && { [ -z "$newest_ep" ] || [ "$newest_ts" -nt "$newest_ep" ]; }; then
  echo "[work-memory] 종결된 trouble-shooting(TS) 이후 회고(EP)가 없습니다. 사건이 일단락됐다면 episode 로 회고하세요 — EP 가 누적되면 pattern(PT) → principle(PR) 로 추상화할 수 있습니다."
fi

exit 0
