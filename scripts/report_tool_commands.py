from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Mapping


TOOL_NAMES = {
    "report_session_start",
    "report_chunk_submit",
    "report_session_sync",
    "report_session_finalize",
}
STATUSES = {
    "confirmed",
    "inferred",
    "unknown",
    "conflicted",
    "not_applicable",
}
RELATIONSHIP_STATUSES = STATUSES - {"not_applicable"}
REASON_STATUSES = {"inferred", "conflicted"}
SUBJECT_KINDS = {
    "deployable",
    "repository_dependency",
    "external_dependency",
    "configuration",
    "excluded",
}
SECTION_KEYS = {
    "scope",
    "candidate_inventory",
    "component_runtime",
    "component_config_state",
    "component_k8s_input",
    "component_gap",
    "deployment_evidence",
    "configuration_detail",
    "exclusion",
    "blocker",
    "readiness",
}
SHA256 = re.compile(r"^[a-f0-9]{64}$")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\([^)]+\)")


@dataclass(frozen=True)
class SubjectDeclaration:
    subject_id: str
    kind: str
    display_name: str


@dataclass(frozen=True)
class ToolClaim:
    claim_id: str
    unit_id: str
    section_key: str
    subject_id: str
    field: str
    value: str
    status: str
    evidence: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ToolRelationship:
    edge_id: str
    unit_id: str
    source_subject_id: str
    target_subject_id: str
    attributes: tuple[tuple[str, str], ...]
    status: str
    evidence: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class StartToolCommand:
    target_ref: str
    target_sha256: str
    analysis_snapshot_id: str
    idempotency_key: str


@dataclass(frozen=True)
class SubmitToolCommand:
    session_id: str
    lease_id: str
    expected_state_version: int
    idempotency_key: str
    chunk_ordinal: int
    subject_declarations: tuple[SubjectDeclaration, ...]
    claims: tuple[ToolClaim, ...]
    relationships: tuple[ToolRelationship, ...]
    continuation: str


@dataclass(frozen=True)
class SyncToolCommand:
    session_id: str
    known_state_version: int
    request_id: str


@dataclass(frozen=True)
class FinalizeToolCommand:
    session_id: str
    expected_state_version: int
    idempotency_key: str


def _object(
    value: object,
    label: str,
    required: tuple[str, ...],
) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    unknown = set(value) - set(required)
    missing = set(required) - set(value)
    if unknown:
        raise ValueError(f"{label} has unknown fields: {sorted(unknown)}")
    if missing:
        raise ValueError(f"{label} is missing fields: {sorted(missing)}")
    return value


def _string(
    value: object,
    label: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    if len(value) < minimum or (
        maximum is not None and len(value) > maximum
    ):
        raise ValueError(f"{label} length is invalid")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _array(
    value: object, label: str, maximum: int
) -> list[object]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{label} exceeds its bounded record limit")
    return value


def _safe_text(
    value: object,
    label: str,
    *,
    maximum: int,
    minimum: int = 0,
) -> str:
    text = _string(
        value, label, minimum=minimum, maximum=maximum
    )
    if "\n" in text or "\r" in text or "`" in text or MARKDOWN_LINK.search(text):
        raise ValueError(f"{label} contains Markdown")
    return text


def _reason(status: str, value: object, label: str) -> str:
    reason = _safe_text(value, label, maximum=1000)
    if status in REASON_STATUSES and not reason:
        raise ValueError(f"{label} is required for {status}")
    if status not in REASON_STATUSES and reason:
        raise ValueError(f"{label} must be empty for {status}")
    return reason


def _evidence(value: object, label: str, minimum: int = 0) -> tuple[str, ...]:
    items = _array(value, label, 8)
    if len(items) < minimum:
        raise ValueError(f"{label} requires at least {minimum} item")
    references = []
    for index, item in enumerate(items):
        reference = _string(
            item, f"{label}[{index}]", maximum=512
        )
        if reference.startswith(("/", "\\")) or re.match(
            r"^[A-Za-z]:[\\/]", reference
        ):
            raise ValueError(f"{label}[{index}] must be repository-relative")
        references.append(reference)
    return tuple(references)


def _parse_subject(value: object, index: int) -> SubjectDeclaration:
    raw = _object(
        value,
        f"subject_declarations[{index}]",
        ("subject_id", "kind", "display_name"),
    )
    kind = _string(raw["kind"], f"subject_declarations[{index}].kind")
    if kind not in SUBJECT_KINDS:
        raise ValueError(f"subject_declarations[{index}].kind is invalid")
    return SubjectDeclaration(
        _string(
            raw["subject_id"],
            f"subject_declarations[{index}].subject_id",
            minimum=1,
            maximum=128,
        ),
        kind,
        _safe_text(
            raw["display_name"],
            f"subject_declarations[{index}].display_name",
            minimum=1,
            maximum=256,
        ),
    )


def _parse_claim(value: object, index: int) -> ToolClaim:
    fields = (
        "claim_id",
        "unit_id",
        "section_key",
        "subject_id",
        "field",
        "value",
        "status",
        "evidence",
        "reason",
    )
    raw = _object(value, f"claims[{index}]", fields)
    status = _string(raw["status"], f"claims[{index}].status")
    if status not in STATUSES:
        raise ValueError(f"claims[{index}].status is invalid")
    section_key = _string(
        raw["section_key"], f"claims[{index}].section_key"
    )
    if section_key not in SECTION_KEYS:
        raise ValueError(f"claims[{index}].section_key is invalid")
    return ToolClaim(
        _string(
            raw["claim_id"],
            f"claims[{index}].claim_id",
            minimum=1,
            maximum=160,
        ),
        _string(raw["unit_id"], f"claims[{index}].unit_id", minimum=1),
        section_key,
        _string(
            raw["subject_id"],
            f"claims[{index}].subject_id",
            maximum=128,
        ),
        _string(
            raw["field"],
            f"claims[{index}].field",
            minimum=1,
            maximum=128,
        ),
        _safe_text(
            raw["value"], f"claims[{index}].value", maximum=2000
        ),
        status,
        _evidence(raw["evidence"], f"claims[{index}].evidence"),
        _reason(status, raw["reason"], f"claims[{index}].reason"),
    )


def _parse_relationship(
    value: object, index: int
) -> ToolRelationship:
    fields = (
        "edge_id",
        "unit_id",
        "source_subject_id",
        "target_subject_id",
        "attributes",
        "status",
        "evidence",
        "reason",
    )
    raw = _object(value, f"relationships[{index}]", fields)
    status = _string(raw["status"], f"relationships[{index}].status")
    if status not in RELATIONSHIP_STATUSES:
        raise ValueError(f"relationships[{index}].status is invalid")
    attributes = []
    for attribute_index, item in enumerate(
        _array(raw["attributes"], f"relationships[{index}].attributes", 12)
    ):
        attribute = _object(
            item,
            f"relationships[{index}].attributes[{attribute_index}]",
            ("key", "value"),
        )
        attributes.append(
            (
                _string(
                    attribute["key"],
                    f"relationships[{index}].attributes[{attribute_index}].key",
                    minimum=1,
                    maximum=128,
                ),
                _safe_text(
                    attribute["value"],
                    f"relationships[{index}].attributes[{attribute_index}].value",
                    maximum=1000,
                ),
            )
        )
    if not attributes:
        raise ValueError(f"relationships[{index}].attributes is empty")
    return ToolRelationship(
        _string(
            raw["edge_id"],
            f"relationships[{index}].edge_id",
            minimum=1,
            maximum=160,
        ),
        _string(
            raw["unit_id"],
            f"relationships[{index}].unit_id",
            minimum=1,
        ),
        _string(
            raw["source_subject_id"],
            f"relationships[{index}].source_subject_id",
            minimum=1,
        ),
        _string(
            raw["target_subject_id"],
            f"relationships[{index}].target_subject_id",
            minimum=1,
        ),
        tuple(attributes),
        status,
        _evidence(
            raw["evidence"],
            f"relationships[{index}].evidence",
            minimum=1,
        ),
        _reason(status, raw["reason"], f"relationships[{index}].reason"),
    )


def parse_tool_call(name: str, arguments: object):
    if name not in TOOL_NAMES:
        raise ValueError(f"unknown tool: {name}")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as error:
            raise ValueError(f"arguments are not valid JSON: {error}") from error

    if name == "report_session_start":
        fields = (
            "target_ref",
            "target_sha256",
            "analysis_snapshot_id",
            "idempotency_key",
        )
        raw = _object(arguments, name, fields)
        target_hash = _string(raw["target_sha256"], "target_sha256")
        if SHA256.fullmatch(target_hash) is None:
            raise ValueError("target_sha256 is invalid")
        return StartToolCommand(
            _string(raw["target_ref"], "target_ref", minimum=1),
            target_hash,
            _string(
                raw["analysis_snapshot_id"],
                "analysis_snapshot_id",
                minimum=1,
            ),
            _string(
                raw["idempotency_key"],
                "idempotency_key",
                minimum=8,
                maximum=128,
            ),
        )

    if name == "report_chunk_submit":
        fields = (
            "session_id",
            "lease_id",
            "expected_state_version",
            "idempotency_key",
            "chunk_ordinal",
            "subject_declarations",
            "claims",
            "relationships",
            "continuation",
        )
        raw = _object(arguments, name, fields)
        continuation = _string(raw["continuation"], "continuation")
        if continuation not in {"more_for_same_lease", "lease_complete"}:
            raise ValueError("continuation is invalid")
        return SubmitToolCommand(
            _string(raw["session_id"], "session_id", minimum=1),
            _string(raw["lease_id"], "lease_id", minimum=1),
            _integer(raw["expected_state_version"], "expected_state_version"),
            _string(
                raw["idempotency_key"],
                "idempotency_key",
                minimum=8,
                maximum=128,
            ),
            _integer(raw["chunk_ordinal"], "chunk_ordinal"),
            tuple(
                _parse_subject(item, index)
                for index, item in enumerate(
                    _array(
                        raw["subject_declarations"],
                        "subject_declarations",
                        32,
                    )
                )
            ),
            tuple(
                _parse_claim(item, index)
                for index, item in enumerate(
                    _array(raw["claims"], "claims", 48)
                )
            ),
            tuple(
                _parse_relationship(item, index)
                for index, item in enumerate(
                    _array(raw["relationships"], "relationships", 16)
                )
            ),
            continuation,
        )

    if name == "report_session_sync":
        fields = ("session_id", "known_state_version", "request_id")
        raw = _object(arguments, name, fields)
        return SyncToolCommand(
            _string(raw["session_id"], "session_id", minimum=1),
            _integer(raw["known_state_version"], "known_state_version"),
            _string(
                raw["request_id"],
                "request_id",
                minimum=8,
                maximum=128,
            ),
        )

    fields = ("session_id", "expected_state_version", "idempotency_key")
    raw = _object(arguments, name, fields)
    return FinalizeToolCommand(
        _string(raw["session_id"], "session_id", minimum=1),
        _integer(raw["expected_state_version"], "expected_state_version"),
        _string(
            raw["idempotency_key"],
            "idempotency_key",
            minimum=8,
            maximum=128,
        ),
    )
