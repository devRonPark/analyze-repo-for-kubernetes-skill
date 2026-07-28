from __future__ import annotations

from dataclasses import asdict, dataclass
import re

import report_contract


@dataclass(frozen=True)
class Diagnostic:
    code: str
    section_key: str
    subject_id: str
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


COMPONENT_FIELD = re.compile(
    r"^### (?:배포 대상|구성 요소):\s*(?P<subject>.+?)에 "
    r"(?:필수 속성이 없습니다|최소 초안 값 또는 최소 입력 누락이 없습니다): "
    r"(?P<label>.+)$"
)
MISSING_SECTION = re.compile(r"^섹션이 없습니다:\s*(?P<heading>.+)$")


def _field_lookup() -> dict[str, tuple[str, str]]:
    contract = report_contract.load_report_contract()
    return {
        field.label: (group, field.field_id)
        for group, fields in contract.field_groups.items()
        for field in fields
    }


def _section_lookup() -> dict[str, str]:
    contract = report_contract.load_report_contract()
    return {
        section.heading: section.key
        for mode in contract.modes.values()
        for section in mode.sections
    }


def _subject_id(display_name: str) -> str:
    if display_name.startswith("deployable:"):
        return display_name
    slug = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", display_name.strip())
    return f"deployable:{slug.strip('-').lower()}"


def from_message(message: str) -> Diagnostic:
    component = COMPONENT_FIELD.match(message)
    if component is not None:
        group, field = _field_lookup().get(
            component.group("label"),
            ("component_gap", ""),
        )
        return Diagnostic(
            "MISSING_REQUIRED_FIELD",
            group,
            _subject_id(component.group("subject")),
            field,
            message,
        )

    section = MISSING_SECTION.match(message)
    if section is not None:
        heading = section.group("heading")
        return Diagnostic(
            "MISSING_SECTION",
            _section_lookup().get(heading, ""),
            "",
            "",
            message,
        )

    if message == "명시적인 최종 판정이 없습니다":
        return Diagnostic(
            "MISSING_REQUIRED_FIELD",
            "readiness",
            "",
            "verdict",
            message,
        )
    if message.startswith("인용 파일이 저장소에 없습니다"):
        code = "EVIDENCE_FILE_NOT_FOUND"
    elif message.startswith("인용 줄 범위가 파일 범위를 벗어났습니다"):
        code = "EVIDENCE_LINE_OUT_OF_RANGE"
    elif message.startswith("저장소 밖 경로를 인용했습니다"):
        code = "EVIDENCE_PATH_OUTSIDE_REPOSITORY"
    elif "근거" in message:
        code = "INVALID_EVIDENCE"
    elif "형식" in message:
        code = "INVALID_FIELD_FORMAT"
    else:
        code = "VALIDATION_ERROR"
    return Diagnostic(code, "", "", "", message)
