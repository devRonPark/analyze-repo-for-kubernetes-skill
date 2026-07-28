#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

if ! git -C "$PLUGIN_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "오류: $PLUGIN_ROOT 는 Git 체크아웃이 아닙니다." >&2
  exit 1
fi

if [ -n "$(git -C "$PLUGIN_ROOT" status --porcelain)" ]; then
  echo "오류: 로컬 변경 사항이 있습니다. 업데이트 전에 commit 또는 stash 하세요." >&2
  git -C "$PLUGIN_ROOT" status --short
  exit 1
fi

git -C "$PLUGIN_ROOT" pull --ff-only
python3 "$PLUGIN_ROOT/scripts/validate_plugin_package.py" "$PLUGIN_ROOT"
python3 -m unittest discover -s "$PLUGIN_ROOT/tests" -p 'test_*.py' -v
bash "$PLUGIN_ROOT/scripts/install-qwen.sh"

echo "Qwen 스킬 업데이트 완료"
