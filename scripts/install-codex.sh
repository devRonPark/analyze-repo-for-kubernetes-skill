#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_ROOT="${1:-$HOME/.agents/skills}"
TARGET_DIR="$TARGET_ROOT/analyze-repo-for-kubernetes"

mkdir -p "$TARGET_ROOT"
rm -rf "$TARGET_DIR"
cp -R "$SOURCE_DIR" "$TARGET_DIR"

echo "설치 완료: $TARGET_DIR"
echo "스킬이 자동으로 표시되지 않으면 Codex를 다시 시작하세요."
