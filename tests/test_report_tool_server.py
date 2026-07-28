import json
from hashlib import sha256
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
    def run_server(
        self, messages, database, *, target_json=None, cwd=ROOT
    ):
        payload = "\n".join(
            json.dumps(message, separators=(",", ":"))
            for message in messages
        )
        environment = {
            **os.environ,
            "REPORT_SESSION_DB": str(database),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if target_json is not None:
            environment["REPORT_TARGET_JSON"] = str(target_json)
        result = subprocess.run(
            [sys.executable, str(SERVER)],
            input=payload + "\n",
            capture_output=True,
            text=True,
            cwd=cwd,
            env=environment,
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

    def test_configured_server_resolves_a_real_start_handoff(self):
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            database = workspace / "session.sqlite"
            target = workspace / "target.json"
            target.write_text(
                json.dumps(
                    {
                        "mode": "summary",
                        "artifacts": {
                            "report": str(workspace / "analysis.md")
                        },
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            snapshot_bytes = (
                b'{"deployable_subject_ids":["deployable:api"],'
                b'"mode":"summary","relationship_edge_ids":[]}\n'
            )
            snapshot_id = sha256(snapshot_bytes).hexdigest()
            snapshot_path = (
                workspace
                / ".report-session/snapshots"
                / f"{snapshot_id}.json"
            )
            snapshot_path.parent.mkdir(parents=True)
            snapshot_path.write_bytes(snapshot_bytes)

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
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                    },
                    request(
                        2,
                        "tools/call",
                        {
                            "name": "report_session_start",
                            "arguments": {
                                "target_ref": str(target),
                                "target_sha256": sha256(
                                    target.read_bytes()
                                ).hexdigest(),
                                "analysis_snapshot_id": snapshot_id,
                                "idempotency_key": "start-real-handoff",
                            },
                        },
                    ),
                ],
                database,
                cwd=workspace,
            )

            store = SQLiteReportSessionStore(database)
            session_count = store.transact(
                lambda connection: connection.execute(
                    "SELECT COUNT(*) FROM sessions"
                ).fetchone()[0]
            )
            store.close()

        self.assertEqual(result.returncode, 0, result.stderr)
        started = responses[1]["result"]["structuredContent"]
        self.assertTrue(started["ok"], started)
        self.assertEqual(started["state"], "COLLECTING")
        self.assertEqual(session_count, 1)

    def test_configured_server_finalizes_ready_session(self):
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            database = workspace / "session.sqlite"
            canonical = workspace / "analysis.md"
            canonical.write_text("# template\n", encoding="utf-8")
            target = workspace / "target.json"
            target.write_text(
                json.dumps(
                    {
                        "mode": "summary",
                        "analysis_root": str(
                            ROOT / "tests/fixtures/report_records/repository"
                        ),
                        "artifacts": {"report": str(canonical)},
                        "validation": {
                            "command": [
                                sys.executable,
                                str(
                                    ROOT
                                    / "scripts/validate_target_report.py"
                                ),
                                str(target),
                            ],
                            "report_command": [
                                sys.executable,
                                str(ROOT / "scripts/validate_report.py"),
                                str(canonical),
                                "--mode",
                                "summary",
                                "--contract",
                                "new",
                                "--repo-root",
                                str(
                                    ROOT
                                    / "tests/fixtures/report_records/repository"
                                ),
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            fixture = (
                ROOT
                / "tests/fixtures/report_records/jpetstore-summary.json"
            )
            store = SQLiteReportSessionStore(database)
            ReportSessionService(store).start(
                StartCommand(
                    session_id="session-ready",
                    idempotency_key="start-ready",
                    analysis_snapshot_id="snapshot-ready",
                    target_hash=sha256(target.read_bytes()).hexdigest(),
                    mode="summary",
                    analysis_snapshot=AnalysisSnapshot(
                        mode="summary",
                        deployable_subject_ids=("deployable:jpetstore",),
                        relationship_edge_ids=("edge:jpetstore:mysql",),
                    ),
                    initial_payload=json.loads(
                        fixture.read_text(encoding="utf-8")
                    ),
                )
            )
            store.close()

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
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                    },
                    request(
                        2,
                        "tools/call",
                        {
                            "name": "report_session_finalize",
                            "arguments": {
                                "session_id": "session-ready",
                                "expected_state_version": 0,
                                "idempotency_key": "finalize-ready",
                            },
                        },
                    ),
                ],
                database,
                target_json=target,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        finalized = responses[1]["result"]["structuredContent"]
        self.assertTrue(finalized["ok"])
        self.assertEqual(finalized["state"], "COMPLETE")
        self.assertEqual(
            finalized["artifact"]["path"], str(canonical)
        )

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
