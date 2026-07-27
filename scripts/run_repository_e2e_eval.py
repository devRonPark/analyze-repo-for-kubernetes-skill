#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import normalize_report
import validate_regression


COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FIXTURE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description="Evaluate full Kubernetes-analysis Skill reports against pinned repository checkouts."
    )
    argument_parser.add_argument("--manifest", type=Path, required=True, help="Pinned repository corpus manifest JSON")
    source = argument_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--report-dir", type=Path, help="Directory containing <fixture-id>.md reports")
    source.add_argument("--live-command", help="Opt-in command that emits one Markdown report to stdout per checkout")
    argument_parser.add_argument("--expectations", type=Path, help="Optional reviewed normalized expectations JSON")
    argument_parser.add_argument("--output", type=Path, help="Write aggregate JSON result to this path")
    argument_parser.add_argument("--mode", choices=["summary", "detailed"], default="summary")
    argument_parser.add_argument("--prompt", default="", help="Prompt metadata passed to the live command")
    argument_parser.add_argument("--model", default="unavailable", help="Model identifier recorded in the result")
    argument_parser.add_argument("--allow-network", action="store_true", help="Allow pinned repository clone operations")
    argument_parser.add_argument("--allow-live-runtime", action="store_true", help="Allow the supplied live command to run")
    argument_parser.add_argument("--timeout-seconds", type=int, default=300, help="Per clone, checkout, or live command timeout")
    return argument_parser


def load_manifest(path: Path) -> list[dict[str, str]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"manifest를 읽을 수 없습니다: {error}") from error
    if not isinstance(raw, dict) or set(raw) != {"fixtures"} or not isinstance(raw["fixtures"], list):
        raise ValueError("manifest는 fixtures 배열만 포함해야 합니다")

    fixtures: list[dict[str, str]] = []
    ids: set[str] = set()
    for index, item in enumerate(raw["fixtures"]):
        if not isinstance(item, dict):
            raise ValueError(f"fixtures[{index}]는 객체여야 합니다")
        fixture = {key: item.get(key) for key in ("id", "upstream", "commit")}
        if not all(isinstance(value, str) for value in fixture.values()):
            raise ValueError(f"fixtures[{index}]에 id, upstream, commit 문자열이 필요합니다")
        identifier = fixture["id"]
        commit = fixture["commit"]
        if not FIXTURE_ID_PATTERN.fullmatch(identifier):
            raise ValueError(f"안전하지 않은 fixture id입니다: {identifier}")
        if identifier in ids:
            raise ValueError(f"중복 fixture id입니다: {identifier}")
        if not COMMIT_PATTERN.fullmatch(commit):
            raise ValueError(f"fixtures[{index}]의 commit은 40자리 소문자 SHA여야 합니다")
        ids.add(identifier)
        fixtures.append({key: str(value) for key, value in fixture.items()})
    if not fixtures:
        raise ValueError("manifest에는 하나 이상의 fixture가 필요합니다")
    return fixtures


def load_expectations(path: Path | None, fixture_ids: set[str]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    if path is None:
        return [], {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"expectations를 읽을 수 없습니다: {error}") from error
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("expectations.schema_version은 1이어야 합니다")
    fields = raw.get("comparison_fields")
    repositories = raw.get("repositories")
    if not isinstance(fields, list) or not fields or not all(isinstance(field, str) for field in fields):
        raise ValueError("expectations.comparison_fields는 비어 있지 않은 문자열 배열이어야 합니다")
    if any(field not in normalize_report.COMPARISON_FIELDS for field in fields):
        raise ValueError("expectations.comparison_fields에 지원하지 않는 정규화 필드가 있습니다")
    if not isinstance(repositories, dict) or set(repositories) != fixture_ids:
        raise ValueError("expectations.repositories는 manifest fixture id와 정확히 일치해야 합니다")
    if any(
        not isinstance(expected, dict) or any(field not in expected for field in fields)
        for expected in repositories.values()
    ):
        raise ValueError("각 expectation에는 모든 comparison_fields가 필요합니다")
    return fields, repositories


def run_process(command: list[str], timeout_seconds: int, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    process_environment = os.environ.copy()
    process_environment["GIT_TERMINAL_PROMPT"] = "0"
    if env:
        process_environment.update(env)
    return subprocess.run(
        command,
        cwd=cwd,
        env=process_environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )


def clone_checkout(fixture: dict[str, str], destination: Path, timeout_seconds: int) -> tuple[bool, str]:
    clone = run_process(
        ["git", "clone", "--filter=blob:none", "--no-checkout", fixture["upstream"], str(destination)],
        timeout_seconds,
    )
    if clone.returncode != 0:
        return False, f"clone 실패 (exit {clone.returncode})"
    checkout = run_process(
        ["git", "-C", str(destination), "checkout", "--detach", fixture["commit"]],
        timeout_seconds,
    )
    if checkout.returncode != 0:
        return False, f"pinned checkout 실패 (exit {checkout.returncode})"
    revision = run_process(["git", "-C", str(destination), "rev-parse", "HEAD"], timeout_seconds)
    if revision.returncode != 0 or revision.stdout.strip() != fixture["commit"]:
        return False, "checkout revision이 manifest commit과 일치하지 않습니다"
    return True, ""


def report_text_for_fixture(
    fixture: dict[str, str],
    repository: Path,
    args: argparse.Namespace,
) -> tuple[str | None, str, str]:
    if args.report_dir is not None:
        report_path = args.report_dir / f"{fixture['id']}.md"
        try:
            return report_path.read_text(encoding="utf-8"), "report-directory", ""
        except OSError:
            return None, "report-directory", f"report를 찾을 수 없습니다: {report_path.name}"

    command = shlex.split(args.live_command)
    if not command:
        return None, "live-command", "live command가 비어 있습니다"
    completed = run_process(
        command,
        args.timeout_seconds,
        cwd=repository,
        env={
            "ANALYZE_REPO_FOR_KUBERNETES_TARGET": str(repository),
            "ANALYZE_REPO_FOR_KUBERNETES_FIXTURE_ID": fixture["id"],
            "ANALYZE_REPO_FOR_KUBERNETES_REPOSITORY_REVISION": fixture["commit"],
            "ANALYZE_REPO_FOR_KUBERNETES_UPSTREAM": fixture["upstream"],
            "ANALYZE_REPO_FOR_KUBERNETES_REPORT_MODE": args.mode,
            "ANALYZE_REPO_FOR_KUBERNETES_PROMPT": args.prompt,
        },
    )
    if completed.returncode != 0:
        return None, "live-command", f"live command 실패 (exit {completed.returncode})"
    return completed.stdout, "live-command", ""


def working_tree_error(repository: Path, timeout_seconds: int) -> str:
    status = run_process(
        ["git", "-C", str(repository), "status", "--porcelain", "--untracked-files=all"],
        timeout_seconds,
    )
    if status.returncode != 0:
        return "live command 후 checkout 상태를 확인할 수 없습니다"
    if status.stdout:
        return "live command가 분석 대상 checkout을 변경했습니다"
    return ""


def comparison_result(
    actual: dict[str, Any],
    fields: list[str],
    expected: dict[str, Any] | None,
) -> dict[str, Any]:
    if not fields or expected is None:
        return {"performed": False, "passed": True, "differences": []}
    differences = [
        f"{field}: expected {json.dumps(expected[field], ensure_ascii=False, sort_keys=True)}, "
        f"actual {json.dumps(actual.get(field), ensure_ascii=False, sort_keys=True)}"
        for field in fields
        if actual.get(field) != expected[field]
    ]
    return {"performed": True, "passed": not differences, "differences": differences}


def evaluate_fixture(
    fixture: dict[str, str],
    workspace: Path,
    args: argparse.Namespace,
    fields: list[str],
    expectations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    repository = workspace / fixture["id"]
    result: dict[str, Any] = {
        "id": fixture["id"],
        "upstream": fixture["upstream"],
        "commit": fixture["commit"],
        "checkout": {"passed": False, "error": ""},
        "report_validation": {"passed": False, "errors": []},
        "comparison": {"performed": bool(fields), "passed": False, "differences": []},
    }
    try:
        checkout_passed, checkout_error = clone_checkout(fixture, repository, args.timeout_seconds)
    except (OSError, subprocess.TimeoutExpired) as error:
        checkout_passed, checkout_error = False, f"checkout 실행 실패: {type(error).__name__}"
    result["checkout"] = {"passed": checkout_passed, "error": checkout_error}
    if not checkout_passed:
        return result

    try:
        report_text, report_source, report_error = report_text_for_fixture(fixture, repository, args)
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        report_text, report_source, report_error = None, "live-command", f"report 생성 실패: {type(error).__name__}"
    result["report_source"] = report_source
    if report_text is None:
        result["report_validation"] = {"passed": False, "errors": [report_error]}
        return result

    if report_source == "live-command":
        mutation_error = working_tree_error(repository, args.timeout_seconds)
        if mutation_error:
            result["report_validation"] = {"passed": False, "errors": [mutation_error]}
            return result

    report_path = workspace / f"{fixture['id']}.md"
    report_path.write_text(report_text, encoding="utf-8")
    validation = validate_regression.validate_report(report_path, repository, args.mode)
    validation_errors = validation.stdout.splitlines() if validation.returncode != 0 else []
    result["report_validation"] = {"passed": validation.returncode == 0, "errors": validation_errors}
    result["normalized_actual"] = normalize_report.normalize_markdown(report_text)
    result["comparison"] = comparison_result(
        result["normalized_actual"], fields, expectations.get(fixture["id"])
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.allow_network:
        parser().error("--allow-network is required because every evaluation performs a pinned clone")
    if args.live_command and not args.allow_live_runtime:
        parser().error("--live-command requires --allow-live-runtime")
    if args.timeout_seconds < 1:
        parser().error("--timeout-seconds must be positive")

    try:
        fixtures = load_manifest(args.manifest)
        fields, expectations = load_expectations(args.expectations, {fixture["id"] for fixture in fixtures})
    except ValueError as error:
        parser().error(str(error))

    with tempfile.TemporaryDirectory(prefix="repository-e2e-eval-") as temporary_directory:
        workspace = Path(temporary_directory)
        evaluations = [evaluate_fixture(fixture, workspace, args, fields, expectations) for fixture in fixtures]

    passed = [
        item["checkout"]["passed"]
        and item["report_validation"]["passed"]
        and item["comparison"]["passed"]
        for item in evaluations
    ]
    payload = {
        "schema_version": 1,
        "metadata": {
            "manifest": str(args.manifest),
            "mode": args.mode,
            "model": args.model,
            "prompt": args.prompt,
            "report_source": "live-command" if args.live_command else "report-directory",
            "expectations": str(args.expectations) if args.expectations else None,
        },
        "summary": {"total": len(evaluations), "passed": all(passed), "passed_count": sum(passed)},
        "repositories": evaluations,
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
