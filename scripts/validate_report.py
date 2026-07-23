#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SUMMARY_SECTIONS = [
    "## 1. 범위",
    "## 2. 한눈에 보기",
    "## 3. 구성 요소별 배포 브리핑",
    "## 4. 구성 요소 관계",
    "## 5. 최종 판정",
]

DETAILED_SECTIONS = [
    "## 1. 평가 범위",
    "## 2. 한눈에 보기",
    "## 3. 구성 요소별 배포 브리핑",
    "## 4. 구성 요소 관계",
    "## 5. 설정과 상태 상세",
    "## 6. 최소 입력 누락 상세",
    "## 7. 최종 판정",
]

FIXTURES = {
    "no-dockerfile-monorepo": [
        "frontend", "api", "worker", "shared",
        "컨테이너화 필요", "PostgreSQL", "Redis", "RabbitMQ",
        "8009", "추가 정보 필요", "브라우저", "빌드 시점",
    ]
}

FILE_LINE_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_./-])(?:[A-Za-z0-9_.@+-]+/)*[A-Za-z0-9_.@+-]+:\d+(?:-\d+)?(?=$|[\s,;|)\]])"
)
COMPONENT_HEADING = re.compile(r"^### 구성 요소:\s*\S+", re.MULTILINE)
PROPERTY_LINE = re.compile(
    r"^- [^:\n]+:.+ — 상태: (확인됨|추정됨|미확인|상충됨) / 근거: (.+)$"
)


def detect_mode(text: str) -> str | None:
    if text.lstrip().startswith("# Kubernetes 이관 요약"):
        return "summary"
    if text.lstrip().startswith("# Kubernetes 이관 상세 평가"):
        return "detailed"
    return None


def has_file_line_reference(value: str) -> bool:
    return bool(FILE_LINE_REFERENCE.search(value))


def evidence_table_errors(text: str) -> list[str]:
    """관계 표처럼 남아 있는 표의 근거 셀도 검사한다."""
    errors: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        header = lines[index]
        if not header.lstrip().startswith("|"):
            index += 1
            continue
        columns = [cell.strip() for cell in header.strip().strip("|").split("|")]
        evidence_column = next(
            (position for position, column in enumerate(columns) if column.startswith("근거")),
            None,
        )
        if evidence_column is None or index + 1 >= len(lines):
            index += 1
            continue
        separator = lines[index + 1].strip()
        if not separator.startswith("|") or "-" not in separator:
            index += 1
            continue
        index += 2
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
            if any(cell for position, cell in enumerate(row) if position != evidence_column):
                evidence = row[evidence_column] if evidence_column < len(row) else ""
                if not has_file_line_reference(evidence):
                    errors.append(f"{index + 1}행 근거 셀에 file:line 근거가 없습니다")
            index += 1
    return errors


def component_cards(text: str) -> list[tuple[str, str]]:
    headings = list(COMPONENT_HEADING.finditer(text))
    cards: list[tuple[str, str]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        next_top_level = text.find("\n## ", heading.end())
        if next_top_level != -1 and next_top_level < end:
            end = next_top_level
        cards.append((heading.group(0), text[heading.end():end]))
    return cards


def component_briefing_errors(text: str) -> list[str]:
    """구성 요소마다 분류된 key:value 속성과 속성별 근거를 요구한다."""
    errors: list[str] = []
    cards = component_cards(text)
    if not cards:
        return ["구성 요소별 배포 브리핑에 구성 요소 카드가 없습니다"]

    categories = [
        "#### 역할과 실행",
        "#### 빌드와 기동",
        "#### 네트워크와 상태 확인",
        "#### 설정과 상태",
        "#### Kubernetes 최소 초안",
        "#### 최소 입력 누락",
    ]
    required_properties = [
        "역할:", "경로:", "유형:", "언어:", "프레임워크:", "런타임:",
        "빌드 명령:", "운영 기동 명령:", "컨테이너화:",
        "프로토콜:", "수신 포트:", "상태 확인:",
        "설정:", "Secret:", "저장소:", "볼륨 또는 세션:", "적용 시점:",
    ]
    minimum_fields = ["workload.kind:", "metadata.name:", "image:", "command:", "args:", "containerPort:"]

    for heading, card in cards:
        for category in categories:
            if category not in card:
                errors.append(f"{heading}에 범주가 없습니다: {category[5:]}")
        for property_name in required_properties:
            if property_name not in card:
                errors.append(f"{heading}에 필수 속성이 없습니다: {property_name[:-1]}")

        minimum_start = card.find("#### Kubernetes 최소 초안")
        missing_start = card.find("#### 최소 입력 누락")
        minimum = card[minimum_start:missing_start] if minimum_start != -1 and missing_start != -1 else ""
        missing = card[missing_start:] if missing_start != -1 else ""
        for property_name in minimum_fields:
            if property_name not in minimum and property_name not in missing:
                errors.append(f"{heading}에 최소 초안 값 또는 최소 입력 누락이 없습니다: {property_name[:-1]}")

        for line in card.splitlines():
            if not line.startswith("- "):
                continue
            match = PROPERTY_LINE.match(line)
            if not match:
                errors.append(f"{heading}의 속성이 key: value — 상태 / 근거 형식이 아닙니다: {line}")
                continue
            if not has_file_line_reference(match.group(2)):
                errors.append(f"{heading}의 속성 근거에 file:line이 없습니다: {line}")
    return errors


def disallowed_section_errors(text: str) -> list[str]:
    errors: list[str] = []
    for label in ["## 다음 작업", "다음 인계:"]:
        if label in text:
            errors.append(f"출력하면 안 되는 작업 계획 항목이 있습니다: {label}")
    return errors


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
    if not any(verdict in text for verdict in ["판정: 준비됨", "판정: 추가 정보 필요", "판정: 진행 불가"]):
        errors.append("명시적인 최종 판정이 없습니다")
    if not has_file_line_reference(text):
        errors.append("repository-relative file:line 근거를 찾을 수 없습니다")

    errors.extend(evidence_table_errors(text))
    errors.extend(component_briefing_errors(text))
    errors.extend(disallowed_section_errors(text))
    for field in ["실행 위치", "적용 시점"]:
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
    print(f"성공: 보고서에 필요한 {mode} 브리핑 구조가 포함되어 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
