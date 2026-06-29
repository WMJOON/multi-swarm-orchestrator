#!/bin/bash
# MSO v0.5.0 — install symlinks into ~/.{claude,codex,gemini}/skills/
# Usage: bash install.sh [--codex] [--all]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$REPO_DIR/skills"

SKILLS=(
  mso-orchestration
  mso-repository-setup
  mso-scaffold-design
  mso-workflow-design
  mso-graph-observability
  mso-workflow-optimizer
  mso-work-memory
  mso-intent-analytics
  mso-conversation-analytics
)

# Parse args
TARGETS=()
for arg in "$@"; do
  case "$arg" in
    --codex) TARGETS+=(codex) ;;
    --gemini) TARGETS+=(gemini/antigravity) ;;
    --all) TARGETS+=(claude codex gemini/antigravity) ;;
  esac
done
[[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=(claude)

echo "MSO v0.5.0 Install"
echo "  Skills  : ${SKILLS[*]}"
echo "  Targets : ${TARGETS[*]}"
echo ""

link_skill() {
  local src="$1" dst="$2" label="$3"
  if [ -L "$dst" ]; then
    rm "$dst"
    ln -s "$src" "$dst"
    echo "  UPDATE  $label"
  elif [ -e "$dst" ]; then
    echo "  SKIP    $label  (directory exists — remove manually to re-link)"
  else
    ln -s "$src" "$dst"
    echo "  LINK    $label"
  fi
}

for target in "${TARGETS[@]}"; do
  DST_DIR="$HOME/.$target/skills"
  mkdir -p "$DST_DIR"
  echo "[$target]"
  for skill in "${SKILLS[@]}"; do
    link_skill "$SKILLS_SRC/$skill" "$DST_DIR/$skill" "$skill"
  done
  echo ""
done

echo "Done."
echo "Tip: run with --all to install for Claude + Codex + Gemini."
