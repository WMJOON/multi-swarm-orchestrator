#!/usr/bin/env bash
# stop-check.sh — throttled Stop hook reminder.
#
# Stop hooks can fire after every assistant turn. To avoid repeated reminder
# noise, this script prints once, writes a tiny local state marker, and skips
# the immediately following Stop invocation while clearing that marker.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-${PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}"
STATE_DIR="$ROOT/.claude/state"
STATE_FILE="$STATE_DIR/stop-check.state"

mkdir -p "$STATE_DIR" 2>/dev/null || exit 0

if [ -f "$STATE_FILE" ]; then
  rm -f "$STATE_FILE" 2>/dev/null || true
  exit 0
fi

printf 'stop:%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >"$STATE_FILE" 2>/dev/null || true

printf '\n\033[1;33m=== MSO session boundary check ===\033[0m\n'
printf '  1. If a workflow TTL node execution is explicit, record worklog manually.\n'
printf '  2. If this turn changed durable behavior, consider AD/IN/TS.\n'
printf '  3. Before release promotion, verify repository-test first.\n\n'
