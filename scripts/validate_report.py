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
NEW_SUMMARY_SECTIONS = [
    "## 1. 분석 범위",
    "## 2. 배포 대상 후보",
    "## 3. 배포 대상별 실행 정보",
    "## 4. 구성과 관계",
    "## 5. 운영 환경 배포 근거",
    "## 6. Kubernetes 설계 입력 상태",
]

DETAILED_SECTIONS = [
    "## 1. 평가 범위",
    "## 2. 한눈에 보기",
    "## 3. 구성 요소별 배포 브리핑",
    "## 4. 구성 요소 관계",
    "## 5. 설정과 상태 상세",
    "## 6. 최소 입력 누락과 conflict 상세",
    "## 7. 최종 판정",
]
NEW_DETAILED_SECTIONS = [
    "## 1. 분석 범위",
    "## 2. 배포 대상 후보",
    "## 3. 배포 대상별 실행 정보",
    "## 4. 구성과 관계",
    "## 5. 운영 환경 배포 근거",
    "## 6. 설정과 상태 상세",
    "## 7. 제외 항목과 설계 차단 항목 상세",
    "## 8. Kubernetes 설계 입력 상태",
]

FIXTURES = {
    "no-dockerfile-monorepo": [
        "frontend", "api", "worker", "shared",
        "컨테이너화 필요", "PostgreSQL", "Redis", "RabbitMQ",
        "8009", "추가 정보 필요", "브라우저", "빌드 시점",
    ]
}

FILE_LINE_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_./-])(?P<path>(?:[A-Za-z0-9_.@+\-\[\]]+/)*[A-Za-z0-9_.@+\-\[\]]+):(?P<start>\d+)(?:-(?P<end>\d+))?(?=$|[`\s,;|)\]])"
)
ABSENCE_REFERENCE = re.compile(
    r"검색\(scope=.+,\s*pattern=.+,\s*result=없음\)"
)
COMPONENT_HEADING = re.compile(r"^### 구성 요소:\s*\S+", re.MULTILINE)
WORKLOAD_HEADING = re.compile(r"^### 배포 대상:\s*\S+", re.MULTILINE)
PROPERTY_LINE = re.compile(
    r"^- [^:\n]+:.+ — 상태: (확인됨|추정됨|미확인|상충됨) / 근거: (.+)$"
)


def detect_mode(text: str) -> str | None:
    if text.lstrip().startswith(("# Kubernetes 이관 요약", "# Kubernetes 설계 입력 요약")):
        return "summary"
    if text.lstrip().startswith(("# Kubernetes 이관 상세 평가", "# Kubernetes 설계 입력 상세 평가")):
        return "detailed"
    return None


def has_valid_evidence(value: str) -> bool:
    return bool(FILE_LINE_REFERENCE.search(value) or ABSENCE_REFERENCE.search(value))


def repository_reference_errors(text: str, repository_root: Path | None) -> list[str]:
    """--repo-root가 주어진 경우 positive evidence의 파일과 줄 범위를 검증한다."""
    if repository_root is None:
        return []

    errors: list[str] = []
    root = repository_root.resolve()
    # `redis-cart:6379` 같은 endpoint는 file:line과 표기가 같으므로,
    # 실제 인용 필드인 `근거:` 뒤에 있는 값만 검사한다.
    evidence_values = [line.split("근거:", 1)[1] for line in text.splitlines() if "근거:" in line]
    for evidence in evidence_values:
        for reference in FILE_LINE_REFERENCE.finditer(evidence):
            relative_path = Path(reference.group("path"))
            # 서비스 endpoint(`shoppingassistantservice:80`)는 근거 문장 안에
            # 있을 수 있지만 file:line 인용은 아니다. 경로 구분자나 확장자가
            # 없는 소문자 단일 이름은 파일 인용으로 해석하지 않는다.
            bare_name = relative_path.name
            if "/" not in reference.group("path") and "." not in bare_name and bare_name not in {"Dockerfile", "Makefile", "README", "LICENSE"}:
                continue
            candidate = (root / relative_path).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                errors.append(f"저장소 밖 경로를 인용했습니다: {reference.group(0)}")
                continue
            if not candidate.is_file():
                errors.append(f"인용 파일이 저장소에 없습니다: {reference.group(0)}")
                continue
            line_count = len(candidate.read_text(encoding="utf-8", errors="replace").splitlines())
            start = int(reference.group("start"))
            end = int(reference.group("end") or start)
            if start < 1 or end < start or end > line_count:
                errors.append(
                    f"인용 줄 범위가 파일 범위를 벗어났습니다: {reference.group(0)} "
                    f"(파일 줄 수: {line_count})"
                )
    return errors


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
                if not has_valid_evidence(evidence):
                    errors.append(f"{index + 1}행 근거 셀에 file:line 또는 검색(...) 근거가 없습니다")
            index += 1
    return errors


def component_cards(text: str) -> list[tuple[str, str]]:
    headings = list(COMPONENT_HEADING.finditer(text)) + list(WORKLOAD_HEADING.finditer(text))
    headings.sort(key=lambda heading: heading.start())
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

    new_contract = "## 3. 배포 대상별 실행 정보" in text
    categories = [
        "#### 역할과 실행",
        "#### 빌드와 기동",
        "#### 네트워크와 상태 확인",
        "#### 설정과 상태",
        "#### Kubernetes 최소 설계 입력",
        "#### 최소 입력 누락",
    ]
    required_properties = [
        "역할:", "배포 대상 여부:", "배포 구성:", "경로:", "유형:", "언어:", "프레임워크:", "런타임:",
        "패키지 관리자:", "설치 명령:", "빌드 명령:", "이미지 빌드 명령:", "운영 기동 명령:", "컨테이너화:",
        "프로토콜:", "수신 포트:", "상태 확인:",
        "설정:", "Secret:", "저장소:", "볼륨 또는 세션:", "적용 시점:",
    ]
    minimum_fields = [
        "workload.kind:", "metadata.name:", "image:", "command:", "args:",
        "containerPort:", "Service:", "Ingress:",
    ]
    if new_contract:
        categories = [
            "#### 실행 정보", "#### 설정과 상태", "#### Kubernetes 최소 설계 입력", "#### 최소 입력 누락",
        ]
        required_properties = [
            "실행 형태:", "경로:", "언어:", "프레임워크:", "런타임:", "패키지 관리자:",
            "설치 명령:", "빌드 명령:", "이미지 빌드 명령:", "운영 기동 명령:", "컨테이너화:",
            "프로토콜:", "수신 포트:", "상태 확인:", "설정:", "Secret:",
            "쓰기 상태 또는 영속성:", "적용 시점:", "종료와 복구:", "관찰 가능성:",
        ]

    for heading, card in cards:
        for category in categories:
            if category not in card:
                errors.append(f"{heading}에 범주가 없습니다: {category[5:]}")
        for property_name in required_properties:
            if property_name not in card:
                errors.append(f"{heading}에 필수 속성이 없습니다: {property_name[:-1]}")

        minimum_start = card.find("#### Kubernetes 최소 설계 입력")
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
            if not has_valid_evidence(match.group(2)):
                errors.append(f"{heading}의 속성 근거에 file:line 또는 검색(...)이 없습니다: {line}")
    return errors


def disallowed_section_errors(text: str) -> list[str]:
    errors: list[str] = []
    for label in ["## 다음 작업", "다음 인계:"]:
        if label in text:
            errors.append(f"출력하면 안 되는 작업 계획 항목이 있습니다: {label}")
    return errors


def dependency_and_readiness_errors(text: str) -> list[str]:
    errors: list[str] = []
    new_contract = "## 3. 배포 대상별 실행 정보" in text
    dependency_fields = ["기능 실행에 필요", "공급 또는 관리 경계"] if new_contract else ["애플리케이션 필수 여부", "선택한 배포 구성에서 필요"]
    for field in dependency_fields:
        if field not in text:
            errors.append(f"의존성 필요 여부 필드가 없습니다: {field}")
    headings = ["### 설계 차단 항목"] if new_contract else ["### Readiness 차단 요인", "### 일반 운영 권장사항"]
    for heading in headings:
        if heading not in text:
            errors.append(f"최종 판정에 필수 구분이 없습니다: {heading[4:]}")
    return errors


def mode_specific_errors(text: str, mode: str | None) -> list[str]:
    errors: list[str] = []
    if mode == "detailed" and "## 3. 구성 요소별 배포 브리핑" in text:
        for heading in ["### Dependency matrix", "### Text dependency graph"]:
            if heading not in text:
                errors.append(f"detailed 모드에 필수 관계 표현이 없습니다: {heading[4:]}")
    return errors


def overview_errors(text: str) -> list[str]:
    errors: list[str] = []
    new_contract = "## 3. 배포 대상별 실행 정보" in text
    required = [
        "배포 가능한 구성 요소:",
        "기본 배포 구성:",
        "제외한 선택·개발용 구성:",
        "제외한 주요 package:",
        "확인된 수신 포트:",
        "적용을 막는 최소 입력 누락:",
    ]
    if new_contract:
        return []
    overview = text.split("## 3. 구성 요소별 배포 브리핑", 1)[0]
    for field in required:
        if field not in overview:
            errors.append(f"한눈에 보기에 필수 키가 없습니다: {field[:-1]}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="생성된 Kubernetes 이관 보고서를 검증합니다.")
    parser.add_argument("report", help="생성된 Markdown 보고서")
    parser.add_argument("--mode", choices=["auto", "summary", "detailed"], default="auto")
    parser.add_argument("--fixture", choices=sorted(FIXTURES), help="fixture별 검사를 적용합니다")
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="인용한 file:line 위치를 검증할 분석 대상 저장소 루트",
    )
    args = parser.parse_args()

    path = Path(args.report)
    if not path.is_file():
        print(f"실패: 보고서를 찾을 수 없습니다: {path}")
        return 1

    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    if args.repo_root is not None and not args.repo_root.is_dir():
        errors.append(f"저장소 루트를 찾을 수 없습니다: {args.repo_root}")
    detected = detect_mode(text)
    mode = detected if args.mode == "auto" else args.mode
    if mode is None:
        errors.append("제목에서 보고서 모드를 감지할 수 없습니다")
    elif detected is not None and args.mode != "auto" and detected != args.mode:
        errors.append(f"보고서 제목은 {detected} 모드를 가리키지만 요청 모드는 {args.mode}입니다")

    new_contract = "## 3. 배포 대상별 실행 정보" in text
    required_sections = (
        NEW_SUMMARY_SECTIONS if new_contract and mode == "summary"
        else NEW_DETAILED_SECTIONS if new_contract and mode == "detailed"
        else SUMMARY_SECTIONS if mode == "summary" else DETAILED_SECTIONS
    )
    for section in required_sections:
        if section not in text:
            errors.append(f"섹션이 없습니다: {section}")
    verdicts = re.findall(r"(?m)^- 판정: (설계 입력 충분|준비됨|추가 정보 필요|분석 불가|진행 불가)$", text)
    if not verdicts:
        errors.append("명시적인 최종 판정이 없습니다")
    elif len(verdicts) > 1:
        errors.append("최종 판정은 정확히 하나여야 합니다")
    if not has_valid_evidence(text):
        errors.append("file:line 또는 검색(...) 근거를 찾을 수 없습니다")

    errors.extend(evidence_table_errors(text))
    errors.extend(component_briefing_errors(text))
    errors.extend(overview_errors(text))
    errors.extend(disallowed_section_errors(text))
    errors.extend(dependency_and_readiness_errors(text))
    errors.extend(mode_specific_errors(text, mode))
    errors.extend(
        repository_reference_errors(
            text,
            args.repo_root if args.repo_root is not None and args.repo_root.is_dir() else None,
        )
    )
    for field in ([] if new_contract else ["실행 위치", "적용 시점"]):
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
