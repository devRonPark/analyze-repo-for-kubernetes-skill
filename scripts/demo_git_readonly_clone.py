#!/usr/bin/env python3
"""Clone one HTTPS repository with a demo credential file without logging its token."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class CredentialError(ValueError):
    """Raised when a demo credential file cannot be used safely."""


@dataclass(frozen=True)
class Credential:
    repository_url: str
    username: str
    access_token: str


def normalize_https_url(value: str) -> tuple[str, str, str]:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise CredentialError("HTTPS repository URL without embedded credentials is required")
    path = parsed.path.rstrip("/")
    if not path or parsed.query or parsed.fragment:
        raise CredentialError("repository URL must identify one repository without query or fragment")
    host = parsed.hostname.lower()
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return ("https", host, path)


def require_private_regular_file(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise CredentialError("credential file does not exist") from error
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise CredentialError("credential file must be a regular non-symlink file")
    if os.name != "nt":
        if info.st_uid != os.getuid():
            raise CredentialError("credential file must be owned by the current user")
        if info.st_mode & 0o077:
            raise CredentialError("credential file must not be readable by group or others")


def load_credential(path: Path, requested_url: str | None = None) -> Credential:
    require_private_regular_file(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CredentialError("credential file must contain valid JSON") from error
    if not isinstance(value, dict) or value.get("version") != 1:
        raise CredentialError("credential file must use version 1")
    fields = ("repository_url", "username", "access_token")
    if any(not isinstance(value.get(field), str) or not value[field] for field in fields):
        raise CredentialError("credential file is missing a required value")
    configured_url = value["repository_url"]
    configured_origin = normalize_https_url(configured_url)
    if requested_url is not None and configured_origin != normalize_https_url(requested_url):
        raise CredentialError("credential file is not scoped to the requested repository URL")
    return Credential(configured_url, value["username"], value["access_token"])


def read_git_request() -> dict[str, str]:
    request: dict[str, str] = {}
    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line:
            break
        key, separator, value = line.partition("=")
        if not separator:
            raise CredentialError("invalid Git credential request")
        request[key] = value
    return request


def credential_for_git_request(path: Path, request: dict[str, str]) -> Credential:
    protocol = request.get("protocol")
    host = request.get("host")
    request_path = request.get("path", "").rstrip("/")
    if protocol != "https" or not host or not request_path:
        raise CredentialError("Git request must identify one HTTPS repository path")
    requested_url = f"https://{host}/{request_path.lstrip('/')}"
    return load_credential(path, requested_url)


def handle_get(path: Path) -> int:
    try:
        credential = credential_for_git_request(path, read_git_request())
    except CredentialError:
        return 1
    sys.stdout.write(f"username={credential.username}\npassword={credential.access_token}\n\n")
    return 0


def helper_command(credential_path: Path) -> str:
    command = [sys.executable, str(Path(__file__).resolve()), "get", "--credential-file", str(credential_path.resolve())]
    return "!" + " ".join(shlex.quote(part) for part in command)


def clone_readonly(url: str, credential_path: Path, destination: Path, revision: str | None) -> int:
    load_credential(credential_path, url)
    if destination.exists():
        raise CredentialError("destination must not already exist")
    command = [
        "git",
        "-c",
        "credential.useHttpPath=true",
        "-c",
        f"credential.helper={helper_command(credential_path)}",
        "clone",
        "--no-checkout",
        url,
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise CredentialError("read-only Git clone failed; verify repository access and the credential scope")
    if revision:
        result = subprocess.run(
            ["git", "-C", str(destination), "checkout", "--detach", revision],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise CredentialError("requested revision could not be checked out")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only HTTPS Git clone with a demo credential file")
    subparsers = parser.add_subparsers(dest="action", required=True)
    get = subparsers.add_parser("get")
    get.add_argument("--credential-file", required=True, type=Path)
    get.add_argument("git_action", nargs="?")
    clone = subparsers.add_parser("clone")
    clone.add_argument("--url", required=True)
    clone.add_argument("--credential-file", required=True, type=Path)
    clone.add_argument("--destination", required=True, type=Path)
    clone.add_argument("--revision")
    args = parser.parse_args()
    if args.action == "get":
        if args.git_action not in (None, "get"):
            return 1
        return handle_get(args.credential_file)
    try:
        return clone_readonly(args.url, args.credential_file, args.destination, args.revision)
    except CredentialError as error:
        print(f"실패: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
