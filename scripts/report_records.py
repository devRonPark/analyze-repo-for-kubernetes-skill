from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Mapping

import report_contract


STATUSES = frozenset(
    ("confirmed", "inferred", "unknown", "conflicted", "not_applicable")
)
REASON_REQUIRED_STATUSES = frozenset(("inferred", "unknown", "conflicted"))
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\([^)]+\)")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:password|passwd|token|api[_-]?key|secret)\s*[:=]\s*\S+"
)
FILE_LINE_REFERENCE = re.compile(r"^(?P<path>[^:\r\n]+):(?P<line>[1-9]\d*)$")
WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class Subject:
    subject_id: str
    kind: str
    display_name: str


@dataclass(frozen=True)
class Claim:
    claim_id: str
    section_key: str
    subject_id: str
    field: str
    value: str
    status: str
    evidence: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class Relationship:
    edge_id: str
    source_subject_id: str
    target_subject_id: str
    attributes: tuple[tuple[str, str], ...]
    status: str
    evidence: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ReportDocument:
    mode: str
    subjects: tuple[Subject, ...]
    claims: tuple[Claim, ...]
    relationships: tuple[Relationship, ...]


@dataclass(frozen=True)
class RecordDiagnostic:
    code: str
    message: str
    record_id: str = ""


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label}은 object여야 합니다")
    return value


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label}은 array여야 합니다")
    return value


def _string(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        qualifier = "" if allow_empty else " 비어 있지 않은"
        raise ValueError(f"{label}은{qualifier} string이어야 합니다")
    return value


def _safe_value(value: object, label: str, *, allow_empty: bool = False) -> str:
    text = _string(value, label, allow_empty=allow_empty)
    if "\n" in text or "\r" in text or "`" in text or MARKDOWN_LINK.search(text):
        raise ValueError(f"{label}에 Markdown 문법을 사용할 수 없습니다")
    if SECRET_ASSIGNMENT.search(text):
        raise ValueError(f"{label}에 secret-like value를 사용할 수 없습니다")
    return text


def _status(value: object, label: str) -> str:
    status = _string(value, label)
    if status not in STATUSES:
        raise ValueError(f"{label} status가 지원되지 않습니다: {status}")
    return status


def _evidence(value: object, label: str) -> tuple[str, ...]:
    references: list[str] = []
    for index, item in enumerate(_array(value, label)):
        reference = _string(item, f"{label}[{index}]")
        if reference.startswith("검색(") and reference.endswith(")"):
            references.append(reference)
            continue
        match = FILE_LINE_REFERENCE.fullmatch(reference)
        if not match:
            raise ValueError(
                f"{label}[{index}]은 repository-relative file:line 또는 검색(...)이어야 합니다"
            )
        relative_path = match.group("path")
        if (
            Path(relative_path).is_absolute()
            or WINDOWS_ABSOLUTE_PATH.match(relative_path)
            or ".." in Path(relative_path).parts
        ):
            raise ValueError(
                f"{label}[{index}]은 repository-relative evidence여야 합니다"
            )
        references.append(reference)
    return tuple(references)


def _reason(payload: Mapping[str, object], status: str, label: str) -> str:
    reason = _safe_value(payload.get("reason", ""), f"{label}.reason", allow_empty=True)
    if status in REASON_REQUIRED_STATUSES and not reason:
        raise ValueError(f"{label}.reason은 {status} status에 필요합니다")
    return reason


def parse_report_document(payload: object) -> ReportDocument:
    root = _object(payload, "report document")
    mode = _string(root.get("mode"), "mode")

    subjects: list[Subject] = []
    subject_ids: set[str] = set()
    for index, item in enumerate(_array(root.get("subjects"), "subjects")):
        raw = _object(item, f"subjects[{index}]")
        subject_id = _string(raw.get("subject_id"), f"subjects[{index}].subject_id")
        if subject_id in subject_ids:
            raise ValueError(f"중복 subject_id입니다: {subject_id}")
        subject_ids.add(subject_id)
        subjects.append(
            Subject(
                subject_id,
                _string(raw.get("kind"), f"subjects[{index}].kind"),
                _safe_value(
                    raw.get("display_name"), f"subjects[{index}].display_name"
                ),
            )
        )

    claims: list[Claim] = []
    claim_ids: set[str] = set()
    for index, item in enumerate(_array(root.get("claims"), "claims")):
        raw = _object(item, f"claims[{index}]")
        claim_id = _string(raw.get("claim_id"), f"claims[{index}].claim_id")
        if claim_id in claim_ids:
            raise ValueError(f"중복 claim_id입니다: {claim_id}")
        claim_ids.add(claim_id)
        subject_id = _string(
            raw.get("subject_id"), f"claims[{index}].subject_id"
        )
        if subject_id not in subject_ids:
            raise ValueError(f"claim이 알 수 없는 subject를 참조합니다: {subject_id}")
        status = _status(raw.get("status"), f"claims[{index}].status")
        claims.append(
            Claim(
                claim_id,
                _string(raw.get("section_key"), f"claims[{index}].section_key"),
                subject_id,
                _string(raw.get("field"), f"claims[{index}].field"),
                _safe_value(raw.get("value"), f"claims[{index}].value"),
                status,
                _evidence(raw.get("evidence"), f"claims[{index}].evidence"),
                _reason(raw, status, f"claims[{index}]"),
            )
        )

    relationships: list[Relationship] = []
    edge_ids: set[str] = set()
    for index, item in enumerate(
        _array(root.get("relationships"), "relationships")
    ):
        raw = _object(item, f"relationships[{index}]")
        edge_id = _string(raw.get("edge_id"), f"relationships[{index}].edge_id")
        if edge_id in edge_ids:
            raise ValueError(f"중복 edge_id입니다: {edge_id}")
        edge_ids.add(edge_id)
        source_id = _string(
            raw.get("source_subject_id"),
            f"relationships[{index}].source_subject_id",
        )
        target_id = _string(
            raw.get("target_subject_id"),
            f"relationships[{index}].target_subject_id",
        )
        for subject_id in (source_id, target_id):
            if subject_id not in subject_ids:
                raise ValueError(
                    f"relationship가 알 수 없는 subject를 참조합니다: {subject_id}"
                )
        raw_attributes = _object(
            raw.get("attributes"), f"relationships[{index}].attributes"
        )
        attributes = tuple(
            sorted(
                (
                    _string(key, f"relationships[{index}].attributes key"),
                    _safe_value(
                        value,
                        f"relationships[{index}].attributes[{key}]",
                    ),
                )
                for key, value in raw_attributes.items()
            )
        )
        status = _status(raw.get("status"), f"relationships[{index}].status")
        relationships.append(
            Relationship(
                edge_id,
                source_id,
                target_id,
                attributes,
                status,
                _evidence(
                    raw.get("evidence"), f"relationships[{index}].evidence"
                ),
                _reason(raw, status, f"relationships[{index}]"),
            )
        )

    return ReportDocument(
        mode, tuple(subjects), tuple(claims), tuple(relationships)
    )


def load_report_document(path: Path) -> ReportDocument:
    return parse_report_document(json.loads(path.read_text(encoding="utf-8")))


def validate_document(
    document: ReportDocument,
    contract: report_contract.ReportContract,
    *,
    repository_root: Path | None = None,
) -> tuple[RecordDiagnostic, ...]:
    diagnostics: list[RecordDiagnostic] = []
    try:
        mode = contract.mode(document.mode)
    except ValueError as error:
        return (RecordDiagnostic("UNKNOWN_MODE", str(error)),)

    section_keys = {section.key for section in mode.sections}
    field_ids = {
        field.field_id
        for group in report_contract.REQUIRED_FIELD_GROUPS
        for field in contract.fields_for(group)
    }
    for claim in document.claims:
        if claim.section_key not in section_keys:
            diagnostics.append(
                RecordDiagnostic(
                    "UNKNOWN_SECTION",
                    f"지원하지 않는 section입니다: {claim.section_key}",
                    claim.claim_id,
                )
            )
        if claim.field not in field_ids:
            diagnostics.append(
                RecordDiagnostic(
                    "UNKNOWN_FIELD",
                    f"지원하지 않는 field입니다: {claim.field}",
                    claim.claim_id,
                )
            )
    if repository_root is not None:
        root = repository_root.resolve()
        if not root.is_dir():
            diagnostics.append(
                RecordDiagnostic(
                    "MISSING_REPOSITORY_ROOT",
                    f"repository root를 찾을 수 없습니다: {repository_root}",
                )
            )
        else:
            evidence_records = [
                (claim.claim_id, claim.evidence) for claim in document.claims
            ] + [
                (relationship.edge_id, relationship.evidence)
                for relationship in document.relationships
            ]
            for record_id, references in evidence_records:
                for reference in references:
                    match = FILE_LINE_REFERENCE.fullmatch(reference)
                    if match is None:
                        continue
                    candidate = (root / match.group("path")).resolve()
                    try:
                        candidate.relative_to(root)
                    except ValueError:
                        diagnostics.append(
                            RecordDiagnostic(
                                "EVIDENCE_OUTSIDE_REPOSITORY",
                                f"evidence가 repository 밖을 가리킵니다: {reference}",
                                record_id,
                            )
                        )
                        continue
                    if not candidate.is_file():
                        diagnostics.append(
                            RecordDiagnostic(
                                "MISSING_EVIDENCE_FILE",
                                f"evidence file을 찾을 수 없습니다: {reference}",
                                record_id,
                            )
                        )
                        continue
                    line_count = len(
                        candidate.read_text(
                            encoding="utf-8", errors="replace"
                        ).splitlines()
                    )
                    if int(match.group("line")) > line_count:
                        diagnostics.append(
                            RecordDiagnostic(
                                "EVIDENCE_LINE_OUT_OF_RANGE",
                                f"evidence line이 파일 범위를 벗어났습니다: {reference}",
                                record_id,
                            )
                        )
    return tuple(sorted(diagnostics, key=lambda item: (item.record_id, item.code)))
