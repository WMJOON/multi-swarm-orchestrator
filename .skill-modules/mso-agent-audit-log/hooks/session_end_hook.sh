#!/bin/bash
# mso-agent-audit-log: SessionEnd hook
# 세션 종료 시 최종 워크로그 기록을 촉구한다

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
  '{"hookSpecificOutput":{"hookEventName":"SessionEnd","additionalContext":"[워크로그 점검 — 세션 종료] 세션이 종료됩니다. 이번 세션에서 실질적인 파일 변경 작업이 있었다면 CLAUDE.md 워크로그 템플릿에 따라 \($wl)에 기록하세요. 단순 질의응답은 생략 가능합니다."}}'
