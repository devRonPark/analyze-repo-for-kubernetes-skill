#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
import sys
from pathlib import Path

import report_contract
from report_diagnostics import Diagnostic
import report_diagnostics

SUMMARY_SECTIONS = [
    "## 1. 범위",
    "## 2. 한눈에 보기",
    "## 3. 구성 요소별 배포 브리핑",
    "## 4. 구성 요소 관계",
    "## 5. 최종 판정",
]
NEW_SUMMARY_SECTIONS = list(report_contract.headings_for("summary"))

DETAILED_SECTIONS = [
    "## 1. 평가 범위",
    "## 2. 한눈에 보기",
    "## 3. 구성 요소별 배포 브리핑",
    "## 4. 구성 요소 관계",
    "## 5. 설정과 상태 상세",
    "## 6. 최소 입력 누락과 conflict 상세",
    "## 7. 최종 판정",
]
NEW_DETAILED_SECTIONS = list(report_contract.headings_for("detailed"))
NEW_REPORT_TITLES = {
    "summary": report_contract.title_for("summary"),
    "detailed": report_contract.title_for("detailed"),
}
SECTION_CONTRACTS = {
    ("legacy", "summary"): SUMMARY_SECTIONS,
    ("legacy", "detailed"): DETAILED_SECTIONS,
    ("new", "summary"): NEW_SUMMARY_SECTIONS,
    ("new", "detailed"): NEW_DETAILED_SECTIONS,
}
CONTRACT_LABELS = {
    ("legacy", "summary"): "LEGACY_SUMMARY",
    ("legacy", "detailed"): "LEGACY_DETAILED",
    ("new", "summary"): "NEW_SUMMARY",
    ("new", "detailed"): "NEW_DETAILED",
}

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
SECTION_FENCE = re.compile(r"^\s*(```|~~~)")
SECTION_HEADING = re.compile(r"^##\s*(?:(?P<number>\d+)\.\s*)?(?P<name>.+?)\s*$")


def detect_mode(text: str) -> str | None:
    if text.lstrip().startswith(("# Kubernetes 이관 요약", f"# {NEW_REPORT_TITLES['summary']}")):
        return "summary"
    if text.lstrip().startswith(("# Kubernetes 이관 상세 평가", f"# {NEW_REPORT_TITLES['detailed']}")):
        return "detailed"
    return None


def markdown_h2_sections(text: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []
    in_fence = False
    fence_marker: str | None = None
    for line in text.splitlines():
        fence = SECTION_FENCE.match(line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker[:3]
            elif marker.startswith(fence_marker or ""):
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue
        match = SECTION_HEADING.match(line)
        if match:
            sections.append((match.group("number"), match.group("name").strip()))
    return sections


def section_name(section: str) -> str:
    match = SECTION_HEADING.match(section)
    if not match:
        return section.removeprefix("##").strip()
    return match.group("name").strip()


def section_number(section: str) -> str | None:
    match = SECTION_HEADING.match(section)
    return match.group("number") if match else None


def matching_section(
    headings: list[tuple[str | None, str]],
    section: str,
) -> tuple[str | None, str] | None:
    expected = section_name(section)
    return next((heading for heading in headings if heading[1] == expected), None)


def detect_contract(
    headings: list[tuple[str | None, str]],
    mode: str | None,
    requested_contract: str,
) -> tuple[str | None, str]:
    if requested_contract == "legacy":
        return "legacy", "명시: --contract legacy"
    if requested_contract == "new":
        return "new", "명시: --contract new"
    if mode not in {"summary", "detailed"}:
        return None, "mode 미감지"

    sections = SECTION_CONTRACTS[("new", mode)]
    matched = [section for section in sections if matching_section(headings, section)]
    if matched:
        first = section_name(matched[0])
        return "new", f"섹션명 매칭: {first} ({len(matched)}/{len(sections)})"
    return None, "신 계약 섹션명 없음"


def missing_section_errors(
    headings: list[tuple[str | None, str]],
    required_sections: list[str],
) -> list[str]:
    errors: list[str] = []
    for section in required_sections:
        if matching_section(headings, section) is None:
            errors.append(f"섹션이 없습니다: {section}")
    return errors


def section_number_warnings(
    headings: list[tuple[str | None, str]],
    required_sections: list[str],
) -> list[str]:
    warnings: list[str] = []
    for section in required_sections:
        expected_number = section_number(section)
        match = matching_section(headings, section)
        if match is not None and expected_number is not None and match[0] != expected_number:
            warnings.append(f"섹션 번호 접두사가 없습니다: {section}")
    return warnings


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


def component_briefing_errors(text: str, contract: str) -> list[str]:
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
    if contract == "new":
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


def dependency_and_readiness_errors(text: str, contract: str) -> list[str]:
    errors: list[str] = []
    dependency_fields = ["기능 실행에 필요", "공급 또는 관리 경계"] if contract == "new" else ["애플리케이션 필수 여부", "선택한 배포 구성에서 필요"]
    for field in dependency_fields:
        if field not in text:
            errors.append(f"의존성 필요 여부 필드가 없습니다: {field}")
    headings = ["### 설계 차단 항목"] if contract == "new" else ["### Readiness 차단 요인", "### 일반 운영 권장사항"]
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


def overview_errors(text: str, contract: str) -> list[str]:
    errors: list[str] = []
    required = [
        "배포 가능한 구성 요소:",
        "기본 배포 구성:",
        "제외한 선택·개발용 구성:",
        "제외한 주요 package:",
        "확인된 수신 포트:",
        "적용을 막는 최소 입력 누락:",
    ]
    if contract == "new":
        return []
    overview = text.split("## 3. 구성 요소별 배포 브리핑", 1)[0]
    for field in required:
        if field not in overview:
            errors.append(f"한눈에 보기에 필수 키가 없습니다: {field[:-1]}")
    return errors


@dataclass(frozen=True)
class ValidationSummary:
    diagnostics: tuple[Diagnostic, ...]
    warnings: tuple[str, ...]
    mode: str | None
    contract: str | None
    detection: str


def _validate_text(
    text: str,
    *,
    requested_mode: str = "auto",
    requested_contract: str = "auto",
    fixture: str | None = None,
    repository_root: Path | None = None,
) -> ValidationSummary:
    headings = markdown_h2_sections(text)
    errors: list[str] = []
    warnings: list[str] = []
    if repository_root is not None and not repository_root.is_dir():
        errors.append(f"저장소 루트를 찾을 수 없습니다: {repository_root}")
    detected = detect_mode(text)
    mode = detected if requested_mode == "auto" else requested_mode
    if mode is None:
        errors.append("제목에서 보고서 모드를 감지할 수 없습니다")
    elif (
        detected is not None
        and requested_mode != "auto"
        and detected != requested_mode
    ):
        errors.append(
            f"보고서 제목은 {detected} 모드를 가리키지만 "
            f"요청 모드는 {requested_mode}입니다"
        )

    contract, detection = detect_contract(
        headings, mode, requested_contract
    )
    if contract is None:
        errors.append(
            "보고서 계약을 감지할 수 없습니다: 신 계약 섹션명을 찾지 못했습니다. "
            "레거시 계약 검증은 --contract legacy로 명시해야 합니다."
        )
        required_sections = []
    elif mode not in {"summary", "detailed"}:
        required_sections = []
    else:
        required_sections = SECTION_CONTRACTS[(contract, mode)]
        errors.extend(missing_section_errors(headings, required_sections))
        if contract == "new":
            warnings.extend(section_number_warnings(headings, required_sections))
    verdicts = re.findall(r"(?m)^- 판정: (설계 입력 충분|준비됨|추가 정보 필요|분석 불가|진행 불가)$", text)
    if not verdicts:
        errors.append("명시적인 최종 판정이 없습니다")
    elif len(verdicts) > 1:
        errors.append("최종 판정은 정확히 하나여야 합니다")
    if not has_valid_evidence(text):
        errors.append("file:line 또는 검색(...) 근거를 찾을 수 없습니다")

    errors.extend(evidence_table_errors(text))
    if contract is not None:
        errors.extend(component_briefing_errors(text, contract))
        errors.extend(overview_errors(text, contract))
        errors.extend(dependency_and_readiness_errors(text, contract))
    errors.extend(disallowed_section_errors(text))
    errors.extend(mode_specific_errors(text, mode))
    errors.extend(
        repository_reference_errors(
            text,
            (
                repository_root
                if repository_root is not None and repository_root.is_dir()
                else None
            ),
        )
    )
    if contract == "legacy":
        for field in ["실행 위치", "적용 시점"]:
            if field not in text:
                errors.append(f"필수 필드가 없습니다: {field}")
    if fixture:
        for term in FIXTURES[fixture]:
            if term not in text:
                errors.append(f"fixture 기대값을 찾을 수 없습니다: {term}")

    return ValidationSummary(
        tuple(report_diagnostics.from_message(error) for error in errors),
        tuple(warnings),
        mode,
        contract,
        detection,
    )


def validate_text(
    text: str,
    *,
    mode: str = "auto",
    contract: str = "auto",
    fixture: str | None = None,
    repository_root: Path | None = None,
) -> tuple[Diagnostic, ...]:
    return _validate_text(
        text,
        requested_mode=mode,
        requested_contract=contract,
        fixture=fixture,
        repository_root=repository_root,
    ).diagnostics


def _json_result(diagnostics: tuple[Diagnostic, ...]) -> str:
    return json.dumps(
        {
            "valid": not diagnostics,
            "errors": [
                diagnostic.to_dict() for diagnostic in diagnostics
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="생성된 Kubernetes 이관 보고서를 검증합니다.")
    parser.add_argument("report", help="생성된 Markdown 보고서")
    parser.add_argument("--mode", choices=["auto", "summary", "detailed"], default="auto")
    parser.add_argument("--contract", choices=["auto", "new", "legacy"], default="auto")
    parser.add_argument("--fixture", choices=sorted(FIXTURES), help="fixture별 검사를 적용합니다")
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="인용한 file:line 위치를 검증할 분석 대상 저장소 루트",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
    )
    args = parser.parse_args()

    path = Path(args.report)
    if not path.is_file():
        message = f"보고서를 찾을 수 없습니다: {path}"
        if args.output_format == "json":
            print(
                _json_result(
                    (
                        Diagnostic(
                            "REPORT_NOT_FOUND", "", "", "", message
                        ),
                    )
                )
            )
        else:
            print(f"실패: {message}")
        return 1

    summary = _validate_text(
        path.read_text(encoding="utf-8"),
        requested_mode=args.mode,
        requested_contract=args.contract,
        fixture=args.fixture,
        repository_root=args.repo_root,
    )
    if args.output_format == "json":
        print(_json_result(summary.diagnostics))
        return 1 if summary.diagnostics else 0

    if summary.diagnostics:
        if (
            summary.contract is not None
            and summary.mode in {"summary", "detailed"}
        ):
            print(
                f"계약: {CONTRACT_LABELS[(summary.contract, summary.mode)]} "
                f"(감지: {summary.detection})"
            )
        for warning in summary.warnings:
            print(f"경고: {warning}")
        for diagnostic in summary.diagnostics:
            print(f"실패: {diagnostic.message}")
        return 1
    if summary.contract is not None and summary.mode in {"summary", "detailed"}:
        print(
            f"계약: {CONTRACT_LABELS[(summary.contract, summary.mode)]} "
            f"(감지: {summary.detection})"
        )
    for warning in summary.warnings:
        print(f"경고: {warning}")
    print(
        f"성공: 보고서에 필요한 {summary.mode} 브리핑 구조가 "
        "포함되어 있습니다."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
