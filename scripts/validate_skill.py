#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED = [
    "SKILL.md",
    "README.md",
    "agents/openai.yaml",
    "references/workflow.md",
    "references/interview-first-intake.md",
    "references/repository-analysis-checklist.md",
    "references/language-discovery-rules.md",
    "references/dependency-analysis.md",
    "references/evidence-and-readiness.md",
    "references/configuration-timing.md",
    "assets/migration-assessment-template.md",
    "assets/migration-summary-template.md",
    "scripts/validate_report.py",
    "tests/scenarios.md",
]

REQUIRED_TERMS = [
    "Confirmed", "Inferred", "Unknown", "Conflicting",
    "Ready", "Needs Input", "Blocked",
    "dependency matrix", "dependency graph",
    "A missing Dockerfile is a finding, not an analysis failure",
    "Do not generate Kubernetes manifests",
    "Execution Locus", "Application Phase",
    "Default output mode: summary", "Interview-First Intake",
    "Repository URL", "Local path",
]


def fail(errors: list[str]) -> int:
    for error in errors:
        print(f"FAIL: {error}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the skill package structure.")
    parser.add_argument("root", nargs="?", default=".", help="Skill package directory")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors: list[str] = []

    for rel in REQUIRED:
        if not (root / rel).is_file():
            errors.append(f"missing required file: {rel}")

    skill_path = root / "SKILL.md"
    if skill_path.is_file():
        text = skill_path.read_text(encoding="utf-8")
        match = re.match(r"^---\nname: ([a-z0-9-]+)\ndescription: (.+)\n---\n", text)
        if not match:
            errors.append("SKILL.md frontmatter must contain name and one-line description")
        else:
            name, description = match.groups()
            if name != "analyze-repo-for-kubernetes":
                errors.append(f"unexpected skill name: {name}")
            if not description.startswith("Use when "):
                errors.append("description must start with 'Use when '")
            if len(description) > 500:
                errors.append("description exceeds 500 characters")

        links = re.findall(r"\((references/[^)]+\.md|assets/[^)]+\.md)\)", text)
        if len(links) < 5:
            errors.append("SKILL.md must link to the packaged references and template")
        for rel in links:
            if not (root / rel).is_file():
                errors.append(f"broken SKILL.md link: {rel}")

    markdown = list(root.rglob("*.md"))
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in markdown)
    for term in REQUIRED_TERMS:
        if term not in all_text:
            errors.append(f"required contract text not found: {term}")

    placeholder_pattern = re.compile(r"\b(?:TBD|TODO|FIXME)\b")
    for path in markdown:
        if placeholder_pattern.search(path.read_text(encoding="utf-8")):
            errors.append(f"placeholder marker found: {path.relative_to(root)}")

    skill_files = [p for p in root.rglob("*") if p.is_file() and p.name.lower() == "skill.md"]
    if len(skill_files) != 1:
        errors.append(f"expected exactly one SKILL.md, found {len(skill_files)}")

    if errors:
        return fail(errors)

    print("PASS: analyze-repo-for-kubernetes package is structurally valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
