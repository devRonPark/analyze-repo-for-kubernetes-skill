#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILLS_DIR="${QWEN_SKILLS_DIR:-$HOME/.qwen/skills}"
TARGET="$SKILLS_DIR/analyze-repo-for-kubernetes"

if [ ! -f "$SKILL_ROOT/SKILL.md" ]; then
  echo "ERROR: SKILL.md not found at $SKILL_ROOT" >&2
  exit 1
fi

mkdir -p "$SKILLS_DIR"

if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
  rm -rf "$TARGET"
fi

ln -s "$SKILL_ROOT" "$TARGET"
python3 "$SKILL_ROOT/scripts/validate_skill.py" "$SKILL_ROOT"

echo "QWEN_SKILL_INSTALL_OK"
echo "Source: $SKILL_ROOT"
echo "Installed: $TARGET"
echo "Restart Qwen Code, then run /skills."
