#!/bin/bash
# mso-agent-audit-log: SessionStart hook
# 최신 워크로그 3개를 세션 시작 시 컨텍스트에 주입한다

if [ -z "$WORKLOG_DIR" ]; then
  CANDIDATE="${PWD}/00.agent_log/logs"
  [ -d "$CANDIDATE" ] || exit 0
  WORKLOG_DIR="$CANDIDATE"
fi

LATEST_LOGS=$(ls -t "${WORKLOG_DIR}"/worklog-*.md 2>/dev/null | head -3)

[ -z "$LATEST_LOGS" ] && exit 0

CONTEXT="[이전 세션 워크로그 — 최근 3개]\n\n"
while IFS= read -r logfile; do
  DATE_LABEL=$(basename "$logfile" .md | sed 's/worklog-//')
  CONTENT=$(head -80 "$logfile" 2>/dev/null)
  CONTEXT+="### ${DATE_LABEL}\n${CONTENT}\n\n---\n\n"
done <<< "$LATEST_LOGS"

jq -n --arg ctx "$CONTEXT" \
  '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$ctx}}'
