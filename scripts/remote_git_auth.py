#!/usr/bin/env python3
"""Select a private remote Git authentication path without handling secret values."""

from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import urlsplit


class AuthenticationError(ValueError):
    """Raised when a remote Git authentication transition is invalid."""


SCP_SSH_URL = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:.+$")


def remote_scheme(value: str) -> str:
    """Return the supported URL scheme while rejecting embedded credentials."""
    parsed = urlsplit(value)
    if parsed.scheme == "https":
        if not parsed.hostname or not parsed.path.strip("/") or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise AuthenticationError("HTTPS Git URL에는 host와 repository path만 포함해야 합니다")
        return "https"
    if parsed.scheme == "ssh":
        if not parsed.hostname or parsed.password or not parsed.path or parsed.query or parsed.fragment:
            raise AuthenticationError("SSH Git URL이 올바르지 않습니다")
        return "ssh"
    if SCP_SSH_URL.fullmatch(value):
        return "ssh"
    raise AuthenticationError("HTTPS 또는 SSH Git URL이 필요합니다")


AUTH_METHODS = {
    "https": {
        "existing_git_auth": "현재 환경에 구성된 Git 인증 사용",
        "demo_credential_file": "데모용 local credential file 경로 제공",
        "alternate_source": "local checkout 또는 source archive로 제공",
    },
    "ssh": {
        "ssh_agent": "현재 환경의 SSH agent 또는 SSH key 사용",
        "alternate_source": "local checkout 또는 source archive로 제공",
    },
}


def authentication_options(url: str) -> dict[str, object]:
    """Return the exact follow-up choices appropriate for the remote protocol."""
    scheme = remote_scheme(url)
    prompt = "원격 Git 저장소에 인증이 필요합니다. 인증값을 대화에 입력하지 말고 접근 방식을 선택해 주세요."
    if scheme == "ssh":
        prompt = "SSH 원격 Git 저장소에 인증이 필요합니다. 인증값을 대화에 입력하지 말고 접근 방식을 선택해 주세요."
    return {
        "state": "awaiting_authentication_method",
        "remote_scheme": scheme,
        "next_prompt": prompt,
        "auth_methods": [
            {"id": method_id, "label": label}
            for method_id, label in AUTH_METHODS[scheme].items()
        ],
    }


def accept_authentication_method(url: str, method: str) -> dict[str, str]:
    """Advance only to the next safe action; do not receive secrets in this flow."""
    scheme = remote_scheme(url)
    if method not in AUTH_METHODS[scheme]:
        raise AuthenticationError(f"{scheme.upper()} URL에서 지원하지 않는 인증 방식입니다")
    if method == "demo_credential_file":
        return {
            "state": "awaiting_credential_file",
            "remote_scheme": scheme,
            "auth_method": method,
            "next_prompt": "데모용 Git 인증 파일의 Local path를 알려주세요. 파일 내용이나 Access Token은 대화에 입력하지 마세요.",
        }
    if method == "alternate_source":
        return {
            "state": "awaiting_source_method",
            "remote_scheme": scheme,
            "auth_method": method,
            "next_prompt": "분석 대상 애플리케이션 소스 코드 제공 방식을 알려주세요.",
        }
    return {
        "state": "retry_plain_clone",
        "remote_scheme": scheme,
        "auth_method": method,
        "next_action": "plain_remote_git_clone",
    }


def emit(value: dict[str, object]) -> int:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="원격 Git URL 프로토콜별 인증 상태 전이를 결정합니다.")
    subparsers = parser.add_subparsers(dest="action", required=True)
    select = subparsers.add_parser("select")
    select.add_argument("--url", required=True)
    accept = subparsers.add_parser("accept")
    accept.add_argument("--url", required=True)
    accept.add_argument("--auth-method", required=True)
    args = parser.parse_args()
    try:
        if args.action == "select":
            return emit(authentication_options(args.url))
        return emit(accept_authentication_method(args.url, args.auth_method))
    except AuthenticationError as error:
        print(f"실패: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
