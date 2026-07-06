#!/usr/bin/env bash
# mso-hermes-bridge/scripts/setup-with-hermes.sh
# MSO repository init + Hermes setup in one command.
#
# Usage:
#   bash skills/mso-hermes-bridge/scripts/setup-with-hermes.sh <project-root> [--provider claude|codex] [--worthy-paths "..."]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILLS_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
PROJECT_ROOT="${1:-.}"
shift || true

echo "[MSO+Hermes] 프로젝트: $PROJECT_ROOT"

# 1. MSO hook
REPO_SETUP="$SKILLS_ROOT/mso-repository-setup/scripts/init.py"
if [[ ! -f "$REPO_SETUP" ]]; then
    echo "[ERROR] mso-repository-setup/scripts/init.py 없음" >&2; exit 1
fi
python3 "$REPO_SETUP" --hook "$PROJECT_ROOT" "$@"

# 2. Hermes setup
bash "$SKILL_DIR/hooks/hermes-repo-setup.sh" --root "$PROJECT_ROOT"

echo ""
echo "완료. 다음: hermes gateway && bash .hermes/bridge.sh '태스크'"
