#!/bin/bash
# MSO Skill Pack — install symlinks into ~/.{claude,codex}/skills/ and ~/.skill-modules/
# Targets: CLAUDE_CODE (default), CODEX, ALL
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_MODULES_SRC="$REPO_DIR/.skill-modules"
ORCHESTRATION_SRC="$REPO_DIR/skills/mso-orchestration"
MODULES_DST="${HOME}/.skill-modules"

# Parse args
TARGETS=()
for arg in "$@"; do
    case "$arg" in
        --codex)      TARGETS+=(codex) ;;
        --all)        TARGETS+=(claude codex) ;;
        *)            ;;
    esac
done
[[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=(claude)

echo "MSO Skill Pack Install"
echo "  Targets : ${TARGETS[*]}"
echo ""

link_target() {
    local src="$1" dst="$2" label="$3"
    if [ -L "$dst" ]; then
        echo "  SKIP  $label  (symlink already exists)"
    elif [ -e "$dst" ]; then
        echo "  SKIP  $label  (path exists — remove manually to re-link)"
    else
        ln -s "$src" "$dst"
        echo "  LINK  $label"
    fi
}

# 1) ~/.skill-modules/mso-skills → .skill-modules/
mkdir -p "$MODULES_DST"
link_target "$SKILL_MODULES_SRC" "$MODULES_DST/mso-skills" "~/.skill-modules/mso-skills"

echo ""

# 2) orchestration skill → each target
for target in "${TARGETS[@]}"; do
    SKILLS_DST="${HOME}/.${target}/skills"
    mkdir -p "$SKILLS_DST"
    echo "  [$target]"
    link_target "$ORCHESTRATION_SRC" "$SKILLS_DST/mso-orchestration" "mso-orchestration"
done

echo ""
echo "Done. Sub-skills are available at ~/.skill-modules/mso-skills/"
echo "Tip: run with --codex or --all to also install for Codex."
