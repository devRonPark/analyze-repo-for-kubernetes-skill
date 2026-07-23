#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ ! -d "$SKILL_ROOT/.git" ]; then
  echo "ERROR: $SKILL_ROOT is not a Git checkout." >&2
  exit 1
fi

if [ -n "$(git -C "$SKILL_ROOT" status --porcelain)" ]; then
  echo "ERROR: Local changes exist. Commit or stash them before updating." >&2
  git -C "$SKILL_ROOT" status --short
  exit 1
fi

git -C "$SKILL_ROOT" pull --ff-only
python3 "$SKILL_ROOT/scripts/validate_skill.py" "$SKILL_ROOT"
python3 -m unittest discover -s "$SKILL_ROOT/tests" -p 'test_*.py' -v
bash "$SKILL_ROOT/scripts/install-qwen.sh"

echo "QWEN_SKILL_UPDATE_OK"
