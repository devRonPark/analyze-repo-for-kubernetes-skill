import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_session_service import ReportSessionService, StartCommand
from report_session_store import SQLiteReportSessionStore
from report_work_units import AnalysisSnapshot


SERVER = ROOT / "mcp/report_tool_server.py"


def request(identifier, method, params=None):
    message = {"jsonrpc": "2.0", "id": identifier, "method": method}
    if params is not None:
        message["params"] = params
    return message


class ReportToolServerTests(unittest.TestCase):
    def run_server(self, messages, database):
        payload = "\n".join(
            json.dumps(message, separators=(",", ":"))
            for message in messages
        )
        result = subprocess.run(
            [sys.executable, str(SERVER)],
            input=payload + "\n",
            capture_output=True,
            text=True,
            cwd=ROOT,
            env={
                **os.environ,
                "REPORT_SESSION_DB": str(database),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            timeout=10,
            check=False,
        )
        responses = [
            json.loads(line)
            for line in result.stdout.splitlines()
            if line.strip()
        ]
        return result, responses

    def initialize_session(self, database):
        store = SQLiteReportSessionStore(database)
        ReportSessionService(store).start(
            StartCommand(
                session_id="session-1",
                idempotency_key="start-key",
                analysis_snapshot_id="snapshot-1",
                target_hash="a" * 64,
                mode="summary",
                analysis_snapshot=AnalysisSnapshot(
                    mode="summary",
                    deployable_subject_ids=(),
                    relationship_edge_ids=(),
                ),
                initial_payload={
                    "mode": "summary",
                    "subjects": [],
                    "claims": [],
                    "relationships": [],
                },
            )
        )
        store.close()

    def test_initialize_notification_list_call_and_eof_contract(self):
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / "session.sqlite"
            self.initialize_session(database)
            result, responses = self.run_server(
                [
                    request(
                        1,
                        "initialize",
                        {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {
                                "name": "contract-test",
                                "version": "1",
                            },
                        },
                    ),
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                    },
                    request(2, "tools/list", {}),
                    request(
                        3,
                        "tools/call",
                        {
                            "name": "report_session_sync",
                            "arguments": {
                                "session_id": "session-1",
                                "known_state_version": 0,
                                "request_id": "request-1",
                            },
                        },
                    ),
                ],
                database,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([response["id"] for response in responses], [1, 2, 3])
        self.assertEqual(
            responses[0]["result"]["protocolVersion"], "2025-06-18"
        )
        tools = responses[1]["result"]["tools"]
        self.assertEqual(
            {tool["name"] for tool in tools},
            {
                "report_session_start",
                "report_chunk_submit",
                "report_session_sync",
                "report_session_finalize",
            },
        )
        for tool in tools:
            self.assertFalse(tool["inputSchema"]["additionalProperties"])
        call_result = responses[2]["result"]
        self.assertEqual(
            call_result["structuredContent"]["session_id"],
            "session-1",
        )
        self.assertEqual(
            json.loads(call_result["content"][0]["text"]),
            call_result["structuredContent"],
        )
        self.assertNotIn('"jsonrpc"', result.stderr)

    def test_tools_are_rejected_before_initialized_notification(self):
        with TemporaryDirectory() as temporary:
            result, responses = self.run_server(
                [
                    request(
                        1,
                        "initialize",
                        {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"},
                        },
                    ),
                    request(2, "tools/list", {}),
                ],
                Path(temporary) / "session.sqlite",
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(responses[1]["error"]["code"], -32002)

    def test_malformed_json_returns_parse_error_and_server_exits_cleanly(self):
        with TemporaryDirectory() as temporary:
            result = subprocess.run(
                [sys.executable, str(SERVER)],
                input="{not-json}\n",
                capture_output=True,
                text=True,
                cwd=ROOT,
                env={
                    **os.environ,
                    "REPORT_SESSION_DB": str(
                        Path(temporary) / "session.sqlite"
                    ),
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                timeout=10,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        response = json.loads(result.stdout)
        self.assertIsNone(response["id"])
        self.assertEqual(response["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
