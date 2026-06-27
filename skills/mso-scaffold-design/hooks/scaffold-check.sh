#!/usr/bin/env bash
# scaffold-check.sh (mso-scaffold-design)
# Non-blocking guardrail for repository directory refinement.
#
# Runs scaffold schema validation and inventory check after scaffold-sensitive
# changes. It warns by default and exits non-zero only when
# MSO_SCAFFOLD_CHECK_STRICT=1.
#
# Environment:
#   PROJECT_DIR / CODEX_PROJECT_DIR / CLAUDE_PROJECT_DIR  project root
#   SCAFFOLD_INDEX          optional index path, repo-relative or absolute
#   MSO_SCAFFOLD_TOOL       optional sf_node.py path
#   MSO_SCAFFOLD_CHECK_STRICT=1  fail on mismatch
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

if [ -n "${SCAFFOLD_INDEX:-}" ]; then
  case "$SCAFFOLD_INDEX" in
    /*) INDEX="$SCAFFOLD_INDEX" ;;
    *) INDEX="$ROOT/$SCAFFOLD_INDEX" ;;
  esac
elif [ -f "$ROOT/agent-context/index/index.yaml" ]; then
  INDEX="$ROOT/agent-context/index/index.yaml"
elif [ -f "$ROOT/index.yaml" ]; then
  INDEX="$ROOT/index.yaml"
else
  exit 0
fi

find_tool() {
  if [ -n "${MSO_SCAFFOLD_TOOL:-}" ] && [ -f "$MSO_SCAFFOLD_TOOL" ]; then
    printf '%s\n' "$MSO_SCAFFOLD_TOOL"
    return 0
  fi

  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
  for candidate in \
    "$script_dir/sf_node.py" \
    "$HOME/.codex/skills/mso-scaffold-design/scripts/sf_node.py" \
    "$HOME/.claude/skills/mso-scaffold-design/scripts/sf_node.py" \
    "$HOME/.agents/skills/mso-scaffold-design/scripts/sf_node.py"
  do
    if [ -f "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

TOOL="$(find_tool || true)"
[ -n "$TOOL" ] || exit 0

# Avoid repeated hook noise when there is no scaffold-sensitive working-tree
# activity. Manual execution still runs because HOOK_EVENT is empty.
if [ -n "$HOOK_EVENT" ]; then
  dirty_count=$(git status --porcelain -- "$INDEX" "$(dirname "$INDEX")" 2>/dev/null | grep -c . || true)
  # Directory moves may not touch index yet, so inspect top-level status too.
  if [ "${dirty_count:-0}" -eq 0 ]; then
    top_dirty=$(git status --porcelain 2>/dev/null | grep -Ev '(^.. agent-context/work-memory/(auditlog|worklog)|^.. agent-context/observability/)' | grep -c . || true)
    [ "${top_dirty:-0}" -eq 0 ] && exit 0
  fi
fi

validate_out="$(python3 "$TOOL" validate "$INDEX" 2>&1)"
validate_status=$?
inventory_out="$(python3 "$TOOL" inventory "$INDEX" 2>&1)"
inventory_status=$?

failed=0
if [ "$validate_status" -ne 0 ] || [ "$inventory_status" -ne 0 ]; then
  failed=1
fi
if printf '%s\n%s\n' "$validate_out" "$inventory_out" | grep -Eq '\[ERROR\]|\[MISSING\]|\[EXTRA\]|ERROR [1-9]'; then
  failed=1
fi

[ "$failed" -eq 0 ] && exit 0

cat <<EOF
[scaffold-check] index SSOT and filesystem may be out of sync.

Run:
  python3 "$TOOL" validate "$INDEX"
  python3 "$TOOL" inventory "$INDEX"

--- validate ---
$validate_out

--- inventory ---
$inventory_out
EOF

[ "${MSO_SCAFFOLD_CHECK_STRICT:-0}" = "1" ] && exit 1
exit 0
