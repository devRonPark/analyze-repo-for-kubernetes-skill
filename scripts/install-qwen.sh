#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_ROOT="$PLUGIN_ROOT/skills/analyze-repo-for-kubernetes"
SKILLS_DIR="${QWEN_SKILLS_DIR:-$HOME/.qwen/skills}"
TARGET="$SKILLS_DIR/analyze-repo-for-kubernetes"

if [ ! -f "$SKILL_ROOT/SKILL.md" ]; then
  echo "오류: $SKILL_ROOT 에서 SKILL.md를 찾을 수 없습니다" >&2
  exit 1
fi

python3 "$PLUGIN_ROOT/scripts/validate_plugin_package.py" "$PLUGIN_ROOT"

mkdir -p "$SKILLS_DIR"

if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
  rm -rf "$TARGET"
fi

ln -s "$SKILL_ROOT" "$TARGET"

echo "Qwen 스킬 설치 완료"
echo "Plugin root: $PLUGIN_ROOT"
echo "원본: $SKILL_ROOT"
echo "설치 위치: $TARGET"
echo "Qwen Code를 다시 시작한 뒤 /skills를 실행하세요."
