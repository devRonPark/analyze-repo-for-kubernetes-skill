#!/usr/bin/env python3
"""Opt-in black-box check for Codex CLI target intake behavior."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import re

SOURCE_METHOD_QUESTION = "소스를 어떻게 제공하시겠어요?"
SOURCE_METHOD_TERMS = ("Repository URL", "Local directory path", "Source archive")
OLD_SINGLE_TARGET_QUESTION = "분석할 Git URL, Local path 또는 Source archive를 알려 주세요."
DISCOVERY_COMMAND = re.compile(r"(?:^|[\s;&|])(?:rg|grep|find|fd|ls|tree|git)(?:\s|$)")


def main() -> int:
    if os.environ.get("CODEX_INTEGRATION") != "1":
        print("건너뜀: 실제 Codex CLI 검증은 CODEX_INTEGRATION=1에서만 실행합니다.")
        return 0
    codex = shutil.which("codex")
    if not codex:
        print("실패: codex CLI를 찾을 수 없습니다.")
        return 1

    with tempfile.TemporaryDirectory(prefix="codex-intake-") as workspace:
        command = [codex, "exec"]
        if os.environ.get("CODEX_BYPASS_HOOK_TRUST") == "1":
            command.append("--dangerously-bypass-hook-trust")
        command.extend(
            [
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--json",
                "-C",
                workspace,
                "/analyze-repo-for-kubernetes",
            ]
        )
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        return result.returncode

    events = []
    for line in result.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if OLD_SINGLE_TARGET_QUESTION in result.stdout:
        print("실패: Target 없는 호출이 폐기된 단일 target 질문을 사용했습니다.")
        return 1
    if SOURCE_METHOD_QUESTION not in result.stdout or any(
        term not in result.stdout for term in SOURCE_METHOD_TERMS
    ):
        print("실패: Target 없는 호출은 source 제공 방식을 묻는 AskUserQuestion을 출력해야 합니다.")
        return 1

    completed_commands = [
        event.get("item", {}).get("command", "")
        for event in events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") == "command_execution"
        and event.get("item", {}).get("status") == "completed"
    ]
    if any(DISCOVERY_COMMAND.search(command) for command in completed_commands):
        print("실패: Target 없는 호출에서 repository discovery command가 완료되었습니다.")
        return 1

    completed_tool_names = [
        event.get("item", {}).get("name", "")
        for event in events
        if event.get("type") == "item.completed"
    ]
    if any("web" in name.lower() for name in completed_tool_names):
        print("실패: Target 없는 호출에서 web discovery tool이 완료되었습니다.")
        return 1

    print("성공: Codex CLI Target intake gate가 repository discovery 없이 source 제공 방식 질문으로 종료되었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
