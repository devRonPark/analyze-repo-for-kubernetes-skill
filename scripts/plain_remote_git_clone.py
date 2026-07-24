#!/usr/bin/env python3
"""Clone a public remote Git repository without injecting credentials."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


class CloneError(ValueError):
    """Raised when a public remote clone cannot be started safely."""


SCP_SSH_URL = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:.+$")


def validate_remote_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme == "https":
        if not parsed.hostname or not parsed.path.strip("/") or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise CloneError("HTTPS Git URL에는 host와 repository path만 포함해야 합니다")
        return "https"
    if parsed.scheme == "ssh":
        if not parsed.hostname or parsed.password or not parsed.path or parsed.query or parsed.fragment:
            raise CloneError("SSH Git URL이 올바르지 않습니다")
        return "ssh"
    if SCP_SSH_URL.fullmatch(value):
        return "ssh"
    raise CloneError("HTTPS 또는 SSH Git URL이 필요합니다")


def plain_clone_command(url: str, destination: Path) -> list[str]:
    validate_remote_url(url)
    return ["git", "clone", "--quiet", url, str(destination)]


def git_output(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise CloneError("clone된 repository의 revision을 확인할 수 없습니다")
    return result.stdout.strip()


def clone_plain(url: str, destination: Path, revision: str | None) -> dict[str, str]:
    scheme = validate_remote_url(url)
    if destination.exists():
        raise CloneError("destination은 존재하지 않는 disposable directory여야 합니다")
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(plain_clone_command(url, destination), capture_output=True, text=True, check=False, env=environment)
    if result.returncode != 0:
        raise CloneError("public read-only Git clone에 실패했습니다; URL, 네트워크 또는 접근 권한을 확인하세요")
    if revision:
        result = subprocess.run(["git", "-C", str(destination), "checkout", "--detach", revision], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise CloneError("요청한 revision을 checkout할 수 없습니다")
    commit = git_output(destination, "rev-parse", "HEAD")
    branch_result = subprocess.run(["git", "-C", str(destination), "symbolic-ref", "--quiet", "--short", "HEAD"], capture_output=True, text=True, check=False)
    resolved_revision = f"{branch_result.stdout.strip()}@{commit}" if branch_result.returncode == 0 else commit
    return {
        "state": "resolved",
        "source_method": "remote_git",
        "target_type": "Remote Git URL",
        "remote_scheme": scheme,
        "resolved_target": str(destination.resolve()),
        "revision": resolved_revision,
        "subdirectory": ".",
        "access_method": "read-only plain remote clone",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="credential 없이 public 원격 Git 저장소를 clone합니다.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--revision")
    args = parser.parse_args()
    try:
        print(json.dumps(clone_plain(args.url, args.destination, args.revision), ensure_ascii=False, sort_keys=True))
        return 0
    except CloneError as error:
        print(f"실패: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
