from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Mapping

from report_model_protocol import ProtocolError, assemble_tool_stream
from report_session_service import ToolResult
from report_tool_handler import ReportToolHandler, compact_tool_result
from report_tool_schemas import schema_for


ACTION_TO_TOOL = {
    "start": "report_session_start",
    "submit_chunk": "report_chunk_submit",
    "sync": "report_session_sync",
    "finalize": "report_session_finalize",
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass
class ReportContext:
    initial_result: dict[str, object]
    base_messages: tuple[dict[str, str], ...] = ()
    start_resolver: object | None = None
    _result: dict[str, object] = field(init=False)

    def __post_init__(self) -> None:
        self._result = dict(self.initial_result)

    @property
    def result(self) -> dict[str, object]:
        return self._result

    def retry_key(self, expected_tool: str) -> str:
        lease = self._result.get("lease")
        lease_id = (
            lease.get("lease_id", "")
            if isinstance(lease, Mapping)
            else ""
        )
        material = ":".join(
            (
                str(self._result.get("session_id", "")),
                str(self._result.get("state_version", -1)),
                lease_id,
                expected_tool,
            )
        )
        return "retry-" + sha256(material.encode("utf-8")).hexdigest()[:24]

    def messages_for(self, expected_tool: str) -> list[dict[str, str]]:
        compact = {
            "required_tool": expected_tool,
            "retry_key": self.retry_key(expected_tool),
            "idempotency_key": self.retry_key(expected_tool),
            "result": self._result,
        }
        return [
            *self.base_messages,
            {
                "role": "user",
                "content": _canonical_json(compact),
            },
        ]

    def replace_with_compact_result(
        self, result: Mapping[str, object]
    ) -> None:
        self._result = dict(result)


def _known_units(result: Mapping[str, object]) -> int:
    progress = result.get("progress")
    if not isinstance(progress, Mapping):
        return 0
    known = progress.get("known_units", 0)
    return known if isinstance(known, int) and not isinstance(known, bool) else 0


def _completed_units(result: Mapping[str, object]) -> int:
    progress = result.get("progress")
    if not isinstance(progress, Mapping):
        return 0
    completed = progress.get("completed_units", 0)
    return (
        completed
        if isinstance(completed, int) and not isinstance(completed, bool)
        else 0
    )


def _max_tokens(result: Mapping[str, object]) -> int:
    lease = result.get("lease")
    if isinstance(lease, Mapping):
        budget = lease.get("output_token_budget")
        if isinstance(budget, int) and not isinstance(budget, bool):
            return budget
    return 1024


def run_report_loop(
    model: object,
    service: object,
    context: ReportContext,
    *,
    handler: object | None = None,
) -> dict[str, object]:
    executor = handler or ReportToolHandler(
        service, start_resolver=context.start_resolver
    )
    known_units = _known_units(context.result)
    max_steps = max(20, known_units * 4)
    seen_payload_hash = ""
    identical_without_progress = 0

    for _ in range(max_steps):
        action = context.result.get("next_action")
        if action == "complete":
            artifact = context.result.get("artifact")
            return dict(artifact) if isinstance(artifact, Mapping) else {}
        expected_tool = ACTION_TO_TOOL.get(str(action))
        if expected_tool is None:
            raise RuntimeError(f"unsupported report action: {action}")

        request = {
            "messages": context.messages_for(expected_tool),
            "tools": [schema_for(expected_tool)],
            "tool_choice": {
                "type": "function",
                "function": {"name": expected_tool},
            },
            "parallel_tool_calls": False,
            "temperature": 0,
            "max_tokens": _max_tokens(context.result),
            "stream": True,
        }
        try:
            stream = model.chat(**request)
            call = assemble_tool_stream(stream, expected_tool)
        except TimeoutError:
            code = "TRANSPORT_TIMEOUT"
            failure_result = _record_transport_failure(
                service, context.result, code
            )
            if failure_result is not None:
                context.replace_with_compact_result(failure_result)
            continue
        except ProtocolError as error:
            failure_result = _record_transport_failure(
                service, context.result, error.code
            )
            if failure_result is not None:
                context.replace_with_compact_result(failure_result)
            continue

        payload_hash = sha256(
            _canonical_json(call.arguments).encode("utf-8")
        ).hexdigest()
        before_progress = _completed_units(context.result)
        result = executor.execute_tool_call(call)
        if not isinstance(result, Mapping):
            raise RuntimeError("tool handler returned a non-object result")
        after_progress = _completed_units(result)
        if after_progress <= before_progress:
            identical_without_progress = (
                identical_without_progress + 1
                if payload_hash == seen_payload_hash
                else 1
            )
        else:
            identical_without_progress = 0
        seen_payload_hash = payload_hash
        if identical_without_progress >= 3:
            raise RuntimeError(
                "three identical tool payloads produced no coverage growth"
            )
        context.replace_with_compact_result(result)

    raise RuntimeError(f"report loop exceeded max steps: {max_steps}")


def _record_transport_failure(
    service: object,
    result: Mapping[str, object],
    code: str,
) -> Mapping[str, object] | None:
    session_id = result.get("session_id")
    lease = result.get("lease")
    lease_id = (
        lease.get("lease_id") if isinstance(lease, Mapping) else None
    )
    if not isinstance(session_id, str) or not isinstance(lease_id, str):
        raise RuntimeError(
            f"{code}: transport failure has no active report lease"
        )
    failure_result = service.record_transport_failure(
        session_id, lease_id, code
    )
    if isinstance(failure_result, Mapping):
        return failure_result
    if isinstance(failure_result, ToolResult):
        return compact_tool_result(failure_result)
    return None
