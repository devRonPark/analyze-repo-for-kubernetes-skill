#!/usr/bin/env python3
"""Codex PreToolUse guard for the Kubernetes repository-analysis skill.

The hook intentionally accepts several Codex event-field spellings so package tests can
exercise the contract without coupling the skill to one desktop or CLI transport shape.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SKILL_NAME = "analyze-repo-for-kubernetes"
SOURCE_METHOD_QUESTION = "소스를 어떻게 제공하시겠어요?"
REPOSITORY_URL_QUESTION = "분석할 GitHub 또는 Git repository URL을 입력해 주세요."
LOCAL_PATH_QUESTION = "분석할 local directory path를 입력해 주세요."
SOURCE_ARCHIVE_QUESTION = "분석할 ZIP, tar, tar.gz 또는 tgz archive path를 입력해 주세요."
TARGET_QUESTION = SOURCE_METHOD_QUESTION
PURPOSE_QUESTION = "이 분석 결과를 어디에 활용하시나요?"
DISCOVERY_TOKENS = re.compile(
    r"(?:\brg\b|\bgrep\b|\bfind\b|\bfd\b|\bls\b|\btree\b|\bgit\b|\bglob\b|\bweb\b)",
    re.IGNORECASE,
)
SOURCE_METHOD_PATTERNS = (
    ("repository_url", re.compile(r"(?:Repository URL|GitHub URL|Git URL|repository url|remote repository|원격|저장소 URL)", re.IGNORECASE)),
    ("local_path", re.compile(r"(?:Local directory path|Local path|local directory|local path|로컬|디렉터리|디렉토리)", re.IGNORECASE)),
    ("source_archive", re.compile(r"(?:Source archive|archive|ZIP|tar\.gz|tgz|압축|아카이브)", re.IGNORECASE)),
)
TARGET_PATTERNS = (
    re.compile(r"(?:https?|ssh)://\S+|git@[^\s:]+:[^\s]+", re.IGNORECASE),
    re.compile(r"\S+\.(?:zip|tar|tar\.gz|tgz)\b", re.IGNORECASE),
    re.compile(r"(?:Use\s+)?Local\s+path\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"/(?:analyze-repo-for-kubernetes)\s+(?:\.|/|[A-Za-z]:\\)", re.IGNORECASE),
    re.compile(r"(?:^|\s)(?!/analyze-repo-for-kubernetes\b)(?:~?/|[A-Za-z]:[\\/])\S+", re.IGNORECASE),
    re.compile(r"(?:현재 저장소|현재 workspace|current repository|current workspace)", re.IGNORECASE),
)
PURPOSE_PATTERNS = re.compile(
    r"(?:빠른 구조 파악|Kubernetes 설계 준비|이관 문제점 점검|전체 상세 보고서|기본 분석으로 진행|"
    r"quick structure|Kubernetes design preparation|migration risk|full (?:detailed )?report|"
    r"Kubernetes.*(?:설계|배포|이관)|(?:설계|배포|이관).*Kubernetes|"
    r"Kubernetes.*(?:design|deploy|migration)|(?:design|deploy|migration).*Kubernetes)",
    re.IGNORECASE,
)


def _first_text(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
        for candidate in value.values():
            found = _first_text(candidate, keys)
            if found:
                return found
    elif isinstance(value, list):
        for candidate in value:
            found = _first_text(candidate, keys)
            if found:
                return found
    return ""


def _event_value(event: dict[str, Any], *keys: str) -> str:
    return _first_text(event, tuple(keys))


def _cache_dir_candidates() -> list[Path]:
    configured = os.environ.get("CODEX_TARGET_GATE_CACHE_DIR")
    if configured:
        return [Path(configured)]
    default_cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / SKILL_NAME
    temp_cache = Path(os.environ.get("TMPDIR", "/tmp")) / SKILL_NAME
    return [default_cache, temp_cache]


def _thread_id(event: dict[str, Any]) -> str:
    return _event_value(event, "thread_id", "threadId", "session_id", "sessionId") or "default"


def _state_paths(event: dict[str, Any]) -> list[Path]:
    safe_thread = re.sub(r"[^A-Za-z0-9._-]", "_", _thread_id(event))
    return [cache_dir / f"{safe_thread}.json" for cache_dir in _cache_dir_candidates()]


def _load_state(event: dict[str, Any]) -> dict[str, str]:
    for path in _state_paths(event):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _save_state(event: dict[str, Any], phase: str, source_method: str = "") -> None:
    payload = {"phase": phase}
    if source_method:
        payload["source_method"] = source_method
    for path in _state_paths(event):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            temporary.replace(path)
            return
        except OSError:
            continue


def _has_target(prompt: str) -> bool:
    return any(pattern.search(prompt) for pattern in TARGET_PATTERNS)


def _has_purpose(prompt: str) -> bool:
    return bool(PURPOSE_PATTERNS.search(prompt))


def _source_method(prompt: str) -> str:
    for method, pattern in SOURCE_METHOD_PATTERNS:
        if pattern.search(prompt):
            return method
    return ""


def _target_value_question(source_method: str) -> str:
    if source_method == "repository_url":
        return REPOSITORY_URL_QUESTION
    if source_method == "local_path":
        return LOCAL_PATH_QUESTION
    if source_method == "source_archive":
        return SOURCE_ARCHIVE_QUESTION
    return SOURCE_METHOD_QUESTION


def _command(event: dict[str, Any]) -> str:
    return _event_value(event, "command", "cmd", "input_text", "inputText")


def _tool_name(event: dict[str, Any]) -> str:
    return _event_value(event, "tool_name", "toolName", "tool")


def _references_skill(command: str) -> bool:
    return SKILL_NAME in command and "SKILL.md" in command


def _is_skill_read_only(command: str) -> bool:
    if not _references_skill(command) or DISCOVERY_TOKENS.search(command):
        return False
    return bool(re.fullmatch(r"\s*(?:cat|sed\s+-n\s+['\"]?[^;|&]+['\"]?)\s*", command))


def _is_target_confirmation(command: str) -> bool:
    return bool(
        re.fullmatch(
            r"\s*(?:test\s+-[er]\s+\S+|realpath\s+\S+|git\s+ls-remote\s+\S+|tar\s+-t\S*\s+\S+)\s*",
            command,
        )
    )


def _deny(reason: str, event_name: str = "PreToolUse") -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _allow(event_name: str = "PreToolUse") -> dict[str, Any]:
    return {}


def evaluate_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return a Codex PreToolUse decision without performing repository discovery."""
    event_name = _event_value(event, "hook_event_name", "hookEventName", "event")
    if event_name not in {"", "PreToolUse", "preToolUse", "UserPromptSubmit", "userPromptSubmit"}:
        return _allow(event_name)

    prompt = _event_value(event, "user_prompt", "userPrompt", "prompt", "latest_user_input")
    command = _command(event)
    tool_name = _tool_name(event)
    state = _load_state(event)
    relevant = (
        bool(state)
        or SKILL_NAME in prompt
        or _references_skill(command)
        or (_has_target(prompt) and bool(re.search(r"(?:Kubernetes|k8s|쿠버네티스|분석|analysis)", prompt, re.IGNORECASE)))
    )
    if not relevant:
        return _allow(event_name)

    source_method = state.get("source_method", "")
    selected_source_method = _source_method(prompt)
    if state.get("phase") == "analysis_ready":
        phase = "analysis_ready"
    elif _has_target(prompt):
        phase = "analysis_ready" if _has_purpose(prompt) else "purpose_required"
    elif state.get("phase") == "purpose_required":
        phase = "analysis_ready" if _has_purpose(prompt) else "purpose_required"
    elif state.get("phase") == "target_value_required":
        phase = "target_value_required"
        source_method = source_method or selected_source_method
    elif selected_source_method:
        phase = "target_value_required"
        source_method = selected_source_method
    else:
        phase = "source_method_required"

    _save_state(event, phase, source_method)
    if event_name in {"UserPromptSubmit", "userPromptSubmit"}:
        return _allow(event_name)
    if phase == "analysis_ready":
        return _allow(event_name)

    if phase == "source_method_required":
        if _is_skill_read_only(command):
            return _allow(event_name)
        if command or tool_name:
            return _deny(
                f"{SOURCE_METHOD_QUESTION} Source 제공 방식 확정 전에는 repository discovery tool을 사용할 수 없습니다.",
                event_name,
            )
        return _allow(event_name)

    if phase == "target_value_required":
        if command or tool_name:
            return _deny(
                f"{_target_value_question(source_method)} Target 값 확정 전에는 repository discovery tool을 사용할 수 없습니다.",
                event_name,
            )
        return _allow(event_name)

    if _is_target_confirmation(command):
        return _allow(event_name)
    if command or tool_name:
        return _deny(
            f"{PURPOSE_QUESTION} Target은 확정됐지만 분석 목적이 아직 확정되지 않았습니다.",
            event_name,
        )
    return _allow(event_name)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps(_deny("Codex hook payload를 읽을 수 없습니다."), ensure_ascii=False))
        return 0
    if not isinstance(event, dict):
        print(json.dumps(_deny("Codex hook payload 형식이 올바르지 않습니다."), ensure_ascii=False))
        return 0
    print(json.dumps(evaluate_event(event), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
