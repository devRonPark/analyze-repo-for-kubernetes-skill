from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import sqlite3
from typing import Mapping

import report_contract
from report_diagnostics import Diagnostic
from report_lease_planner import (
    DynamicLeasePlanner,
    LeaseMetrics,
    LeasePlanningSnapshot,
)
import report_records
from report_session_models import Lease, SessionState
from report_session_store import SQLiteReportSessionStore
from report_work_units import (
    AnalysisSnapshot,
    Coverage,
    WorkUnit,
    build_work_units,
    calculate_coverage,
    diagnostics_to_repair_units,
)


MAX_REPAIR_ROUNDS = 3


@dataclass(frozen=True)
class StartCommand:
    session_id: str
    idempotency_key: str
    analysis_snapshot_id: str
    target_hash: str
    mode: str
    analysis_snapshot: AnalysisSnapshot
    initial_payload: object


@dataclass(frozen=True)
class SubmitChunkCommand:
    session_id: str
    lease_id: str
    chunk_ordinal: int
    idempotency_key: str
    expected_state_version: int
    unit_ids: tuple[str, ...]
    payload: object
    transport_status: str = "complete"
    observed_duration: float = 16.0
    payload_hash: str = ""
    continuation: str = "lease_complete"


@dataclass(frozen=True)
class SyncCommand:
    session_id: str


@dataclass(frozen=True)
class ToolResult:
    status: str
    session_id: str
    state: str
    state_version: int
    lease: Lease | None
    coverage: tuple[int, int]
    message: str = ""
    artifact: Mapping[str, object] | None = None


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _lease_from_row(row: sqlite3.Row | None) -> Lease | None:
    if row is None:
        return None
    return Lease(
        lease_id=row["lease_id"],
        session_id=row["session_id"],
        allowed_unit_ids=tuple(json.loads(row["allowed_unit_ids_json"])),
        allowed_fields=tuple(
            (item[0], tuple(item[1]))
            for item in json.loads(row["allowed_fields_json"])
        ),
        output_token_budget=row["output_token_budget"],
        max_argument_bytes=row["max_argument_bytes"],
        max_claims=row["max_claims"],
        max_relationships=row["max_relationships"],
        retry_count=row["retry_count"],
        no_progress_count=row["no_progress_count"],
        status=row["status"],
    )


def _lease_to_dict(lease: Lease | None) -> dict[str, object] | None:
    return asdict(lease) if lease is not None else None


def _lease_from_dict(payload: Mapping[str, object] | None) -> Lease | None:
    if payload is None:
        return None
    return Lease(
        lease_id=str(payload["lease_id"]),
        session_id=str(payload["session_id"]),
        allowed_unit_ids=tuple(payload["allowed_unit_ids"]),
        allowed_fields=tuple(
            (str(item[0]), tuple(item[1]))
            for item in payload.get("allowed_fields", ())
        ),
        output_token_budget=int(payload["output_token_budget"]),
        max_argument_bytes=int(payload["max_argument_bytes"]),
        max_claims=int(payload["max_claims"]),
        max_relationships=int(payload["max_relationships"]),
        retry_count=int(payload.get("retry_count", 0)),
        no_progress_count=int(payload.get("no_progress_count", 0)),
        status=str(payload.get("status", "ACTIVE")),
    )


def _result_json(result: ToolResult) -> str:
    return _canonical_json(
        {
            "status": result.status,
            "session_id": result.session_id,
            "state": result.state,
            "state_version": result.state_version,
            "lease": _lease_to_dict(result.lease),
            "coverage": result.coverage,
            "message": result.message,
            "artifact": result.artifact,
        }
    )


def _result_from_json(raw: str) -> ToolResult:
    payload = json.loads(raw)
    return ToolResult(
        status=payload["status"],
        session_id=payload["session_id"],
        state=payload["state"],
        state_version=payload["state_version"],
        lease=_lease_from_dict(payload["lease"]),
        coverage=tuple(payload["coverage"]),
        message=payload["message"],
        artifact=payload.get("artifact"),
    )


def _claim_payload(claim: report_records.Claim) -> dict[str, object]:
    return {
        "claim_id": claim.claim_id,
        "section_key": claim.section_key,
        "subject_id": claim.subject_id,
        "field": claim.field,
        "value": claim.value,
        "status": claim.status,
        "evidence": claim.evidence,
        "reason": claim.reason,
    }


def _relationship_payload(
    relationship: report_records.Relationship,
) -> dict[str, object]:
    return {
        "edge_id": relationship.edge_id,
        "source_subject_id": relationship.source_subject_id,
        "target_subject_id": relationship.target_subject_id,
        "attributes": dict(relationship.attributes),
        "status": relationship.status,
        "evidence": relationship.evidence,
        "reason": relationship.reason,
    }


def _document_payload(
    document: report_records.ReportDocument,
) -> dict[str, object]:
    return {
        "mode": document.mode,
        "subjects": [asdict(subject) for subject in document.subjects],
        "claims": [_claim_payload(claim) for claim in document.claims],
        "relationships": [
            _relationship_payload(relationship)
            for relationship in document.relationships
        ],
    }


class ReportSessionService:
    def __init__(
        self,
        store: SQLiteReportSessionStore,
        *,
        contract: report_contract.ReportContract | None = None,
        planner: DynamicLeasePlanner | None = None,
        lifecycle: object | None = None,
    ):
        self.store = store
        self.contract = contract or report_contract.load_report_contract()
        self.planner = planner or DynamicLeasePlanner()
        self.lifecycle = lifecycle

    def _parse_payload(
        self, payload: object
    ) -> report_records.ReportDocument:
        parsed = json.loads(payload) if isinstance(payload, str) else payload
        return report_records.parse_report_document(parsed)

    def _load_units(
        self, connection: sqlite3.Connection, session_id: str
    ) -> tuple[WorkUnit, ...]:
        rows = connection.execute(
            "SELECT * FROM work_units WHERE session_id = ? ORDER BY unit_id",
            (session_id,),
        )
        units = []
        for row in rows:
            relationship_edge_id = (
                row["unit_id"].removeprefix("relationship:")
                if row["unit_type"] == "relationship"
                else None
            )
            units.append(
                WorkUnit(
                    unit_id=row["unit_id"],
                    unit_type=row["unit_type"],
                    subject_id=row["subject_id"],
                    required_fields=tuple(
                        json.loads(row["required_fields_json"])
                    ),
                    relationship_edge_id=relationship_edge_id,
                )
            )
        return tuple(units)

    def _load_document(
        self, connection: sqlite3.Connection, session_id: str
    ) -> report_records.ReportDocument:
        session = connection.execute(
            "SELECT mode FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        subjects = [
            {
                "subject_id": row["subject_id"],
                "kind": row["kind"],
                "display_name": row["display_name"],
            }
            for row in connection.execute(
                "SELECT * FROM subjects WHERE session_id = ? ORDER BY subject_id",
                (session_id,),
            )
        ]
        claims = [
            json.loads(row["payload_json"])
            for row in connection.execute(
                "SELECT payload_json FROM claims "
                "WHERE session_id = ? ORDER BY claim_id",
                (session_id,),
            )
        ]
        relationships = [
            json.loads(row["payload_json"])
            for row in connection.execute(
                "SELECT payload_json FROM relationships "
                "WHERE session_id = ? ORDER BY edge_id",
                (session_id,),
            )
        ]
        return report_records.parse_report_document(
            {
                "mode": session["mode"],
                "subjects": subjects,
                "claims": claims,
                "relationships": relationships,
            }
        )

    def _insert_document(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        document: report_records.ReportDocument,
    ) -> None:
        for subject in document.subjects:
            existing = connection.execute(
                "SELECT kind, display_name FROM subjects "
                "WHERE session_id = ? AND subject_id = ?",
                (session_id, subject.subject_id),
            ).fetchone()
            if existing is not None:
                if (existing["kind"], existing["display_name"]) != (
                    subject.kind,
                    subject.display_name,
                ):
                    raise ValueError(
                        f"subject definition conflict: {subject.subject_id}"
                    )
                continue
            connection.execute(
                "INSERT INTO subjects("
                "session_id, subject_id, kind, display_name, payload_json"
                ") VALUES (?, ?, ?, ?, '{}')",
                (
                    session_id,
                    subject.subject_id,
                    subject.kind,
                    subject.display_name,
                ),
            )
        for claim in document.claims:
            connection.execute(
                "INSERT INTO claims("
                "session_id, claim_id, subject_id, payload_json"
                ") VALUES (?, ?, ?, ?)",
                (
                    session_id,
                    claim.claim_id,
                    claim.subject_id,
                    _canonical_json(_claim_payload(claim)),
                ),
            )
        for relationship in document.relationships:
            connection.execute(
                "INSERT INTO relationships("
                "session_id, edge_id, payload_json"
                ") VALUES (?, ?, ?)",
                (
                    session_id,
                    relationship.edge_id,
                    _canonical_json(_relationship_payload(relationship)),
                ),
            )

    def _insert_lease(
        self, connection: sqlite3.Connection, lease: Lease
    ) -> None:
        connection.execute(
            """
            INSERT INTO leases(
                session_id,
                lease_id,
                allowed_unit_ids_json,
                allowed_fields_json,
                output_token_budget,
                max_argument_bytes,
                max_claims,
                max_relationships,
                retry_count,
                no_progress_count,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lease.session_id,
                lease.lease_id,
                _canonical_json(lease.allowed_unit_ids),
                _canonical_json(lease.allowed_fields),
                lease.output_token_budget,
                lease.max_argument_bytes,
                lease.max_claims,
                lease.max_relationships,
                lease.retry_count,
                lease.no_progress_count,
                lease.status,
            ),
        )

    def _active_lease(
        self, connection: sqlite3.Connection, session_id: str
    ) -> Lease | None:
        return _lease_from_row(
            connection.execute(
                "SELECT * FROM leases "
                "WHERE session_id = ? AND status = 'ACTIVE'",
                (session_id,),
            ).fetchone()
        )

    def _update_coverage(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        coverage: Coverage,
    ) -> None:
        missing = set(coverage.missing_unit_ids)
        connection.executemany(
            "UPDATE work_units SET status = ? "
            "WHERE session_id = ? AND unit_id = ?",
            (
                (
                    "PENDING" if unit_id in missing else "COMPLETE",
                    session_id,
                    unit_id,
                )
                for unit_id in (
                    row[0]
                    for row in connection.execute(
                        "SELECT unit_id FROM work_units WHERE session_id = ?",
                        (session_id,),
                    )
                )
            ),
        )

    def _pending_units(
        self,
        units: tuple[WorkUnit, ...],
        coverage: Coverage,
    ) -> tuple[WorkUnit, ...]:
        missing_fields = dict(coverage.missing_fields)
        pending = []
        for unit in units:
            if unit.unit_id not in missing_fields:
                continue
            pending.append(
                unit
                if unit.relationship_edge_id is not None
                else replace(
                    unit,
                    required_fields=missing_fields[unit.unit_id],
                )
            )
        return tuple(pending)

    def start(self, command: StartCommand) -> ToolResult:
        if command.mode != command.analysis_snapshot.mode:
            raise ValueError("start mode와 analysis snapshot mode가 다릅니다")
        document = self._parse_payload(command.initial_payload)
        if document.mode != command.mode:
            raise ValueError("start mode와 initial payload mode가 다릅니다")
        diagnostics = report_records.validate_document(
            document, self.contract
        )
        if diagnostics:
            raise ValueError(
                "; ".join(item.message for item in diagnostics)
            )
        units = build_work_units(self.contract, command.analysis_snapshot)
        coverage = calculate_coverage(units, document)

        def operation(connection: sqlite3.Connection) -> ToolResult:
            existing = connection.execute(
                "SELECT result_json FROM start_results "
                "WHERE idempotency_key = ?",
                (command.idempotency_key,),
            ).fetchone()
            if existing is not None:
                return _result_from_json(existing["result_json"])
            connection.execute(
                """
                INSERT INTO sessions(
                    session_id,
                    start_idempotency_key,
                    analysis_snapshot_id,
                    target_hash,
                    mode,
                    state,
                    state_version
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    command.session_id,
                    command.idempotency_key,
                    command.analysis_snapshot_id,
                    command.target_hash,
                    command.mode,
                    (
                        SessionState.READY.value
                        if coverage.rendering_ready
                        else SessionState.COLLECTING.value
                    ),
                ),
            )
            connection.executemany(
                """
                INSERT INTO work_units(
                    session_id,
                    unit_id,
                    unit_type,
                    subject_id,
                    required_fields_json,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        command.session_id,
                        unit.unit_id,
                        unit.unit_type,
                        unit.subject_id,
                        _canonical_json(unit.required_fields),
                        (
                            "PENDING"
                            if unit.unit_id in coverage.missing_unit_ids
                            else "COMPLETE"
                        ),
                    )
                    for unit in units
                ),
            )
            self._insert_document(
                connection, command.session_id, document
            )
            lease = None
            if not coverage.rendering_ready:
                lease = self.planner.issue_or_resume(
                    LeasePlanningSnapshot(
                        session_id=command.session_id,
                        state_version=0,
                        pending_units=self._pending_units(units, coverage),
                    ),
                    LeaseMetrics(),
                )
                self._insert_lease(connection, lease)
            result = ToolResult(
                status=(
                    "rendering_ready"
                    if coverage.rendering_ready
                    else "lease_issued"
                ),
                session_id=command.session_id,
                state=(
                    SessionState.READY.value
                    if coverage.rendering_ready
                    else SessionState.COLLECTING.value
                ),
                state_version=0,
                lease=lease,
                coverage=(coverage.completed_units, coverage.total_units),
            )
            connection.execute(
                "INSERT INTO start_results("
                "session_id, idempotency_key, result_json"
                ") VALUES (?, ?, ?)",
                (
                    command.session_id,
                    command.idempotency_key,
                    _result_json(result),
                ),
            )
            connection.execute(
                "INSERT INTO audit_events("
                "session_id, event_type, state_version, details_json"
                ") VALUES (?, 'SESSION_STARTED', 0, ?)",
                (
                    command.session_id,
                    _canonical_json({"status": result.status}),
                ),
            )
            return result

        return self.store.transact(operation)

    def submit(self, command: SubmitChunkCommand) -> ToolResult:
        if command.transport_status != "complete":
            return self._current_result(
                command.session_id,
                "retryable",
                f"transport가 완전하지 않습니다: {command.transport_status}",
            )
        try:
            document = self._parse_payload(command.payload)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            return self._current_result(
                command.session_id,
                "retryable",
                f"malformed payload: {error}",
            )
        diagnostics = report_records.validate_document(
            document, self.contract
        )
        if diagnostics:
            return self._current_result(
                command.session_id,
                "rejected",
                "; ".join(item.message for item in diagnostics),
            )

        def operation(connection: sqlite3.Connection) -> ToolResult:
            duplicate = connection.execute(
                "SELECT result_json FROM chunk_results "
                "WHERE session_id = ? AND idempotency_key = ?",
                (command.session_id, command.idempotency_key),
            ).fetchone()
            if duplicate is not None:
                return _result_from_json(duplicate["result_json"])
            session = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (command.session_id,),
            ).fetchone()
            if session is None:
                raise KeyError(
                    f"report session을 찾을 수 없습니다: {command.session_id}"
                )
            current_lease = self._active_lease(
                connection, command.session_id
            )
            current_coverage = calculate_coverage(
                self._load_units(connection, command.session_id),
                self._load_document(connection, command.session_id),
            )
            if document.mode != session["mode"]:
                return ToolResult(
                    "rejected",
                    command.session_id,
                    session["state"],
                    session["state_version"],
                    current_lease,
                    (
                        current_coverage.completed_units,
                        current_coverage.total_units,
                    ),
                    "session mode와 payload mode가 다릅니다",
                )
            if session["state_version"] != command.expected_state_version:
                return ToolResult(
                    "sync_required",
                    command.session_id,
                    session["state"],
                    session["state_version"],
                    current_lease,
                    (
                        current_coverage.completed_units,
                        current_coverage.total_units,
                    ),
                    "expected_state_version이 stale합니다",
                )
            if (
                current_lease is None
                or current_lease.lease_id != command.lease_id
            ):
                return ToolResult(
                    "rejected",
                    command.session_id,
                    session["state"],
                    session["state_version"],
                    current_lease,
                    (
                        current_coverage.completed_units,
                        current_coverage.total_units,
                    ),
                    "active lease가 일치하지 않습니다",
                )
            if not set(command.unit_ids).issubset(
                current_lease.allowed_unit_ids
            ):
                return ToolResult(
                    "rejected",
                    command.session_id,
                    session["state"],
                    session["state_version"],
                    current_lease,
                    (
                        current_coverage.completed_units,
                        current_coverage.total_units,
                    ),
                    "허용되지 않은 work-unit입니다",
                )
            if len(document.claims) > current_lease.max_claims:
                return ToolResult(
                    "rejected",
                    command.session_id,
                    session["state"],
                    session["state_version"],
                    current_lease,
                    (
                        current_coverage.completed_units,
                        current_coverage.total_units,
                    ),
                    "lease claim cap을 초과했습니다",
                )
            if (
                len(document.relationships)
                > current_lease.max_relationships
            ):
                return ToolResult(
                    "rejected",
                    command.session_id,
                    session["state"],
                    session["state_version"],
                    current_lease,
                    (
                        current_coverage.completed_units,
                        current_coverage.total_units,
                    ),
                    "lease relationship cap을 초과했습니다",
                )
            argument_size = len(
                _canonical_json(_document_payload(document)).encode("utf-8")
            )
            if argument_size > current_lease.max_argument_bytes:
                return ToolResult(
                    "rejected",
                    command.session_id,
                    session["state"],
                    session["state_version"],
                    current_lease,
                    (
                        current_coverage.completed_units,
                        current_coverage.total_units,
                    ),
                    "lease argument byte cap을 초과했습니다",
                )
            allowed_fields = {
                field
                for unit_id, fields in current_lease.allowed_fields
                if unit_id in command.unit_ids
                for field in fields
            }
            if any(
                claim.field not in allowed_fields
                for claim in document.claims
            ):
                return ToolResult(
                    "rejected",
                    command.session_id,
                    session["state"],
                    session["state_version"],
                    current_lease,
                    (
                        current_coverage.completed_units,
                        current_coverage.total_units,
                    ),
                    "lease가 허용하지 않은 claim field입니다",
                )
            allowed_relationships = {
                unit_id.removeprefix("relationship:")
                for unit_id in command.unit_ids
                if unit_id.startswith("relationship:")
            }
            if any(
                relationship.edge_id not in allowed_relationships
                for relationship in document.relationships
            ):
                return ToolResult(
                    "rejected",
                    command.session_id,
                    session["state"],
                    session["state_version"],
                    current_lease,
                    (
                        current_coverage.completed_units,
                        current_coverage.total_units,
                    ),
                    "lease가 허용하지 않은 relationship입니다",
                )

            self._insert_document(
                connection, command.session_id, document
            )
            units = self._load_units(connection, command.session_id)
            updated_coverage = calculate_coverage(
                units,
                self._load_document(connection, command.session_id),
            )
            self._update_coverage(
                connection, command.session_id, updated_coverage
            )
            connection.execute(
                "UPDATE leases SET status = 'COMPLETE', "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE session_id = ? AND lease_id = ?",
                (command.session_id, command.lease_id),
            )
            next_version = session["state_version"] + 1
            next_lease = None
            if updated_coverage.rendering_ready:
                next_state = SessionState.READY.value
                status = "rendering_ready"
            else:
                next_state = SessionState.COLLECTING.value
                status = "lease_issued"
                adjusted = self.planner.record_success(
                    current_lease,
                    observed_duration=command.observed_duration,
                    coverage_increased=(
                        updated_coverage.completed_units
                        > current_coverage.completed_units
                    ),
                    repeated_payload=False,
                )
                next_lease = self.planner.issue_or_resume(
                    LeasePlanningSnapshot(
                        session_id=command.session_id,
                        state_version=next_version,
                        pending_units=self._pending_units(
                            units, updated_coverage
                        ),
                    ),
                    LeaseMetrics(
                        current_budget=adjusted.output_token_budget
                    ),
                )
                self._insert_lease(connection, next_lease)
            connection.execute(
                "UPDATE sessions SET state = ?, state_version = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (next_state, next_version, command.session_id),
            )
            result = ToolResult(
                status,
                command.session_id,
                next_state,
                next_version,
                next_lease,
                (
                    updated_coverage.completed_units,
                    updated_coverage.total_units,
                ),
            )
            connection.execute(
                """
                INSERT INTO chunk_results(
                    session_id,
                    lease_id,
                    chunk_ordinal,
                    idempotency_key,
                    payload_hash,
                    result_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    command.session_id,
                    command.lease_id,
                    command.chunk_ordinal,
                    command.idempotency_key,
                    command.payload_hash,
                    _result_json(result),
                ),
            )
            connection.execute(
                "INSERT INTO audit_events("
                "session_id, event_type, state_version, details_json"
                ") VALUES (?, 'CHUNK_ACCEPTED', ?, ?)",
                (
                    command.session_id,
                    next_version,
                    _canonical_json(
                        {
                            "lease_id": command.lease_id,
                            "chunk_ordinal": command.chunk_ordinal,
                        }
                    ),
                ),
            )
            return result

        try:
            return self.store.transact(operation)
        except (sqlite3.IntegrityError, ValueError) as error:
            return self._current_result(
                command.session_id, "rejected", str(error)
            )

    def _remove_repair_records(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        diagnostics: tuple[Diagnostic, ...],
        repair_units: tuple[WorkUnit, ...],
    ) -> None:
        relationship_ids = {
            diagnostic.subject_id
            for diagnostic in diagnostics
            if diagnostic.section_key == "relationships"
            and diagnostic.subject_id
        }
        if relationship_ids:
            connection.executemany(
                "DELETE FROM relationships "
                "WHERE session_id = ? AND edge_id = ?",
                (
                    (session_id, edge_id)
                    for edge_id in sorted(relationship_ids)
                ),
            )

        repair_fields = {
            (unit.subject_id, field)
            for unit in repair_units
            if unit.relationship_edge_id is None
            for field in unit.required_fields
        }
        claim_ids = []
        for row in connection.execute(
            "SELECT claim_id, payload_json FROM claims "
            "WHERE session_id = ?",
            (session_id,),
        ):
            payload = json.loads(row["payload_json"])
            subject_id = payload.get("subject_id")
            field = payload.get("field")
            if (subject_id, field) in repair_fields or (
                (None, field) in repair_fields
            ):
                claim_ids.append(row["claim_id"])
        connection.executemany(
            "DELETE FROM claims WHERE session_id = ? AND claim_id = ?",
            ((session_id, claim_id) for claim_id in claim_ids),
        )

    def route_repair_diagnostics(
        self,
        session_id: str,
        diagnostics: tuple[Diagnostic, ...],
    ) -> ToolResult:
        details = [diagnostic.to_dict() for diagnostic in diagnostics]

        def operation(connection: sqlite3.Connection) -> ToolResult:
            session = connection.execute(
                "SELECT state, state_version FROM sessions "
                "WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if session is None:
                raise KeyError(
                    f"report session을 찾을 수 없습니다: {session_id}"
                )
            active = self._active_lease(connection, session_id)
            if active is not None:
                completed, total = (
                    connection.execute(
                        "SELECT COUNT(*) FROM work_units "
                        "WHERE session_id = ? AND status = 'COMPLETE'",
                        (session_id,),
                    ).fetchone()[0],
                    connection.execute(
                        "SELECT COUNT(*) FROM work_units "
                        "WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()[0],
                )
                return ToolResult(
                    "lease_issued",
                    session_id,
                    session["state"],
                    session["state_version"],
                    active,
                    (completed, total),
                )
            if session["state"] != SessionState.REPAIRING.value:
                completed, total = (
                    connection.execute(
                        "SELECT COUNT(*) FROM work_units "
                        "WHERE session_id = ? AND status = 'COMPLETE'",
                        (session_id,),
                    ).fetchone()[0],
                    connection.execute(
                        "SELECT COUNT(*) FROM work_units "
                        "WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()[0],
                )
                return ToolResult(
                    "rejected",
                    session_id,
                    session["state"],
                    session["state_version"],
                    None,
                    (completed, total),
                    "REPAIRING session만 repair lease를 발급할 수 있습니다",
                )

            units = self._load_units(connection, session_id)
            repair_units = diagnostics_to_repair_units(
                diagnostics, units
            )
            repair_rounds = connection.execute(
                "SELECT COUNT(*) FROM audit_events "
                "WHERE session_id = ? "
                "AND event_type = 'REPAIR_LEASE_ISSUED'",
                (session_id,),
            ).fetchone()[0]
            if not repair_units or repair_rounds >= MAX_REPAIR_ROUNDS:
                version = session["state_version"] + 1
                reason = (
                    "validation diagnostic을 repair work-unit에 "
                    "안전하게 연결할 수 없습니다"
                    if not repair_units
                    else "repair budget을 초과했습니다"
                )
                connection.execute(
                    "UPDATE sessions SET state = ?, state_version = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                    (SessionState.FAILED.value, version, session_id),
                )
                connection.execute(
                    "INSERT INTO audit_events("
                    "session_id, event_type, state_version, details_json"
                    ") VALUES (?, 'REPAIR_FAILED', ?, ?)",
                    (
                        session_id,
                        version,
                        _canonical_json(
                            {
                                "reason": reason,
                                "diagnostics": details,
                                "repair_rounds": repair_rounds,
                            }
                        ),
                    ),
                )
                completed, total = (
                    connection.execute(
                        "SELECT COUNT(*) FROM work_units "
                        "WHERE session_id = ? AND status = 'COMPLETE'",
                        (session_id,),
                    ).fetchone()[0],
                    connection.execute(
                        "SELECT COUNT(*) FROM work_units "
                        "WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()[0],
                )
                return ToolResult(
                    "failed",
                    session_id,
                    SessionState.FAILED.value,
                    version,
                    None,
                    (completed, total),
                    reason,
                )

            self._remove_repair_records(
                connection, session_id, diagnostics, repair_units
            )
            connection.executemany(
                "UPDATE work_units SET status = 'PENDING' "
                "WHERE session_id = ? AND unit_id = ?",
                (
                    (session_id, unit.unit_id)
                    for unit in repair_units
                ),
            )
            version = session["state_version"] + 1
            lease = self.planner.issue_or_resume(
                LeasePlanningSnapshot(
                    session_id=session_id,
                    state_version=session["state_version"],
                    pending_units=repair_units,
                ),
                LeaseMetrics(),
            )
            self._insert_lease(connection, lease)
            connection.execute(
                "UPDATE sessions SET state = ?, state_version = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (SessionState.COLLECTING.value, version, session_id),
            )
            connection.execute(
                "INSERT INTO audit_events("
                "session_id, event_type, state_version, details_json"
                ") VALUES (?, 'REPAIR_LEASE_ISSUED', ?, ?)",
                (
                    session_id,
                    version,
                    _canonical_json(
                        {
                            "diagnostics": details,
                            "unit_ids": lease.allowed_unit_ids,
                            "repair_round": repair_rounds + 1,
                        }
                    ),
                ),
            )
            completed, total = (
                connection.execute(
                    "SELECT COUNT(*) FROM work_units "
                    "WHERE session_id = ? AND status = 'COMPLETE'",
                    (session_id,),
                ).fetchone()[0],
                connection.execute(
                    "SELECT COUNT(*) FROM work_units "
                    "WHERE session_id = ?",
                    (session_id,),
                ).fetchone()[0],
            )
            return ToolResult(
                "lease_issued",
                session_id,
                SessionState.COLLECTING.value,
                version,
                lease,
                (completed, total),
            )

        return self.store.transact(operation)

    def finalize(self, command: object) -> ToolResult:
        if self.lifecycle is None:
            raise RuntimeError("report lifecycle이 구성되지 않았습니다")
        result = self.lifecycle.finalize(
            session_id=command.session_id,
            expected_state_version=command.expected_state_version,
            idempotency_key=command.idempotency_key,
        )
        if result.status != "validation_failed":
            return result
        try:
            raw_diagnostics = json.loads(result.message)
            diagnostics = tuple(
                Diagnostic(
                    code=str(item["code"]),
                    section_key=str(item["section_key"]),
                    subject_id=str(item["subject_id"]),
                    field=str(item["field"]),
                    message=str(item["message"]),
                )
                for item in raw_diagnostics
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            diagnostics = (
                Diagnostic(
                    "VALIDATOR_INFRASTRUCTURE_ERROR",
                    "",
                    "",
                    "",
                    "structured validator diagnostics를 읽을 수 없습니다",
                ),
            )
        routed = self.route_repair_diagnostics(
            command.session_id, diagnostics
        )
        self.lifecycle.finish_repair_routing(command.session_id)
        return routed

    def _current_result(
        self, session_id: str, status: str, message: str
    ) -> ToolResult:
        snapshot = self.store.load(session_id)
        completed, total = self.store.transact(
            lambda connection: (
                connection.execute(
                    "SELECT COUNT(*) FROM work_units "
                    "WHERE session_id = ? AND status = 'COMPLETE'",
                    (session_id,),
                ).fetchone()[0],
                connection.execute(
                    "SELECT COUNT(*) FROM work_units WHERE session_id = ?",
                    (session_id,),
                ).fetchone()[0],
            )
        )
        return ToolResult(
            status,
            session_id,
            snapshot.state.value,
            snapshot.state_version,
            snapshot.active_lease,
            (completed, total),
            message,
        )

    def sync(self, command: SyncCommand) -> ToolResult:
        snapshot = self.store.load(command.session_id)
        status = (
            "rendering_ready"
            if snapshot.state is SessionState.READY
            else "lease_issued"
        )
        return self._current_result(command.session_id, status, "")

    def record_transport_failure(
        self,
        session_id: str,
        lease_id: str,
        code: str,
    ) -> ToolResult:
        def operation(connection: sqlite3.Connection) -> ToolResult:
            session = connection.execute(
                "SELECT state, state_version FROM sessions "
                "WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if session is None:
                raise KeyError(
                    f"report session을 찾을 수 없습니다: {session_id}"
                )
            current = self._active_lease(connection, session_id)
            if current is None or current.lease_id != lease_id:
                raise ValueError("active lease가 일치하지 않습니다")
            adjusted = self.planner.record_transport_failure(current)
            connection.execute(
                "UPDATE leases SET allowed_unit_ids_json = ?, "
                "allowed_fields_json = ?, output_token_budget = ?, "
                "retry_count = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE session_id = ? AND lease_id = ?",
                (
                    _canonical_json(adjusted.allowed_unit_ids),
                    _canonical_json(adjusted.allowed_fields),
                    adjusted.output_token_budget,
                    adjusted.retry_count,
                    session_id,
                    lease_id,
                ),
            )
            completed, total = (
                connection.execute(
                    "SELECT COUNT(*) FROM work_units "
                    "WHERE session_id = ? AND status = 'COMPLETE'",
                    (session_id,),
                ).fetchone()[0],
                connection.execute(
                    "SELECT COUNT(*) FROM work_units WHERE session_id = ?",
                    (session_id,),
                ).fetchone()[0],
            )
            connection.execute(
                "INSERT INTO audit_events("
                "session_id, event_type, state_version, details_json"
                ") VALUES (?, 'TRANSPORT_FAILURE', ?, ?)",
                (
                    session_id,
                    session["state_version"],
                    _canonical_json(
                        {
                            "code": code,
                            "lease_id": lease_id,
                            "retry_count": adjusted.retry_count,
                        }
                    ),
                ),
            )
            return ToolResult(
                "retryable",
                session_id,
                session["state"],
                session["state_version"],
                adjusted,
                (completed, total),
                code,
            )

        return self.store.transact(operation)
