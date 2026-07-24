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
TARGET_QUESTION = "분석할 Git URL, Local path 또는 Source archive를 알려 주세요."
PURPOSE_QUESTION = "이 분석 결과를 어디에 활용하시나요?"
DISCOVERY_TOKENS = re.compile(
    r"(?:\brg\b|\bgrep\b|\bfind\b|\bfd\b|\bls\b|\btree\b|\bgit\b|\bglob\b|\bweb\b)",
    re.IGNORECASE,
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


def _cache_dir() -> Path:
    configured = os.environ.get("CODEX_TARGET_GATE_CACHE_DIR")
    if configured:
        return Path(configured)
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / SKILL_NAME


def _thread_id(event: dict[str, Any]) -> str:
    return _event_value(event, "thread_id", "threadId", "session_id", "sessionId") or "default"


def _state_path(event: dict[str, Any]) -> Path:
    safe_thread = re.sub(r"[^A-Za-z0-9._-]", "_", _thread_id(event))
    return _cache_dir() / f"{safe_thread}.json"


def _load_state(event: dict[str, Any]) -> dict[str, str]:
    path = _state_path(event)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state(event: dict[str, Any], phase: str) -> None:
    path = _state_path(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"phase": phase}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _has_target(prompt: str) -> bool:
    return any(pattern.search(prompt) for pattern in TARGET_PATTERNS)


def _has_purpose(prompt: str) -> bool:
    return bool(PURPOSE_PATTERNS.search(prompt))


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
    if event_name in {"UserPromptSubmit", "userPromptSubmit"}:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse" if event_name == "" else event_name,
            "permissionDecision": "allow",
        }
    }


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

    if state.get("phase") == "analysis_ready":
        phase = "analysis_ready"
    elif state.get("phase") == "purpose_required":
        phase = "analysis_ready" if _has_purpose(prompt) else "purpose_required"
    elif _has_target(prompt):
        phase = "analysis_ready" if _has_purpose(prompt) else "purpose_required"
    else:
        phase = "target_required"

    _save_state(event, phase)
    if event_name in {"UserPromptSubmit", "userPromptSubmit"}:
        return _allow(event_name)
    if phase == "analysis_ready":
        return _allow(event_name)

    if phase == "target_required":
        if _is_skill_read_only(command):
            return _allow(event_name)
        if command or tool_name:
            return _deny(
                f"{TARGET_QUESTION} Target 확정 전에는 repository discovery tool을 사용할 수 없습니다.",
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
