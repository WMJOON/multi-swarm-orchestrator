#!/bin/bash
# MSO v0.13.1 — install skill symlinks for Claude, Codex, and Gemini.
# Usage: bash install.sh [--codex] [--codex-legacy] [--gemini] [--all] [--venv]
#   --venv : create a Python venv OUTSIDE the repo ($MSO_VENV, default ~/.mso/venv) and install requirements*.txt into it.
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
MAKE_VENV=0
for arg in "$@"; do
  case "$arg" in
    --venv) MAKE_VENV=1 ;;
    --codex) TARGETS+=(agents) ;;
    --codex-legacy) TARGETS+=(codex) ;;
    --gemini) TARGETS+=(gemini/antigravity) ;;
    --all) TARGETS+=(claude agents gemini/antigravity) ;;
  esac
done
[[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=(claude)

echo "MSO v0.13.1 Install"
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

if [[ "$MAKE_VENV" -eq 1 ]]; then
  VENV_DIR="${MSO_VENV:-$HOME/.mso/venv}"
  echo "[venv] $VENV_DIR"
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    mkdir -p "$(dirname "$VENV_DIR")"
    python3 -m venv "$VENV_DIR"
  fi
  "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
  "$VENV_DIR/bin/python" -m pip install --quiet -r "$REPO_DIR/requirements.txt" -r "$REPO_DIR/requirements-langgraph.txt"
  echo "  READY   $VENV_DIR/bin/python  (use it to run compile_workflow.py and generated graph.py)"
  echo ""
fi

echo "Done."
echo "Tip: --codex uses Codex's shared ~/.agents/skills location."
echo "     Use --codex-legacy only when an older setup explicitly requires ~/.codex/skills."
