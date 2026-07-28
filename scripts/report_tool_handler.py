from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Callable, Mapping, Protocol

from report_session_service import (
    StartCommand,
    SubmitChunkCommand,
    SyncCommand,
    ToolResult,
)
from report_tool_commands import (
    FinalizeToolCommand,
    StartToolCommand,
    SubmitToolCommand,
    SyncToolCommand,
    parse_tool_call,
)


SECTION_KEYS = {
    "scope": "scope",
    "candidate_inventory": "candidate_inventory",
    "component_runtime": "component_cards",
    "component_config_state": "component_cards",
    "component_k8s_input": "component_cards",
    "component_gap": "component_cards",
    "deployment_evidence": "deployment_evidence",
    "configuration_detail": "configuration_detail",
    "exclusion": "exclusions_and_blockers",
    "blocker": "exclusions_and_blockers",
    "readiness": "readiness",
}
SUBJECT_KINDS = {
    "repository_dependency": "dependency",
    "external_dependency": "dependency",
}
ERROR_STATUSES = {"rejected", "retryable", "sync_required", "failed"}


class CompleteToolCall(Protocol):
    name: str
    arguments: object


StartResolver = Callable[[StartToolCommand], StartCommand]


def _empty_envelope(
    *,
    session_id: str = "",
    diagnostic_code: str,
    message: str,
) -> dict[str, object]:
    return {
        "ok": False,
        "session_id": session_id,
        "state": "",
        "state_version": -1,
        "next_action": "sync",
        "lease": None,
        "progress": {"completed_units": 0, "known_units": 0},
        "diagnostics": [
            {
                "code": diagnostic_code,
                "message": message.replace("\r", " ").replace("\n", " ")[:500],
            }
        ],
        "artifact": {},
    }


def _call_parts(call: object) -> tuple[str, object]:
    if isinstance(call, Mapping):
        name = call.get("name")
        arguments = call.get("arguments")
    else:
        name = getattr(call, "name", None)
        arguments = getattr(call, "arguments", None)
    if not isinstance(name, str):
        raise ValueError("tool call name is missing")
    return name, arguments


def _session_id(arguments: object) -> str:
    if isinstance(arguments, Mapping):
        value = arguments.get("session_id")
        return value if isinstance(value, str) else ""
    return ""


def _lease_envelope(lease: object | None) -> dict[str, object] | None:
    if lease is None:
        return None
    allowed_fields = getattr(lease, "allowed_fields", ())
    required_fields = sorted(
        {
            field
            for _, fields in allowed_fields
            for field in fields
        }
    )
    allowed_unit_ids = list(getattr(lease, "allowed_unit_ids", ()))
    first_unit = allowed_unit_ids[0] if allowed_unit_ids else ""
    phase = first_unit.split(":", 1)[0] if first_unit else ""
    return {
        "lease_id": getattr(lease, "lease_id"),
        "phase": phase,
        "allowed_unit_ids": allowed_unit_ids,
        "required_fields": required_fields,
        "max_claims": getattr(lease, "max_claims"),
        "max_relationships": getattr(lease, "max_relationships"),
        "max_argument_bytes": getattr(lease, "max_argument_bytes"),
        "output_token_budget": getattr(lease, "output_token_budget"),
        "retry_count": getattr(lease, "retry_count", 0),
    }


def _next_action(result: ToolResult) -> str:
    if result.status == "sync_required":
        return "sync"
    if result.state == "COMPLETE":
        return "complete"
    if result.state == "READY":
        return "finalize"
    if result.lease is not None:
        return "submit_chunk"
    return "sync"


def _diagnostics(result: ToolResult) -> list[dict[str, str]]:
    if not result.message:
        return []
    code = {
        "sync_required": "STALE_STATE",
        "rejected": "REJECTED",
        "retryable": "RETRYABLE",
        "failed": "FAILED",
    }.get(result.status, "SERVICE_MESSAGE")
    return [{"code": code, "message": result.message[:500]}]


def _artifact(result: object) -> dict[str, object]:
    value = getattr(result, "artifact", None)
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return {}


def _envelope(result: ToolResult) -> dict[str, object]:
    completed, known = result.coverage
    return {
        "ok": result.status not in ERROR_STATUSES,
        "session_id": result.session_id,
        "state": result.state,
        "state_version": result.state_version,
        "next_action": _next_action(result),
        "lease": _lease_envelope(result.lease),
        "progress": {
            "completed_units": completed,
            "known_units": known,
        },
        "diagnostics": _diagnostics(result),
        "artifact": _artifact(result),
    }


def _claim_payload(claim: object) -> dict[str, object]:
    return {
        "claim_id": claim.claim_id,
        "section_key": SECTION_KEYS[claim.section_key],
        "subject_id": claim.subject_id,
        "field": claim.field,
        "value": claim.value,
        "status": claim.status,
        "evidence": list(claim.evidence),
        "reason": claim.reason,
    }


def _relationship_payload(relationship: object) -> dict[str, object]:
    return {
        "edge_id": relationship.edge_id,
        "source_subject_id": relationship.source_subject_id,
        "target_subject_id": relationship.target_subject_id,
        "attributes": dict(relationship.attributes),
        "status": relationship.status,
        "evidence": list(relationship.evidence),
        "reason": relationship.reason,
    }


class ReportToolHandler:
    def __init__(
        self,
        service: object,
        *,
        start_resolver: StartResolver | None = None,
    ):
        self.service = service
        self.start_resolver = start_resolver

    def _dispatch(self, command: object) -> ToolResult:
        if isinstance(command, StartToolCommand):
            if self.start_resolver is None:
                raise RuntimeError("report session start resolver is unavailable")
            return self.service.start(self.start_resolver(command))
        if isinstance(command, SyncToolCommand):
            return self.service.sync(SyncCommand(command.session_id))
        if isinstance(command, FinalizeToolCommand):
            finalize = getattr(self.service, "finalize", None)
            if finalize is None:
                raise RuntimeError("report session finalize is unavailable")
            return finalize(command)
        if not isinstance(command, SubmitToolCommand):
            raise ValueError("unsupported report tool command")

        snapshot = self.service.store.load(command.session_id)
        unit_ids = tuple(
            dict.fromkeys(
                [
                    *(claim.unit_id for claim in command.claims),
                    *(
                        relationship.unit_id
                        for relationship in command.relationships
                    ),
                ]
            )
        )
        payload = {
            "mode": snapshot.mode,
            "subjects": [
                {
                    "subject_id": subject.subject_id,
                    "kind": SUBJECT_KINDS.get(subject.kind, subject.kind),
                    "display_name": subject.display_name,
                }
                for subject in command.subject_declarations
            ],
            "claims": [_claim_payload(claim) for claim in command.claims],
            "relationships": [
                _relationship_payload(relationship)
                for relationship in command.relationships
            ],
        }
        return self.service.submit(
            SubmitChunkCommand(
                session_id=command.session_id,
                lease_id=command.lease_id,
                chunk_ordinal=command.chunk_ordinal,
                idempotency_key=command.idempotency_key,
                expected_state_version=command.expected_state_version,
                unit_ids=unit_ids,
                payload=payload,
                continuation=command.continuation,
            )
        )

    def execute_tool_call(self, call: CompleteToolCall) -> dict[str, object]:
        try:
            name, arguments = _call_parts(call)
            command = parse_tool_call(name, arguments)
        except (TypeError, ValueError) as error:
            return _empty_envelope(
                session_id=_session_id(
                    getattr(call, "arguments", None)
                    if not isinstance(call, Mapping)
                    else call.get("arguments")
                ),
                diagnostic_code="INVALID_TOOL_CALL",
                message=str(error),
            )
        try:
            return _envelope(self._dispatch(command))
        except Exception as error:
            return _empty_envelope(
                session_id=getattr(command, "session_id", ""),
                diagnostic_code="SERVICE_ERROR",
                message=str(error),
            )


def execute_tool_call(
    call: CompleteToolCall,
    service: object,
    *,
    start_resolver: StartResolver | None = None,
) -> dict[str, object]:
    return ReportToolHandler(
        service, start_resolver=start_resolver
    ).execute_tool_call(call)
