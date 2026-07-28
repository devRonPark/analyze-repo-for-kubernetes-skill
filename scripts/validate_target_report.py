#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import bounded_subprocess

MAX_DIAGNOSTIC_CHARS = 32_768
VALIDATION_TIMEOUT_SECONDS = 30


def load_target(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(
            f"target.json을 읽을 수 없습니다: {path}: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"target.json이 유효한 JSON이 아닙니다: {path}: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ValueError("target.json root는 object여야 합니다")
    return payload


def canonical_report_path(target: dict[str, Any]) -> Path:
    artifacts = target.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("target.json에 artifacts object가 없습니다")
    report = artifacts.get("report")
    if not isinstance(report, str) or not report:
        raise ValueError("target.json artifacts.report가 없습니다")
    return Path(report)


def validation_command(
    target: dict[str, Any], report: Path
) -> list[str]:
    validation = target.get("validation")
    if not isinstance(validation, dict):
        raise ValueError("target.json에 validation object가 없습니다")
    command = validation.get("report_command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
    ):
        raise ValueError(
            "target.json validation.report_command는 비어 있지 않은 "
            "string array여야 합니다"
        )
    canonical = report.expanduser().resolve(strict=False)
    command_paths = {
        Path(item).expanduser().resolve(strict=False) for item in command
    }
    if canonical not in command_paths:
        raise ValueError(
            "validation.report_command가 artifacts.report를 검증하지 "
            f"않습니다: artifacts.report={report}"
        )
    return list(command)


def alternate_report_files(report: Path) -> tuple[Path, ...]:
    if not report.parent.is_dir():
        return ()
    canonical = report.expanduser().resolve(strict=False)
    return tuple(
        sorted(
            candidate
            for candidate in report.parent.glob("*report*.md")
            if candidate.is_file()
            and candidate.expanduser().resolve(strict=False) != canonical
        )
    )


def _bounded(value: str) -> str:
    if len(value) <= MAX_DIAGNOSTIC_CHARS:
        return value
    return value[:MAX_DIAGNOSTIC_CHARS] + "\n[diagnostics truncated]\n"


def validate(target_json: Path) -> int:
    try:
        target = load_target(target_json)
        report = canonical_report_path(target)
        command = validation_command(target, report)
    except ValueError as error:
        print(f"실패: {error}")
        return 1

    alternates = alternate_report_files(report)
    try:
        completed = bounded_subprocess.run(
            command,
            timeout=VALIDATION_TIMEOUT_SECONDS,
            max_output_bytes=MAX_DIAGNOSTIC_CHARS,
        )
    except OSError as error:
        print(
            "실패: canonical report validator infrastructure failure: "
            f"{type(error).__name__}"
        )
        return 1
    if completed.timed_out:
        print("실패: canonical report validator timeout")
        return 1
    if completed.output_exceeded:
        print("실패: canonical report validator output limit을 초과했습니다")
        return 1

    failed = completed.returncode != 0 or bool(alternates)
    if not failed:
        print(report)
        return 0

    if completed.stdout:
        print(_bounded(completed.stdout), end="")
    if completed.stderr:
        print(_bounded(completed.stderr), end="", file=sys.stderr)
    if completed.returncode != 0:
        print(f"실패: canonical report validation failed: {report}")
    for alternate in alternates:
        print(f"실패: alternate report-like file exists: {alternate}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="target.json의 canonical report만 검증합니다."
    )
    parser.add_argument("target_json", type=Path)
    args = parser.parse_args()
    return validate(args.target_json)


if __name__ == "__main__":
    raise SystemExit(main())
