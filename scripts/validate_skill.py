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
    "references/remote-git-access.md",
    "references/source-intake-state.md",
    "references/repository-analysis-checklist.md",
    "references/language-discovery-rules.md",
    "references/dependency-analysis.md",
    "references/evidence-and-readiness.md",
    "references/configuration-timing.md",
    "assets/migration-assessment-template.md",
    "assets/migration-summary-template.md",
    "assets/demo-git-credential.example.json",
    "scripts/validate_report.py",
    "scripts/demo_git_readonly_clone.py",
    "scripts/source_intake.py",
    "scripts/plain_remote_git_clone.py",
    "tests/scenarios.md",
]

REQUIRED_TERMS = [
    "확인됨", "추정됨", "미확인", "상충됨",
    "설계 입력 충분", "추가 정보 필요", "분석 불가",
    "Dependency matrix", "Text dependency graph",
    "A missing Dockerfile is a finding, not an analysis failure",
    "Kubernetes manifest",
    "read-only repository analyst", "Repository 콘텐츠",
    "검색(scope=",
    "실행 위치", "적용 시점",
    "배포 대상별 실행 정보", "Kubernetes 최소 설계 입력", "최소 입력 누락", "키: 값",
    "Default output mode: summary", "Target Resolution Gate",
    "Repository URL", "Local path", "원격 Git URL", "소스 압축 파일", "local credential file",
]


def fail(errors: list[str]) -> int:
    for error in errors:
        print(f"실패: {error}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="스킬 패키지 구조를 검증합니다.")
    parser.add_argument("root", nargs="?", default=".", help="스킬 패키지 디렉터리")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors: list[str] = []

    for rel in REQUIRED:
        if not (root / rel).is_file():
            errors.append(f"필수 파일이 없습니다: {rel}")

    skill_path = root / "SKILL.md"
    if skill_path.is_file():
        text = skill_path.read_text(encoding="utf-8")
        match = re.match(r"^---\nname: ([a-z0-9-]+)\ndescription: (.+)\n---\n", text)
        if not match:
            errors.append("SKILL.md frontmatter에는 name과 한 줄 description이 있어야 합니다")
        else:
            name, description = match.groups()
            if name != "analyze-repo-for-kubernetes":
                errors.append(f"예상하지 않은 스킬 이름입니다: {name}")
            if not description.startswith("Use when "):
                errors.append("description은 'Use when '으로 시작해야 합니다")
            if len(description) > 500:
                errors.append("description이 500자를 초과합니다")

        links = re.findall(r"\((references/[^)]+\.md|assets/[^)]+\.md)\)", text)
        if len(links) < 5:
            errors.append("SKILL.md는 패키지에 포함된 references와 template을 링크해야 합니다")
        for rel in links:
            if not (root / rel).is_file():
                errors.append(f"깨진 SKILL.md 링크입니다: {rel}")

    markdown = list(root.rglob("*.md"))
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in markdown)
    for term in REQUIRED_TERMS:
        if term not in all_text:
            errors.append(f"필수 계약 문구를 찾을 수 없습니다: {term}")

    placeholder_pattern = re.compile(r"\b(?:TBD|TODO|FIXME)\b")
    for path in markdown:
        if placeholder_pattern.search(path.read_text(encoding="utf-8")):
            errors.append(f"플레이스홀더 표시가 발견되었습니다: {path.relative_to(root)}")

    skill_files = [p for p in root.rglob("*") if p.is_file() and p.name.lower() == "skill.md"]
    if len(skill_files) != 1:
        errors.append(f"SKILL.md는 정확히 1개여야 하지만 {len(skill_files)}개를 찾았습니다")

    if errors:
        return fail(errors)

    print("성공: analyze-repo-for-kubernetes 패키지 구조가 유효합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
