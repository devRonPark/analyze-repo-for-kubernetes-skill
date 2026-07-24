#!/usr/bin/env python3
"""Resolve source-intake state without inspecting a repository before a target is supplied."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


class IntakeError(ValueError):
    """Raised when a supplied source target cannot be resolved safely."""


SOURCE_METHODS = {
    "remote_git": {
        "label": "원격 Git URL",
        "prompt": "분석할 원격 Git URL을 알려주세요.",
    },
    "local_checkout": {
        "label": "로컬 checkout 경로",
        "prompt": "분석할 애플리케이션 소스의 Local path를 알려주세요.",
    },
    "source_archive": {
        "label": "소스 압축 파일",
        "prompt": "분석할 소스 압축 파일의 Local path를 알려주세요. 지원 형식: .zip, .tar.gz, .tgz",
    },
}


def emit(value: dict[str, str]) -> int:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


def select_source_method(source_method: str) -> dict[str, str]:
    method = SOURCE_METHODS.get(source_method)
    if method is None:
        raise IntakeError("지원하지 않는 source method입니다")
    return {
        "state": "awaiting_target_value",
        "source_method": source_method,
        "source_method_label": method["label"],
        "next_prompt": method["prompt"],
    }


def git_output(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise IntakeError("Local path가 읽기 가능한 Git checkout이 아닙니다")
    return result.stdout.strip()


def resolve_local_checkout(value: str) -> dict[str, str]:
    requested = Path(value).expanduser()
    if requested.is_symlink():
        raise IntakeError("Local path symlink는 분석 대상으로 사용할 수 없습니다")
    try:
        requested = requested.resolve(strict=True)
    except FileNotFoundError as error:
        raise IntakeError("Local path가 존재하지 않습니다") from error
    if not requested.is_dir():
        raise IntakeError("Local path는 디렉터리여야 합니다")
    if not os.access(requested, os.R_OK | os.X_OK):
        raise IntakeError("Local path를 읽을 수 없습니다")

    root = Path(git_output(requested, "rev-parse", "--show-toplevel"))
    root = root.resolve(strict=True)
    try:
        subdirectory = requested.relative_to(root).as_posix() or "."
    except ValueError as error:
        raise IntakeError("Local path가 확인된 Git checkout 밖에 있습니다") from error
    commit = git_output(root, "rev-parse", "HEAD")
    branch_result = subprocess.run(
        ["git", "-C", str(root), "symbolic-ref", "--quiet", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    revision = f"{branch_result.stdout.strip()}@{commit}" if branch_result.returncode == 0 else commit
    return {
        "state": "resolved",
        "source_method": "local_checkout",
        "target_type": "Local path",
        "resolved_target": str(root),
        "revision": revision,
        "subdirectory": subdirectory,
        "access_method": "read-only local checkout",
    }


def accept_source_value(source_method: str, value: str) -> dict[str, str]:
    if source_method == "local_checkout":
        return resolve_local_checkout(value)
    if source_method not in SOURCE_METHODS:
        raise IntakeError("지원하지 않는 source method입니다")
    return {
        "state": "target_supplied",
        "source_method": source_method,
        "target_value": value,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="소스 제공 방식과 local checkout 범위를 결정합니다.")
    subparsers = parser.add_subparsers(dest="action", required=True)
    select = subparsers.add_parser("select")
    select.add_argument("--source-method", required=True, choices=sorted(SOURCE_METHODS))
    accept = subparsers.add_parser("accept")
    accept.add_argument("--source-method", required=True, choices=sorted(SOURCE_METHODS))
    accept.add_argument("--value", required=True)
    args = parser.parse_args()
    try:
        if args.action == "select":
            return emit(select_source_method(args.source_method))
        return emit(accept_source_value(args.source_method, args.value))
    except IntakeError as error:
        print(f"실패: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
