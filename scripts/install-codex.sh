#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_ROOT="${1:-$HOME/.agents/skills}"
TARGET_DIR="$TARGET_ROOT/analyze-repo-for-kubernetes"
if [[ -n "${CODEX_CONFIG_DIR:-}" ]]; then
  CODEX_CONFIG_DIR="$CODEX_CONFIG_DIR"
elif [[ -n "${CODEX_HOME:-}" ]]; then
  CODEX_CONFIG_DIR="$CODEX_HOME"
elif [[ -n "${USERPROFILE:-}" && -d "$USERPROFILE/.codex" ]]; then
  # WSL-launched Codex may use the Windows profile instead of the POSIX HOME.
  CODEX_CONFIG_DIR="$USERPROFILE/.codex"
else
  CODEX_CONFIG_DIR="$HOME/.codex"
fi
CODEX_CONFIG_FILE="$CODEX_CONFIG_DIR/config.toml"
MANAGED_BEGIN="# BEGIN analyze-repo-for-kubernetes target gate"
MANAGED_END="# END analyze-repo-for-kubernetes target gate"

remove_managed_hook() {
  local source_file="$1"
  local output_file="$2"
  if [[ -f "$source_file" ]]; then
    awk -v begin="$MANAGED_BEGIN" -v end="$MANAGED_END" '
      $0 == begin { skip = 1; next }
      $0 == end { skip = 0; next }
      !skip { print }
    ' "$source_file" > "$output_file"
  else
    : > "$output_file"
  fi
}

install_hook() {
  if [[ "${CODEX_SKIP_HOOK:-}" == "1" ]]; then
    echo "Codex hook 등록을 건너뜁니다 (CODEX_SKIP_HOOK=1)."
    return
  fi

  if ! command -v codex >/dev/null 2>&1; then
    echo "실패: Codex hook을 등록하려면 codex CLI가 필요합니다." >&2
    exit 1
  fi
  if ! codex features list 2>/dev/null | awk '$1 == "hooks" && $2 == "stable" && $3 == "true" { found = 1 } END { exit !found }'; then
    echo "실패: stable hooks 기능이 활성화된 Codex CLI가 필요합니다." >&2
    exit 1
  fi

  mkdir -p "$CODEX_CONFIG_DIR"
  local config_tmp
  local config_backup
  local config_existed=0
  config_tmp="$(mktemp "$CODEX_CONFIG_DIR/.config.toml.XXXXXX")"
  config_backup="$(mktemp "$CODEX_CONFIG_DIR/.config.toml.backup.XXXXXX")"
  if [[ -f "$CODEX_CONFIG_FILE" ]]; then
    cp "$CODEX_CONFIG_FILE" "$config_backup"
    config_existed=1
  fi
  remove_managed_hook "$CODEX_CONFIG_FILE" "$config_tmp"
  {
    printf '\n%s\n' "$MANAGED_BEGIN"
    printf '[[hooks.PreToolUse]]\n'
    printf 'matcher = ".*"\n'
    printf '[[hooks.PreToolUse.hooks]]\n'
    printf 'type = "command"\n'
    printf 'command = "python3 %s/scripts/codex_target_gate_hook.py"\n' "$TARGET_DIR"
    printf 'timeout = 2\n'
    printf 'statusMessage = "Kubernetes 분석 대상 확인 중"\n'
    printf '\n[[hooks.UserPromptSubmit]]\n'
    printf '[[hooks.UserPromptSubmit.hooks]]\n'
    printf 'type = "command"\n'
    printf 'command = "python3 %s/scripts/codex_target_gate_hook.py"\n' "$TARGET_DIR"
    printf 'timeout = 2\n'
    printf 'statusMessage = "Kubernetes 분석 대상 확인 중"\n'
    printf '%s\n' "$MANAGED_END"
  } >> "$config_tmp"

  mv "$config_tmp" "$CODEX_CONFIG_FILE"
  local validation_log
  validation_log="$(mktemp "$CODEX_CONFIG_DIR/.hook-validation.XXXXXX")"
  if ! codex --strict-config --version >"$validation_log" 2>&1; then
    if [[ "$config_existed" == "1" ]]; then
      mv "$config_backup" "$CODEX_CONFIG_FILE"
    else
      rm -f "$CODEX_CONFIG_FILE" "$config_backup"
    fi
    echo "실패: Codex hook 설정 검증에 실패했습니다. 기존 config.toml을 복구했습니다." >&2
    sed -n '1,120p' "$validation_log" >&2
    rm -f "$validation_log"
    exit 1
  fi
  rm -f "$validation_log"
  rm -f "$config_backup"
  echo "Codex PreToolUse hook을 등록했습니다: $CODEX_CONFIG_FILE"
}

mkdir -p "$TARGET_ROOT"
rm -rf "$TARGET_DIR"
cp -R "$SOURCE_DIR" "$TARGET_DIR"
install_hook

echo "설치 완료: $TARGET_DIR"
echo "스킬이 자동으로 표시되지 않으면 Codex를 다시 시작하세요."
