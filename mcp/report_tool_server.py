#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_model_protocol import CompleteToolCall
from report_session_service import ReportSessionService
from report_session_store import SQLiteReportSessionStore
from report_tool_handler import ReportToolHandler
from report_tool_schemas import TOOL_NAMES, schema_for


SERVER_INFO = {
    "name": "analyze-repo-for-kubernetes-report-tools",
    "version": "0.2.0",
}


class JsonRpcError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _database_path() -> Path:
    configured = os.environ.get("REPORT_SESSION_DB")
    if configured:
        return Path(configured)
    plugin_data = os.environ.get("PLUGIN_DATA") or os.environ.get(
        "CLAUDE_PLUGIN_DATA"
    )
    if plugin_data:
        return Path(plugin_data) / "report-session/session.sqlite"
    return (
        Path(tempfile.gettempdir())
        / "analyze-repo-for-kubernetes/report-session/session.sqlite"
    )


def _response(identifier: object, result: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def _error(
    identifier: object, code: int, message: str
) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "error": {"code": code, "message": message},
    }


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise JsonRpcError(-32602, f"{label} must be an object")
    return value


def _tool_list() -> list[dict[str, object]]:
    tools = []
    for name in TOOL_NAMES:
        openai_tool = schema_for(name)["function"]
        tools.append(
            {
                "name": openai_tool["name"],
                "description": openai_tool["description"],
                "inputSchema": openai_tool["parameters"],
            }
        )
    return tools


class ReportToolServer:
    def __init__(self, handler: ReportToolHandler):
        self.handler = handler
        self.initialize_received = False
        self.initialized = False
        self.protocol_version = "2025-06-18"

    def handle(self, message: object) -> dict[str, object] | None:
        request = _object(message, "request")
        if request.get("jsonrpc") != "2.0":
            raise JsonRpcError(-32600, "jsonrpc must be 2.0")
        method = request.get("method")
        if not isinstance(method, str):
            raise JsonRpcError(-32600, "method is required")
        identifier = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            if identifier is None:
                raise JsonRpcError(-32600, "initialize requires an id")
            values = _object(params, "initialize params")
            requested = values.get("protocolVersion")
            if isinstance(requested, str) and requested:
                self.protocol_version = requested
            self.initialize_received = True
            return _response(
                identifier,
                {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO,
                },
            )

        if method == "notifications/initialized":
            if not self.initialize_received:
                raise JsonRpcError(-32002, "server is not initialized")
            self.initialized = True
            return None

        if method in {"tools/list", "tools/call"} and not self.initialized:
            raise JsonRpcError(-32002, "initialized notification is required")

        if method == "tools/list":
            if identifier is None:
                raise JsonRpcError(-32600, "tools/list requires an id")
            _object(params, "tools/list params")
            return _response(identifier, {"tools": _tool_list()})

        if method == "tools/call":
            if identifier is None:
                raise JsonRpcError(-32600, "tools/call requires an id")
            values = _object(params, "tools/call params")
            if set(values) != {"name", "arguments"}:
                raise JsonRpcError(
                    -32602,
                    "tools/call requires only name and arguments",
                )
            name = values["name"]
            if not isinstance(name, str):
                raise JsonRpcError(-32602, "tool name must be a string")
            arguments = _object(values["arguments"], "tool arguments")
            envelope = self.handler.execute_tool_call(
                CompleteToolCall(name, dict(arguments))
            )
            text = json.dumps(
                envelope,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            return _response(
                identifier,
                {
                    "content": [{"type": "text", "text": text}],
                    "structuredContent": envelope,
                    "isError": not bool(envelope.get("ok")),
                },
            )

        if method.startswith("notifications/"):
            return None
        raise JsonRpcError(-32601, f"method not found: {method}")


def serve() -> int:
    store = SQLiteReportSessionStore(_database_path())
    server = ReportToolServer(
        ReportToolHandler(ReportSessionService(store))
    )
    try:
        for raw_line in sys.stdin:
            if not raw_line.strip():
                continue
            identifier = None
            try:
                message = json.loads(raw_line)
                if isinstance(message, Mapping):
                    identifier = message.get("id")
                response = server.handle(message)
            except json.JSONDecodeError:
                response = _error(None, -32700, "parse error")
            except JsonRpcError as error:
                response = _error(identifier, error.code, str(error))
            except Exception as error:
                print(
                    f"report tool server error: {type(error).__name__}",
                    file=sys.stderr,
                )
                response = _error(identifier, -32603, "internal error")
            if response is not None:
                print(
                    json.dumps(
                        response,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    flush=True,
                )
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
