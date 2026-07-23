#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_ROOT="${1:-$HOME/.agents/skills}"
TARGET_DIR="$TARGET_ROOT/analyze-repo-for-kubernetes"

mkdir -p "$TARGET_ROOT"
rm -rf "$TARGET_DIR"
cp -R "$SOURCE_DIR" "$TARGET_DIR"

echo "Installed: $TARGET_DIR"
echo "Restart Codex if the skill does not appear automatically."
