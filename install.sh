#!/bin/bash
# MSO Skill Pack — install skills as symlinks into ~/.claude/skills/
# Default: minimal (orchestration skill only)
# Full:    ./install.sh --full
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$REPO_DIR/skills"
SKILLS_DST="${HOME}/.claude/skills"

FULL=false
for arg in "$@"; do
    [[ "$arg" == "--full" ]] && FULL=true
done

mkdir -p "$SKILLS_DST"

echo "MSO Skill Pack Install ($( $FULL && echo 'full' || echo 'minimal — orchestration only' ))"
echo "  Source : $SKILLS_SRC"
echo "  Target : $SKILLS_DST"
echo ""

installed=0
skipped=0

for skill_dir in "$SKILLS_SRC"/*/; do
    skill_name="$(basename "$skill_dir")"
    [[ "$skill_name" == _* || "$skill_name" == .* ]] && continue

    # minimal mode: only install *-orchestration skills
    if ! $FULL && [[ "$skill_name" != *"-orchestration" ]]; then
        continue
    fi

    target="$SKILLS_DST/$skill_name"

    if [ -L "$target" ]; then
        echo "  SKIP  $skill_name  (symlink already exists)"
        ((skipped++)) || true
    elif [ -d "$target" ]; then
        echo "  SKIP  $skill_name  (directory exists — remove manually to re-link)"
        ((skipped++)) || true
    else
        ln -s "$skill_dir" "$target"
        echo "  LINK  $skill_name"
        ((installed++)) || true
    fi
done

echo ""
echo "Done: $installed linked, $skipped skipped."
if ! $FULL; then
    echo "Tip: run './install.sh --full' to install all individual skills."
fi
