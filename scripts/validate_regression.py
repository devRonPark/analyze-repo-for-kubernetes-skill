#!/usr/bin/env python3
"""고정된 실제 출력 핵심 필드의 결정성을 검증한다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


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


def main() -> int:
    parser = argparse.ArgumentParser(description="고정된 Skill 출력 회귀 fixture를 검증합니다.")
    parser.add_argument("fixture", type=Path, help="expected.json fixture 경로")
    args = parser.parse_args()

    try:
        payload = json.loads(args.fixture.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"실패: fixture를 읽을 수 없습니다: {error}")
        return 1

    comparison_fields = payload.get("comparison_fields")
    if set(comparison_fields or []) != REQUIRED_FIELDS:
        print("실패: comparison_fields는 배포 대상·의존성·제외 항목·기동 정의·설계 입력 상태를 정확히 포함해야 합니다")
        return 1
    if payload.get("allowed_differences") != []:
        print("실패: 이 fixture는 핵심 필드의 반복 결과 차이를 허용하지 않습니다")
        return 1

    errors: list[str] = []
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
    if errors:
        for error in errors:
            print(f"실패: {error}")
        return 1
    print(f"성공: {len(cases)}개 고정 Skill 출력 fixture의 핵심 필드가 일관됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
