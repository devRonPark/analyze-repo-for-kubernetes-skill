from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import re

import report_contract
import report_records


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
COMPONENT_PROPERTY = re.compile(
    r"^### (?:배포 대상|구성 요소):\s*(?P<subject>.+?)의 속성 "
    r"(?:근거에 .+?이 없습니다|이 .+? 형식이 아닙니다): "
    r"- (?P<label>[^:]+):"
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


EVIDENCE_REFERENCE = re.compile(
    r"(?<![0-9A-Za-z_.-])(?P<reference>[0-9A-Za-z_./-]+:[1-9]\d*)"
)


def resolve_document_diagnostics(
    diagnostics: tuple[Diagnostic, ...],
    document: report_records.ReportDocument,
    contract: report_contract.ReportContract,
) -> tuple[Diagnostic, ...]:
    actual_subject_ids = {
        subject.subject_id for subject in document.subjects
    }
    subjects_by_display: dict[str, list[str]] = {}
    for subject in document.subjects:
        subjects_by_display.setdefault(subject.display_name, []).append(
            subject.subject_id
        )
    group_by_field = {
        field.field_id: group
        for group, fields in contract.field_groups.items()
        for field in fields
    }

    resolved = []
    for diagnostic in diagnostics:
        item = diagnostic
        component = COMPONENT_FIELD.match(item.message)
        if (
            component is not None
            and item.subject_id not in actual_subject_ids
        ):
            matches = subjects_by_display.get(
                component.group("subject"), []
            )
            if len(matches) == 1:
                item = replace(item, subject_id=matches[0])

        component_property = COMPONENT_PROPERTY.match(item.message)
        if component_property is not None:
            matches = subjects_by_display.get(
                component_property.group("subject"), []
            )
            group, field = _field_lookup().get(
                component_property.group("label"),
                ("", ""),
            )
            if len(matches) == 1 and group and field:
                item = replace(
                    item,
                    section_key=group,
                    subject_id=matches[0],
                    field=field,
                )

        references = {
            match.group("reference")
            for match in EVIDENCE_REFERENCE.finditer(item.message)
        }
        if references and not item.section_key:
            record_matches: list[Diagnostic] = []
            for claim in document.claims:
                if references.intersection(claim.evidence):
                    record_matches.append(
                        replace(
                            item,
                            section_key=group_by_field.get(
                                claim.field, ""
                            ),
                            subject_id=claim.subject_id,
                            field=claim.field,
                        )
                    )
            for relationship in document.relationships:
                if references.intersection(relationship.evidence):
                    record_matches.append(
                        replace(
                            item,
                            section_key="relationships",
                            subject_id=relationship.edge_id,
                        )
                    )
            if record_matches:
                unique = {
                    (
                        match.section_key,
                        match.subject_id,
                        match.field,
                    ): match
                    for match in record_matches
                }
                resolved.extend(
                    unique[key] for key in sorted(unique)
                )
                continue
        resolved.append(item)
    return tuple(resolved)
