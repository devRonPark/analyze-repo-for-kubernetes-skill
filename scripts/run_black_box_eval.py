#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import normalize_report
import validate_regression


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a black-box repository report regression eval.")
    parser.add_argument("--repo", type=Path, required=True, help="Fixture repository root")
    parser.add_argument("--expected", type=Path, required=True, help="Reviewed expected normalized snapshot")
    parser.add_argument("--report", type=Path, help="Generated Markdown report to validate and compare")
    parser.add_argument("--output", type=Path, help="Write machine-readable eval result JSON")
    parser.add_argument("--model", default="unavailable", help="Model identifier recorded as metadata")
    parser.add_argument("--runtime", default="", help="Runtime identifier recorded as metadata")
    parser.add_argument("--mode", choices=["summary", "detailed"], default="summary")
    parser.add_argument("--skill-mode", choices=["skill-on", "skill-off", "unspecified"], default="unspecified")
    parser.add_argument("--prompt", default="", help="Prompt shared by comparable eval runs")
    parser.add_argument("--repository-revision", default="unavailable", help="Repository revision shared by comparable eval runs")
    parser.add_argument("--runtime-options", default="{}", help="JSON runtime options shared by comparable eval runs")
    parser.add_argument("--tool-permissions", default="unavailable", help="Tool permission profile shared by comparable eval runs")
    parser.add_argument("--live-command", help="Opt-in command that emits a Markdown report on stdout")
    parser.add_argument("--allow-live-runtime", action="store_true", help="Allow live runtime execution")
    args = parser.parse_args()

    if args.live_command and not args.allow_live_runtime:
        parser.error("--live-command requires --allow-live-runtime")
    if args.report and args.live_command:
        parser.error("--report and --live-command are mutually exclusive")
    if not args.report and not args.live_command:
        parser.error("one of --report or --live-command is required")

    report_text, runtime = _obtain_report(args)
    report_path = args.report
    if report_path is None:
        report_path = (args.output or Path("black-box-eval-result.json")).with_suffix(".md")
        report_path.write_text(report_text, encoding="utf-8")

    report_validation = validate_regression.validate_report(report_path, args.repo, args.mode)
    expected_payload = json.loads(args.expected.read_text(encoding="utf-8"))
    normalized = normalize_report.normalize_markdown(report_text)
    differences = (
        validate_regression.validate_black_box_expected_schema(expected_payload)
        or validate_regression.compare_normalized(normalized, expected_payload)
    )
    validation_errors: list[str] = []
    if report_validation.returncode != 0:
        validation_errors.append(report_validation.stdout + report_validation.stderr)

    result_payload: dict[str, Any] = {
        "metadata": {
            "model": args.model,
            "runtime": args.runtime or runtime,
            "skill_mode": args.skill_mode,
            "prompt": args.prompt,
            "repository_revision": args.repository_revision,
            "runtime_options": _parse_runtime_options(args.runtime_options),
            "tool_permissions": args.tool_permissions,
            "skill_commit": _skill_commit(),
            "fixture_repository": str(args.repo),
        },
        "report_validation": {
            "passed": report_validation.returncode == 0,
            "errors": validation_errors,
        },
        "normalized_actual": normalized,
        "expected": expected_payload.get("expected", {}),
        "comparison": {
            "passed": not differences and report_validation.returncode == 0,
            "differences": differences,
        },
    }

    output = json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if result_payload["comparison"]["passed"]:
        return 0
    for error in validation_errors:
        print(error, end="", file=sys.stderr)
    for difference in differences:
        print(f"실패: {difference}", file=sys.stderr)
    return 1


def _obtain_report(args: argparse.Namespace) -> tuple[str, str]:
    if args.report:
        return args.report.read_text(encoding="utf-8"), "fixture-report"

    command = shlex.split(args.live_command)
    env = os.environ.copy()
    env["ANALYZE_REPO_FOR_KUBERNETES_SKILL_MODE"] = args.skill_mode
    env["ANALYZE_REPO_FOR_KUBERNETES_PROMPT"] = args.prompt
    env["ANALYZE_REPO_FOR_KUBERNETES_REPOSITORY_REVISION"] = args.repository_revision
    env["ANALYZE_REPO_FOR_KUBERNETES_RUNTIME_OPTIONS"] = args.runtime_options
    env["ANALYZE_REPO_FOR_KUBERNETES_TOOL_PERMISSIONS"] = args.tool_permissions
    completed = subprocess.run(
        command,
        cwd=args.repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print(completed.stdout, end="")
        print(completed.stderr, end="", file=sys.stderr)
        raise SystemExit(completed.returncode)
    return completed.stdout, "live-command"


def _parse_runtime_options(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _skill_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return "unavailable"
    return completed.stdout.strip()


if __name__ == "__main__":
    sys.exit(main())
