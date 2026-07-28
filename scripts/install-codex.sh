#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

python3 "$PLUGIN_ROOT/scripts/validate_plugin_package.py" "$PLUGIN_ROOT"

echo "이 저장소는 standalone Skill이 아니라 Codex Plugin입니다."
echo "Codex Plugin 설치는 local marketplace에 이 Plugin root를 등록한 뒤 Plugins Directory에서 진행하세요."
echo "자세한 절차: https://developers.openai.com/plugins/build/plugins"
echo "이 안내 스크립트는 Skill, hook 또는 Codex 설정 파일을 변경하지 않았습니다."
