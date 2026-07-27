#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any

from repository_evidence import (
    ALLOWED_EVIDENCE_KINDS,
    ALLOWED_PROVENANCE,
    EVIDENCE_SCHEMA_VERSION,
    EXTRACTOR_NAME,
    EXTRACTOR_VERSION,
    LEGACY_V1_SCHEMA_VERSION,
    RUNTIME_EVIDENCE_KINDS,
    parse_positive_evidence,
    redact_sensitive_text,
    stable_evidence_id,
    stable_v1_evidence_id,
)


ALLOWED_STATUSES = {"confirmed", "inferred", "unknown", "conflict"}
EXTRACTOR_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def error(code: str, message: str, path: str) -> dict[str, str]:
    return {"code": code, "message": message, "path": path}


def is_safe_relative_path(value: Any, allow_dot: bool = False) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if value == ".":
        return allow_dot
    if "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() == value


def line_counts_by_path(snapshot: dict[str, Any], errors: list[dict[str, str]]) -> dict[str, int]:
    files = snapshot.get("files")
    if not isinstance(files, list):
        errors.append(error("invalid_schema", "snapshot.files must be a list", "$.snapshot.files"))
        return {}

    line_counts: dict[str, int] = {}
    for index, file_record in enumerate(files):
        path = file_record.get("path") if isinstance(file_record, dict) else None
        pointer = f"$.snapshot.files[{index}].path"
        if not is_safe_relative_path(path):
            errors.append(error("repository_root_escape", "snapshot file path must stay repository-relative", pointer))
            continue
        line_count = file_record.get("line_count")
        if not isinstance(line_count, int) or line_count < 0:
            errors.append(error("invalid_schema", "snapshot file line_count must be a non-negative integer", f"$.snapshot.files[{index}].line_count"))
            continue
        line_counts[path] = line_count
    return line_counts


def absence_from_legacy(record: dict[str, Any]) -> dict[str, str] | None:
    data = record.get("data")
    if isinstance(data, dict) and all(isinstance(data.get(key), str) for key in ("scope", "pattern", "result")):
        return {"scope": data["scope"], "pattern": data["pattern"], "result": data["result"]}
    evidence = record.get("evidence")
    if not isinstance(evidence, str):
        return None
    match = re.match(r"^검색\(scope=(.*), pattern=(.*), result=(.*)\)$", evidence)
    if not match:
        return None
    return {"scope": match.group(1), "pattern": match.group(2), "result": match.group(3)}


def normalize_legacy_payload(payload: dict[str, Any], errors: list[dict[str, str]]) -> dict[str, Any] | None:
    if payload.get("schema_version") != 1:
        return payload
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        errors.append(error("invalid_schema", "evidence must be a list", "$.evidence"))
        return None

    normalized = dict(payload)
    normalized["schema_version"] = EVIDENCE_SCHEMA_VERSION
    normalized_records: list[dict[str, Any]] = []
    for index, record in enumerate(evidence):
        pointer = f"$.evidence[{index}]"
        if not isinstance(record, dict):
            errors.append(error("invalid_schema", "evidence item must be an object", pointer))
            continue
        kind = record.get("kind")
        status = record.get("status")
        data = record.get("data")
        evidence_text = record.get("evidence")
        if not isinstance(kind, str) or not isinstance(status, str) or not isinstance(data, dict) or not isinstance(evidence_text, str):
            errors.append(error("invalid_schema", "legacy evidence item is missing kind, status, evidence, or data", pointer))
            continue
        normalized_record = dict(record)
        if kind == "absence":
            absence = absence_from_legacy(record)
            if absence is None:
                errors.append(error("invalid_absence", "legacy absence evidence must include scope, pattern, and result", pointer))
                continue
            normalized_record["absence"] = absence
            normalized_record.pop("source", None)
            source = None
        else:
            source = parse_positive_evidence(evidence_text)
            if source is None:
                errors.append(error("invalid_source", "legacy positive evidence must use path:line citation", pointer))
                continue
            normalized_record["source"] = source
            normalized_record.pop("absence", None)
            absence = None
        normalized_record["extractor"] = {"name": EXTRACTOR_NAME, "version": EXTRACTOR_VERSION}
        normalized_record["provenance"] = "INFERRED"
        normalized_record["id"] = stable_evidence_id(kind, status, data, source=source, absence=absence)
        normalized_records.append(normalized_record)
    normalized["evidence"] = normalized_records
    return normalized


def normalize_v1_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["schema_version"] = EVIDENCE_SCHEMA_VERSION
    evidence = payload.get("evidence")
    if isinstance(evidence, list):
        normalized["evidence"] = [
            {**record, "provenance": "INFERRED"} if isinstance(record, dict) else record
            for record in evidence
        ]
    return normalized


def iter_strings(value: Any, pointer: str = "$"):
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_strings(item, f"{pointer}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from iter_strings(item, f"{pointer}.{key}")


def contains_unredacted_secret(text: str) -> bool:
    return redact_sensitive_text(text) != text


def validate_source(
    record: dict[str, Any],
    index: int,
    line_counts: dict[str, int],
    errors: list[dict[str, str]],
) -> None:
    pointer = f"$.evidence[{index}].source"
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append(error("missing_source", "positive evidence must include source", pointer))
        return
    path = source.get("path")
    if not is_safe_relative_path(path):
        errors.append(error("repository_root_escape", "source path must stay repository-relative", f"{pointer}.path"))
        return
    if path not in line_counts:
        errors.append(error("source_path_not_in_snapshot", "source path must exist in snapshot.files", f"{pointer}.path"))
        return
    start_line = source.get("start_line")
    end_line = source.get("end_line")
    if (
        not isinstance(start_line, int)
        or not isinstance(end_line, int)
        or start_line < 1
        or end_line < start_line
        or end_line > line_counts[path]
    ):
        errors.append(error("source_span_out_of_bounds", "source line span must fit the snapshot file bounds", pointer))
        return
    expected_evidence = f"{path}:{start_line}" if start_line == end_line else f"{path}:{start_line}-{end_line}"
    if record.get("evidence") != expected_evidence:
        errors.append(error("citation_mismatch", "human-readable evidence must match structured source", f"$.evidence[{index}].evidence"))


def validate_absence(record: dict[str, Any], index: int, errors: list[dict[str, str]]) -> None:
    pointer = f"$.evidence[{index}].absence"
    if "source" in record:
        errors.append(error("invalid_absence", "absence evidence must not include a positive source", f"$.evidence[{index}].source"))
    absence = record.get("absence")
    if not isinstance(absence, dict):
        errors.append(error("invalid_absence", "absence evidence must include structured absence data", pointer))
        return
    scope = absence.get("scope")
    pattern = absence.get("pattern")
    result = absence.get("result")
    if not is_safe_relative_path(scope, allow_dot=True):
        errors.append(error("repository_root_escape", "absence scope must stay repository-relative", f"{pointer}.scope"))
    if not isinstance(pattern, str) or not pattern:
        errors.append(error("invalid_absence", "absence pattern must be a non-empty string", f"{pointer}.pattern"))
    if result != "없음":
        errors.append(error("invalid_absence", "absence result must be 없음", f"{pointer}.result"))


def validate_evidence_records(
    payload: dict[str, Any],
    line_counts: dict[str, int],
    errors: list[dict[str, str]],
    legacy_v1_identity: bool = False,
) -> None:
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        errors.append(error("invalid_schema", "evidence must be a list", "$.evidence"))
        return

    seen_ids: dict[str, int] = {}
    for index, record in enumerate(evidence):
        pointer = f"$.evidence[{index}]"
        if not isinstance(record, dict):
            errors.append(error("invalid_schema", "evidence item must be an object", pointer))
            continue

        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(error("invalid_schema", "evidence id must be a non-empty string", f"{pointer}.id"))
        elif identifier in seen_ids:
            errors.append(error("duplicate_id", f"evidence id duplicates item {seen_ids[identifier]}", f"{pointer}.id"))
        else:
            seen_ids[identifier] = index

        kind = record.get("kind")
        status = record.get("status")
        provenance = record.get("provenance")
        data = record.get("data")
        if kind not in ALLOWED_EVIDENCE_KINDS:
            errors.append(error("unknown_evidence_kind", "evidence kind is not in the repository evidence enum", f"{pointer}.kind"))
        if status not in ALLOWED_STATUSES:
            errors.append(error("unknown_evidence_status", "evidence status is not in the repository evidence enum", f"{pointer}.status"))
        if provenance not in ALLOWED_PROVENANCE:
            errors.append(error("invalid_provenance", "evidence provenance must be EXTRACTED or INFERRED", f"{pointer}.provenance"))
        elif provenance == "EXTRACTED" and kind not in RUNTIME_EVIDENCE_KINDS:
            errors.append(error("invalid_provenance", "EXTRACTED provenance is reserved for runtime evidence kinds", f"{pointer}.provenance"))
        if not isinstance(data, dict):
            errors.append(error("invalid_schema", "evidence data must be an object", f"{pointer}.data"))
            data = {}

        extractor = record.get("extractor")
        if (
            not isinstance(extractor, dict)
            or not isinstance(extractor.get("name"), str)
            or not isinstance(extractor.get("version"), str)
            or not EXTRACTOR_VERSION_PATTERN.match(extractor["version"])
        ):
            errors.append(error("invalid_extractor", "extractor must include name and semantic version", f"{pointer}.extractor"))

        if kind == "absence":
            validate_absence(record, index, errors)
            source = None
            absence = record.get("absence") if isinstance(record.get("absence"), dict) else None
        else:
            validate_source(record, index, line_counts, errors)
            source = record.get("source") if isinstance(record.get("source"), dict) else None
            absence = None

        if isinstance(identifier, str) and isinstance(kind, str) and isinstance(status, str):
            expected_id = (
                stable_v1_evidence_id(kind, status, data, source=source, absence=absence)
                if legacy_v1_identity
                else stable_evidence_id(kind, status, data, source=source, absence=absence, provenance=str(provenance))
            )
            if identifier != expected_id:
                errors.append(error("stable_id_mismatch", "evidence id does not match canonical identity", f"{pointer}.id"))

        for string_path, text in iter_strings(record, pointer):
            if contains_unredacted_secret(text):
                errors.append(error("secret_value_leak", "evidence contains an unredacted secret-like value", string_path))


def validate_payload(raw_payload: Any) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(raw_payload, dict):
        return [error("invalid_schema", "artifact root must be an object", "$")]

    schema_version = raw_payload.get("schema_version")
    if schema_version not in {EVIDENCE_SCHEMA_VERSION, LEGACY_V1_SCHEMA_VERSION, 1}:
        errors.append(error("unsupported_schema_version", "unsupported repository evidence schema version", "$.schema_version"))
        return errors

    legacy_v1_identity = schema_version == LEGACY_V1_SCHEMA_VERSION
    payload = (
        normalize_legacy_payload(raw_payload, errors)
        if schema_version == 1
        else normalize_v1_payload(raw_payload)
        if legacy_v1_identity
        else raw_payload
    )
    if payload is None or errors:
        return errors
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        errors.append(error("invalid_schema", "snapshot must be an object", "$.snapshot"))
        return errors

    line_counts = line_counts_by_path(snapshot, errors)
    validate_evidence_records(payload, line_counts, errors, legacy_v1_identity=legacy_v1_identity)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate repository evidence JSON artifacts.")
    parser.add_argument("artifact", type=Path, help="Path to repository evidence JSON")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors = [error("invalid_json", str(exc), "$")]
    else:
        errors = validate_payload(payload)

    response = {"valid": not errors, "errors": errors}
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
