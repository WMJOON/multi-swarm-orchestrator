#!/bin/bash
# MSO v0.12.1 — install skill symlinks for Claude, Codex, and Gemini.
# Usage: bash install.sh [--codex] [--codex-legacy] [--gemini] [--all]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$REPO_DIR/skills"

SKILLS=(
  mso-orchestration
  mso-repository-setup
  mso-scaffold-design
  mso-workflow-design
  mso-graph-observability
  mso-workflow-observation
  mso-workflow-optimizer
  mso-work-memory
  mso-work-memory-link
  mso-intent-analytics
  mso-conversation-analytics
)

# Parse args
TARGETS=()
for arg in "$@"; do
  case "$arg" in
    --codex) TARGETS+=(agents) ;;
    --codex-legacy) TARGETS+=(codex) ;;
    --gemini) TARGETS+=(gemini/antigravity) ;;
    --all) TARGETS+=(claude agents gemini/antigravity) ;;
  esac
done
[[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=(claude)

echo "MSO v0.10.1 Install"
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

if [[ " ${TARGETS[*]} " == *" agents "* ]]; then
  LEGACY_CODEX_SKILLS=()
  for skill in "${SKILLS[@]}"; do
    legacy_path="$HOME/.codex/skills/$skill"
    if [ -e "$legacy_path" ] || [ -L "$legacy_path" ]; then
      LEGACY_CODEX_SKILLS+=("$skill")
    fi
  done
  if [[ ${#LEGACY_CODEX_SKILLS[@]} -gt 0 ]]; then
    echo "WARNING: legacy ~/.codex/skills entries also exist: ${LEGACY_CODEX_SKILLS[*]}"
    echo "         Codex may discover duplicate skill names. Review and remove only obsolete legacy links."
  fi
fi

echo "Done."
echo "Tip: --codex uses Codex's shared ~/.agents/skills location."
echo "     Use --codex-legacy only when an older setup explicitly requires ~/.codex/skills."
