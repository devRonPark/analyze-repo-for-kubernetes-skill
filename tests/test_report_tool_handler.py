from dataclasses import dataclass
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_session_models import Lease
from report_session_service import ToolResult
from report_tool_handler import ReportToolHandler


@dataclass(frozen=True)
class Call:
    name: str
    arguments: object


class Snapshot:
    mode = "summary"


class Store:
    def load(self, session_id):
        return Snapshot()


class FakeService:
    def __init__(self, result=None, error=None):
        self.result = result or ToolResult(
            status="lease_issued",
            session_id="session-1",
            state="COLLECTING",
            state_version=2,
            lease=Lease(
                lease_id="lease-2",
                session_id="session-1",
                allowed_unit_ids=("component:app:runtime",),
                allowed_fields=(
                    (
                        "component:app:runtime",
                        ("runtime", "startup_command"),
                    ),
                ),
                output_token_budget=1200,
                max_argument_bytes=8192,
                max_claims=16,
                max_relationships=0,
            ),
            coverage=(3, 9),
        )
        self.error = error
        self.calls = []
        self.store = Store()

    def sync(self, command):
        self.calls.append(("sync", command))
        if self.error:
            raise self.error
        return self.result

    def submit(self, command):
        self.calls.append(("submit", command))
        if self.error:
            raise self.error
        return self.result


def sync_call(**overrides):
    arguments = {
        "session_id": "session-1",
        "known_state_version": 1,
        "request_id": "request-1",
    }
    arguments.update(overrides)
    return Call("report_session_sync", arguments)


class ReportToolHandlerTests(unittest.TestCase):
    def test_returns_only_compact_envelope_keys(self):
        service = FakeService()

        result = ReportToolHandler(service).execute_tool_call(sync_call())

        self.assertEqual(
            set(result),
            {
                "ok",
                "session_id",
                "state",
                "state_version",
                "next_action",
                "lease",
                "progress",
                "diagnostics",
                "artifact",
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["next_action"], "submit_chunk")
        self.assertEqual(
            result["progress"],
            {"completed_units": 3, "known_units": 9},
        )
        self.assertEqual(
            result["lease"],
            {
                "lease_id": "lease-2",
                "phase": "component",
                "allowed_unit_ids": ["component:app:runtime"],
                "required_fields": ["runtime", "startup_command"],
                "max_claims": 16,
                "max_relationships": 0,
                "max_argument_bytes": 8192,
                "output_token_budget": 1200,
                "retry_count": 0,
            },
        )

    def test_unknown_tool_is_rejected_without_calling_service(self):
        service = FakeService()

        result = ReportToolHandler(service).execute_tool_call(
            Call("write_report", {})
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["diagnostics"][0]["code"], "INVALID_TOOL_CALL")
        self.assertEqual(service.calls, [])

    def test_service_exception_is_normalized_without_source_content(self):
        service = FakeService(error=RuntimeError("database unavailable"))

        result = ReportToolHandler(service).execute_tool_call(sync_call())

        self.assertFalse(result["ok"])
        self.assertEqual(result["next_action"], "sync")
        self.assertEqual(
            result["diagnostics"],
            [
                {
                    "code": "SERVICE_ERROR",
                    "message": "database unavailable",
                }
            ],
        )
        serialized = repr(result)
        self.assertNotIn("source", serialized)
        self.assertNotIn("report_markdown", serialized)

    def test_stale_state_has_sync_diagnostic_and_authoritative_version(self):
        service = FakeService(
            ToolResult(
                status="sync_required",
                session_id="session-1",
                state="COLLECTING",
                state_version=7,
                lease=None,
                coverage=(4, 9),
                message="expected_state_version이 stale합니다",
            )
        )

        result = ReportToolHandler(service).execute_tool_call(sync_call())

        self.assertFalse(result["ok"])
        self.assertEqual(result["next_action"], "sync")
        self.assertEqual(result["state_version"], 7)
        self.assertEqual(
            result["diagnostics"][0]["code"], "STALE_STATE"
        )

    def test_submit_command_contains_only_semantic_document_records(self):
        service = FakeService()
        call = Call(
            "report_chunk_submit",
            {
                "session_id": "session-1",
                "lease_id": "lease-2",
                "expected_state_version": 2,
                "idempotency_key": "submit-1",
                "chunk_ordinal": 0,
                "subject_declarations": [
                    {
                        "subject_id": "deployable:app",
                        "kind": "deployable",
                        "display_name": "app",
                    }
                ],
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "unit_id": "component:app:runtime",
                        "section_key": "component_runtime",
                        "subject_id": "deployable:app",
                        "field": "runtime",
                        "value": "Python 3",
                        "status": "confirmed",
                        "evidence": ["pyproject.toml:1"],
                        "reason": "",
                    }
                ],
                "relationships": [],
                "continuation": "lease_complete",
            },
        )

        ReportToolHandler(service).execute_tool_call(call)

        kind, command = service.calls[0]
        self.assertEqual(kind, "submit")
        self.assertEqual(command.unit_ids, ("component:app:runtime",))
        self.assertEqual(command.payload["mode"], "summary")
        self.assertEqual(
            command.payload["claims"][0]["section_key"],
            "component_cards",
        )
        self.assertNotIn("unit_id", command.payload["claims"][0])
        self.assertNotIn("continuation", command.payload)


if __name__ == "__main__":
    unittest.main()
