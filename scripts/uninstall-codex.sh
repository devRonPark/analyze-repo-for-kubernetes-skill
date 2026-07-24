#!/usr/bin/env bash
set -euo pipefail

TARGET_ROOT="${1:-$HOME/.agents/skills}"
TARGET_DIR="$TARGET_ROOT/analyze-repo-for-kubernetes"
CODEX_CONFIG_DIR="${CODEX_CONFIG_DIR:-$HOME/.codex}"
CODEX_CONFIG_FILE="$CODEX_CONFIG_DIR/config.toml"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/analyze-repo-for-kubernetes"
MANAGED_BEGIN="# BEGIN analyze-repo-for-kubernetes target gate"
MANAGED_END="# END analyze-repo-for-kubernetes target gate"

if [[ -f "$CODEX_CONFIG_FILE" ]]; then
  CONFIG_TMP="$(mktemp "$CODEX_CONFIG_DIR/.config.toml.XXXXXX")"
  awk -v begin="$MANAGED_BEGIN" -v end="$MANAGED_END" '
    $0 == begin { skip = 1; next }
    $0 == end { skip = 0; next }
    !skip { print }
  ' "$CODEX_CONFIG_FILE" > "$CONFIG_TMP"
  mv "$CONFIG_TMP" "$CODEX_CONFIG_FILE"
fi

rm -rf "$TARGET_DIR"
rm -rf "$CACHE_DIR"
echo "제거 완료: $TARGET_DIR"
