#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SUMMARY_SECTIONS = [
    "## 1. Scope and Verdict",
    "## 2. Architecture at a Glance",
    "## 3. Component Summary",
    "## 4. Critical Dependency Matrix",
    "## 5. Configuration Timing Highlights",
    "## 6. Kubernetes Mapping Summary",
    "## 7. Risks and Required Inputs",
    "## 8. Evidence Index",
]

DETAILED_SECTIONS = [
    "## 1. Assessment Scope",
    "## 2. Executive Summary",
    "## 3. Component Inventory",
    "## 4. Component Details",
    "## 5. Repository Dependency Matrix",
    "## 6. Repository Dependency Graph",
    "## 8. Kubernetes Migration Risks",
    "## 9. Required Inputs",
    "## 10. Final Readiness Verdict",
]

FIXTURES = {
    "no-dockerfile-monorepo": [
        "frontend", "api", "worker", "shared",
        "Containerization Required", "PostgreSQL", "Redis", "RabbitMQ",
        "8009", "Needs Input", "browser", "build-time",
    ]
}


def detect_mode(text: str) -> str | None:
    if text.lstrip().startswith("# Kubernetes Migration Summary"):
        return "summary"
    if text.lstrip().startswith("# Kubernetes Migration Assessment"):
        return "detailed"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="생성된 Kubernetes 이관 보고서를 검증합니다.")
    parser.add_argument("report", help="생성된 Markdown 보고서")
    parser.add_argument("--mode", choices=["auto", "summary", "detailed"], default="auto")
    parser.add_argument("--fixture", choices=sorted(FIXTURES), help="fixture별 검사를 적용합니다")
    args = parser.parse_args()

    path = Path(args.report)
    if not path.is_file():
        print(f"실패: 보고서를 찾을 수 없습니다: {path}")
        return 1

    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    detected = detect_mode(text)
    mode = detected if args.mode == "auto" else args.mode

    if mode is None:
        errors.append("제목에서 보고서 모드를 감지할 수 없습니다")
    elif detected is not None and args.mode != "auto" and detected != args.mode:
        errors.append(f"보고서 제목은 {detected} 모드를 가리키지만 요청 모드는 {args.mode}입니다")

    required_sections = SUMMARY_SECTIONS if mode == "summary" else DETAILED_SECTIONS
    for section in required_sections:
        if section not in text:
            errors.append(f"섹션이 없습니다: {section}")

    if not any(verdict in text for verdict in ["Verdict: Ready", "Verdict: Needs Input", "Verdict: Blocked"]):
        errors.append("명시적인 최종 판정이 없습니다")

    if not any(status in text for status in ["Confirmed", "Inferred", "Unknown", "Conflicting"]):
        errors.append("근거 신뢰도 상태를 찾을 수 없습니다")

    for field in ["Execution Locus", "Application Phase"]:
        if field not in text:
            errors.append(f"필수 필드가 없습니다: {field}")

    if args.fixture:
        for term in FIXTURES[args.fixture]:
            if term not in text:
                errors.append(f"fixture 기대값을 찾을 수 없습니다: {term}")

    if errors:
        for error in errors:
            print(f"실패: {error}")
        return 1

    print(f"성공: 보고서에 필요한 {mode} 평가 구조가 포함되어 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
