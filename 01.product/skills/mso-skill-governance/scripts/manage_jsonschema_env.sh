#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VENV_DIR="${MSO_JSONSCHEMA_VENV_DIR:-$ROOT_DIR/.venv-jsonschema}"
REQ_FILE="${MSO_JSONSCHEMA_REQUIREMENTS:-$ROOT_DIR/skills/mso-skill-governance/scripts/requirements-jsonschema.txt}"
PY="$VENV_DIR/bin/python3"

usage() {
  cat <<'USAGE'
Usage: manage_jsonschema_env.sh <command> [args]

Commands:
  install   Create local venv and install jsonschema dependency from requirements
  uninstall Remove local venv (dependencies are deleted and can be removed)
  run       Run a command inside the venv (requires install)
  status   Show venv status and key packages
  help     Show this help

Examples:
  ./manage_jsonschema_env.sh install
  ./manage_jsonschema_env.sh run -- python3 -m pip show jsonschema
  ./manage_jsonschema_env.sh run -- python3 skills/mso-skill-governance/scripts/validate_schemas.py --json
USAGE
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  install)
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$REQ_FILE"
    echo "jsonschema env installed: $VENV_DIR"
    "$VENV_DIR/bin/pip" show jsonschema
    ;;

  uninstall)
    if [ -d "$VENV_DIR" ]; then
      rm -rf "$VENV_DIR"
      echo "jsonschema env removed: $VENV_DIR"
    else
      echo "jsonschema env not found: $VENV_DIR"
    fi
    ;;

  run)
    if [ ! -x "$PY" ]; then
      echo "jsonschema env not installed. Run: $0 install" >&2
      exit 1
    fi
    exec "$PY" "$@"
    ;;

  status)
    if [ -x "$PY" ]; then
      echo "jsonschema env: active"
      "$PY" --version
      "$PY" -m pip show jsonschema || true
    else
      echo "jsonschema env: missing"
    fi
    ;;

  help|--help|-h)
    usage
    ;;

  *)
    echo "unknown command: $cmd" >&2
    usage >&2
    exit 1
    ;;
esac
