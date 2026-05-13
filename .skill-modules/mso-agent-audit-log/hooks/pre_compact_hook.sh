#!/bin/bash
# mso-agent-audit-log: PreCompact hook
# 컴팩션 직전 — 컨텍스트가 압축되기 전에 워크로그 기록을 촉구한다

DATE=$(date +%Y%m%d)
COOLDOWN="${WORKLOG_COOLDOWN_SEC:-300}"

if [ -z "$WORKLOG_DIR" ]; then
  CANDIDATE="${PWD}/00.agent_log/logs"
  [ -d "$CANDIDATE" ] || exit 0
  WORKLOG_DIR="$CANDIDATE"
fi

WORKLOG="${WORKLOG_DIR}/worklog-${DATE}.md"

MTIME=$(stat -f %m "$WORKLOG" 2>/dev/null || echo 0)
NOW=$(date +%s)
[ $((NOW - MTIME)) -lt "$COOLDOWN" ] && exit 0

jq -n --arg wl "$WORKLOG" \
  '{"hookSpecificOutput":{"hookEventName":"PreCompact","additionalContext":"[워크로그 점검 — 컴팩션 직전] 컨텍스트가 곧 압축됩니다. 현재 세션의 주요 작업 내용을 \($wl)에 기록하세요. 컴팩션 후에는 현재 맥락이 손실될 수 있으므로 지금 기록하는 것이 중요합니다. 단순 질의응답은 생략 가능합니다."}}'
