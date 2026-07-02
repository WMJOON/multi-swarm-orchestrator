#!/usr/bin/env bash
# workflow-check.sh (mso-workflow-design)
# Non-blocking guardrail for workflow TTL ABox (SSOT-of-record).
#
# Runs validate_abox.py on agent-context/workflow/*.abox.ttl after
# workflow-sensitive changes, then regenerates observability views via
# mso-graph-observability's observe_graph.py. Validation (design gate) runs
# first; observation is projection-only and never judges.
#
# It warns by default and exits non-zero only when MSO_WORKFLOW_CHECK_STRICT=1.
#
# Environment:
#   PROJECT_DIR / CODEX_PROJECT_DIR / CLAUDE_PROJECT_DIR  project root
#   WORKFLOW_DIR                 optional workflow dir (default agent-context/workflow)
#   MSO_WORKFLOW_VALIDATE_TOOL   optional validate_abox.py path
#   MSO_OBSERVE_TOOL             optional observe_graph.py path
#   MSO_WORKFLOW_CHECK_STRICT=1  fail on validation error
#   MSO_WORKFLOW_CHECK_NO_OBSERVE=1  skip observability regeneration
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
  SessionStart|PostToolUse|"") : ;;
  *) exit 0 ;;
esac

ROOT="${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-${PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}}}"
[ -n "$ROOT" ] || exit 0
cd "$ROOT" 2>/dev/null || exit 0

if [ -n "${WORKFLOW_DIR:-}" ]; then
  case "$WORKFLOW_DIR" in
    /*) WF_DIR="$WORKFLOW_DIR" ;;
    *) WF_DIR="$ROOT/$WORKFLOW_DIR" ;;
  esac
else
  WF_DIR="$ROOT/agent-context/workflow"
fi
[ -d "$WF_DIR" ] || exit 0

# No abox → nothing to validate (migration is a manual step).
ls "$WF_DIR"/*.abox.ttl >/dev/null 2>&1 || exit 0

find_tool() {
  # $1 = env override path, $2 = skill name, $3 = script relpath
  if [ -n "$1" ] && [ -f "$1" ]; then
    printf '%s\n' "$1"
    return 0
  fi
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
  for candidate in \
    "$script_dir/../scripts/$3" \
    "$ROOT/skills/$2/scripts/$3" \
    "$HOME/.claude/skills/$2/scripts/$3" \
    "$HOME/.codex/skills/$2/scripts/$3" \
    "$HOME/.agents/skills/$2/scripts/$3"
  do
    if [ -f "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

VALIDATE_TOOL="$(find_tool "${MSO_WORKFLOW_VALIDATE_TOOL:-}" "mso-workflow-design" "validate_abox.py" || true)"
[ -n "$VALIDATE_TOOL" ] || exit 0

# Avoid repeated hook noise when there is no workflow-sensitive activity.
# Manual execution still runs because HOOK_EVENT is empty.
if [ -n "$HOOK_EVENT" ]; then
  dirty_count=$(git status --porcelain -- "$WF_DIR" 2>/dev/null | grep -c . || true)
  [ "${dirty_count:-0}" -eq 0 ] && exit 0
fi

validate_out="$(python3 "$VALIDATE_TOOL" "$WF_DIR" 2>&1)"
validate_status=$?

if [ "$validate_status" -ne 0 ]; then
  cat <<EOF
[workflow-check] workflow TTL ABox validation failed.

Run:
  python3 "$VALIDATE_TOOL" "$WF_DIR"

--- validate_abox ---
$validate_out
EOF
  [ "${MSO_WORKFLOW_CHECK_STRICT:-0}" = "1" ] && exit 1
  exit 0
fi

# Validation passed — materialize property-chain derivations (v0.8.0, ROADMAP §5).
if [ "${MSO_WORKFLOW_CHECK_NO_MATERIALIZE:-0}" != "1" ]; then
  MATERIALIZE_TOOL="$(find_tool "${MSO_MATERIALIZE_TOOL:-}" "mso-workflow-design" "materialize_v07.py" || true)"
  if [ -n "$MATERIALIZE_TOOL" ]; then
    materialize_out="$(python3 "$MATERIALIZE_TOOL" "$WF_DIR" 2>&1)" || {
      echo "[workflow-check] materialize_v07.py failed (non-blocking):"
      echo "$materialize_out"
    }
  fi
fi

# Trust report (v0.10.0, ROADMAP §8·§9) — 계산 전용, SSOT 비저장 (D-25).
if [ "${MSO_WORKFLOW_CHECK_NO_TRUST:-0}" != "1" ]; then
  TRUST_TOOL="$(find_tool "${MSO_TRUST_TOOL:-}" "mso-workflow-design" "trust_v07.py" || true)"
  if [ -n "$TRUST_TOOL" ]; then
    trust_out="$(python3 "$TRUST_TOOL" "$WF_DIR" --report "$ROOT/agent-context/observability/trust-report.md" 2>&1)" || {
      echo "[workflow-check] trust_v07.py failed (non-blocking):"
      echo "$trust_out"
    }
  fi
fi

# Regenerate observability projections (projection only).
if [ "${MSO_WORKFLOW_CHECK_NO_OBSERVE:-0}" != "1" ]; then
  OBSERVE_TOOL="$(find_tool "${MSO_OBSERVE_TOOL:-}" "mso-graph-observability" "observe_graph.py" || true)"
  if [ -n "$OBSERVE_TOOL" ]; then
    observe_out="$(python3 "$OBSERVE_TOOL" --root "$ROOT" 2>&1)" || {
      echo "[workflow-check] observe_graph.py failed (non-blocking):"
      echo "$observe_out"
    }
  fi
fi

exit 0
