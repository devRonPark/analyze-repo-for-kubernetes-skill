from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable, Mapping


class ProtocolError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CompleteToolCall:
    name: str
    arguments: dict[str, object]
    call_id: str = ""


def _choice(event: object) -> Mapping[str, object]:
    if not isinstance(event, Mapping):
        raise ProtocolError("MALFORMED_STREAM_EVENT", "stream event is not an object")
    choices = event.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ProtocolError(
            "MALFORMED_STREAM_EVENT",
            "stream event must contain exactly one choice",
        )
    choice = choices[0]
    if not isinstance(choice, Mapping):
        raise ProtocolError("MALFORMED_STREAM_EVENT", "stream choice is invalid")
    return choice


def assemble_tool_stream(
    stream: Iterable[object],
    expected_tool: str,
) -> CompleteToolCall:
    finish_reason = None
    text_parts: list[str] = []
    calls: dict[int, dict[str, str]] = {}

    for event in stream:
        choice = _choice(event)
        current_finish = choice.get("finish_reason")
        if current_finish is not None:
            finish_reason = current_finish
        delta = choice.get("delta", {})
        if not isinstance(delta, Mapping):
            raise ProtocolError(
                "MALFORMED_STREAM_EVENT", "stream delta is invalid"
            )
        content = delta.get("content")
        if isinstance(content, str) and content:
            text_parts.append(content)
        tool_calls = delta.get("tool_calls", [])
        if tool_calls is None:
            tool_calls = []
        if not isinstance(tool_calls, list):
            raise ProtocolError(
                "MALFORMED_STREAM_EVENT", "tool_calls delta is invalid"
            )
        for fragment in tool_calls:
            if not isinstance(fragment, Mapping):
                raise ProtocolError(
                    "MALFORMED_STREAM_EVENT", "tool call fragment is invalid"
                )
            index = fragment.get("index", 0)
            if isinstance(index, bool) or not isinstance(index, int):
                raise ProtocolError(
                    "MALFORMED_STREAM_EVENT", "tool call index is invalid"
                )
            accumulated = calls.setdefault(
                index, {"id": "", "name": "", "arguments": ""}
            )
            call_id = fragment.get("id")
            if isinstance(call_id, str):
                accumulated["id"] += call_id
            function = fragment.get("function", {})
            if not isinstance(function, Mapping):
                raise ProtocolError(
                    "MALFORMED_STREAM_EVENT", "tool function delta is invalid"
                )
            name = function.get("name")
            if isinstance(name, str):
                accumulated["name"] += name
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                accumulated["arguments"] += arguments

    if finish_reason is None:
        raise ProtocolError(
            "NO_FINISH_REASON", "stream ended without a finish reason"
        )
    if finish_reason != "tool_calls":
        raise ProtocolError(
            "INVALID_FINISH_REASON",
            f"expected tool_calls finish reason, got {finish_reason}",
        )
    if any(part.strip() for part in text_parts):
        raise ProtocolError(
            "TEXT_WITH_TOOL_CALL",
            "assistant text cannot accompany a report tool call",
        )
    if len(calls) != 1:
        raise ProtocolError(
            "INVALID_TOOL_CALL_COUNT",
            f"expected one tool call, got {len(calls)}",
        )
    raw = next(iter(calls.values()))
    if raw["name"] != expected_tool:
        raise ProtocolError(
            "UNEXPECTED_TOOL",
            f"expected {expected_tool}, got {raw['name'] or '<missing>'}",
        )
    try:
        arguments = json.loads(raw["arguments"])
    except json.JSONDecodeError as error:
        raise ProtocolError(
            "MALFORMED_TOOL_ARGUMENTS",
            f"tool arguments are incomplete or invalid: {error}",
        ) from error
    if not isinstance(arguments, dict):
        raise ProtocolError(
            "MALFORMED_TOOL_ARGUMENTS", "tool arguments must be an object"
        )
    return CompleteToolCall(raw["name"], arguments, raw["id"])
