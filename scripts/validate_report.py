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
    parser = argparse.ArgumentParser(description="Validate a generated Kubernetes migration report.")
    parser.add_argument("report", help="Generated Markdown report")
    parser.add_argument("--mode", choices=["auto", "summary", "detailed"], default="auto")
    parser.add_argument("--fixture", choices=sorted(FIXTURES), help="Apply fixture-specific checks")
    args = parser.parse_args()

    path = Path(args.report)
    if not path.is_file():
        print(f"FAIL: report not found: {path}")
        return 1

    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    detected = detect_mode(text)
    mode = detected if args.mode == "auto" else args.mode

    if mode is None:
        errors.append("unable to detect report mode from title")
    elif detected is not None and args.mode != "auto" and detected != args.mode:
        errors.append(f"report title indicates {detected} mode, not {args.mode}")

    required_sections = SUMMARY_SECTIONS if mode == "summary" else DETAILED_SECTIONS
    for section in required_sections:
        if section not in text:
            errors.append(f"missing section: {section}")

    if not any(verdict in text for verdict in ["Verdict: Ready", "Verdict: Needs Input", "Verdict: Blocked"]):
        errors.append("missing explicit final verdict")

    if not any(status in text for status in ["Confirmed", "Inferred", "Unknown", "Conflicting"]):
        errors.append("no evidence confidence status found")

    for field in ["Execution Locus", "Application Phase"]:
        if field not in text:
            errors.append(f"missing required field: {field}")

    if args.fixture:
        for term in FIXTURES[args.fixture]:
            if term not in text:
                errors.append(f"fixture expectation not found: {term}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1

    print(f"PASS: report contains the required {mode} assessment structure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
