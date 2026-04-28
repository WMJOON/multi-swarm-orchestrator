#!/bin/bash
# MSO Skill Pack — install skills as symlinks into ~/.claude/skills/
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$REPO_DIR/skills"
SKILLS_DST="${HOME}/.claude/skills"

mkdir -p "$SKILLS_DST"

echo "MSO Skill Pack Install"
echo "  Source : $SKILLS_SRC"
echo "  Target : $SKILLS_DST"
echo ""

installed=0
skipped=0

for skill_dir in "$SKILLS_SRC"/*/; do
    skill_name="$(basename "$skill_dir")"
    [[ "$skill_name" == _* || "$skill_name" == .* ]] && continue

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
