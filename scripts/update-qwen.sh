#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ ! -d "$SKILL_ROOT/.git" ]; then
  echo "오류: $SKILL_ROOT 는 Git 체크아웃이 아닙니다." >&2
  exit 1
fi

if [ -n "$(git -C "$SKILL_ROOT" status --porcelain)" ]; then
  echo "오류: 로컬 변경 사항이 있습니다. 업데이트 전에 commit 또는 stash 하세요." >&2
  git -C "$SKILL_ROOT" status --short
  exit 1
fi

git -C "$SKILL_ROOT" pull --ff-only
python3 "$SKILL_ROOT/scripts/validate_skill.py" "$SKILL_ROOT"
python3 -m unittest discover -s "$SKILL_ROOT/tests" -p 'test_*.py' -v
bash "$SKILL_ROOT/scripts/install-qwen.sh"

echo "Qwen 스킬 업데이트 완료"
