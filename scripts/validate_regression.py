#!/usr/bin/env python3
"""고정된 실제 출력 핵심 필드의 결정성을 검증한다."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import normalize_report


REQUIRED_FIELDS = {
    "workload_candidates",
    "workload_kinds",
    "repository_defined_runtime_dependencies",
    "external_runtime_dependencies",
    "excluded_candidates",
    "repository_launch_definitions",
    "target_environment_baseline",
    "design_input_verdict",
}


def validate_static_fixture_schema(payload: dict) -> list[str]:
    comparison_fields = payload.get("comparison_fields")
    errors: list[str] = []
    if set(comparison_fields or []) != REQUIRED_FIELDS:
        errors.append("comparison_fields는 배포 대상·의존성·제외 항목·기동 정의·설계 입력 상태를 정확히 포함해야 합니다")
        return errors
    if payload.get("allowed_differences") != []:
        errors.append("이 fixture는 핵심 필드의 반복 결과 차이를 허용하지 않습니다")

    cases = payload.get("cases", [])
    if len(cases) < 8:
        errors.append("대표 fixture는 최소 8개여야 합니다")
    for case in cases:
        case_id = case.get("id", "<unknown>")
        if not case.get("coverage"):
            errors.append(f"{case_id}: 언어·구조·예외 범주가 없습니다")
        first, second = case.get("first"), case.get("second")
        if not isinstance(first, dict) or not isinstance(second, dict):
            errors.append(f"{case_id}: 반복 출력 쌍이 없습니다")
            continue
        for field in comparison_fields:
            if field not in first or field not in second:
                errors.append(f"{case_id}: 핵심 필드가 없습니다: {field}")
            elif first[field] != second[field]:
                errors.append(f"{case_id}: 반복 출력의 핵심 필드가 다릅니다: {field}")
    return errors


def validate_black_box_expected_schema(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("black-box expected fixture schema_version은 1이어야 합니다")
    comparison_fields = payload.get("comparison_fields")
    if set(comparison_fields or []) != REQUIRED_FIELDS:
        errors.append("comparison_fields는 normalized report 핵심 필드를 정확히 포함해야 합니다")
    expected = payload.get("expected")
    if not isinstance(expected, dict):
        errors.append("expected normalized report object가 없습니다")
        return errors
    for field in comparison_fields or []:
        if field not in expected:
            errors.append(f"expected에 핵심 필드가 없습니다: {field}")
    case = payload.get("case")
    if not isinstance(case, dict):
        errors.append("case metadata가 없습니다")
    else:
        reconciliation = " ".join(case.get("reconciles_closed_dependencies", [])) + " " + case.get("reconciliation", "")
        for issue in ["#22", "#23"]:
            if issue not in reconciliation:
                errors.append(f"closed/not-planned dependency reconciliation이 없습니다: {issue}")
    return errors


def validate_report(report: Path, repo_root: Path, mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "validate_report.py"),
            str(report),
            "--mode",
            mode,
            "--repo-root",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def compare_normalized(actual: dict, expected_payload: dict) -> list[str]:
    differences: list[str] = []
    expected = expected_payload["expected"]
    for field in expected_payload["comparison_fields"]:
        if actual.get(field) != expected.get(field):
            differences.append(
                f"{field}: expected {json.dumps(expected.get(field), ensure_ascii=False, sort_keys=True)}, "
                f"actual {json.dumps(actual.get(field), ensure_ascii=False, sort_keys=True)}"
            )
    return differences


def main() -> int:
    parser = argparse.ArgumentParser(description="고정된 Skill 출력 회귀 fixture를 검증합니다.")
    parser.add_argument("fixture", type=Path, help="expected.json 또는 black_box_expected.json fixture 경로")
    parser.add_argument("--actual-report", type=Path, help="생성된 Markdown report를 normalize해 expected와 비교합니다")
    parser.add_argument("--repo-root", type=Path, help="actual report file:line citation을 검증할 fixture repository root")
    parser.add_argument("--mode", choices=["summary", "detailed"], default="summary")
    args = parser.parse_args()

    try:
        payload = json.loads(args.fixture.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"실패: fixture를 읽을 수 없습니다: {error}")
        return 1

    if "cases" in payload:
        errors = validate_static_fixture_schema(payload)
        success_message = f"성공: {len(payload.get('cases', []))}개 고정 Skill 출력 fixture schema가 유효합니다."
        if args.actual_report:
            errors.append("--actual-report 비교에는 black_box_expected.json fixture를 사용해야 합니다")
    else:
        errors = validate_black_box_expected_schema(payload)
        success_message = "성공: black-box expected fixture schema가 유효합니다."

    if errors:
        for error in errors:
            print(f"실패: {error}")
        return 1

    if args.actual_report:
        if args.repo_root is None:
            print("실패: --actual-report 비교에는 --repo-root가 필요합니다")
            return 1
        report_validation = validate_report(args.actual_report, args.repo_root, args.mode)
        if report_validation.returncode != 0:
            print("실패: validate_report.py가 생성 report를 거부했습니다")
            print(report_validation.stdout, end="")
            print(report_validation.stderr, end="", file=sys.stderr)
            return 1
        actual = normalize_report.normalize_markdown(args.actual_report.read_text(encoding="utf-8"))
        differences = compare_normalized(actual, payload)
        if differences:
            for difference in differences:
                print(f"실패: {difference}")
            return 1
        print("성공: normalized actual report가 black-box expected snapshot과 일치합니다.")
        return 0

    print(success_message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
