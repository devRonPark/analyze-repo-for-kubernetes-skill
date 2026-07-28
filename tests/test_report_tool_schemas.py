from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import report_tool_commands
import report_tool_schemas


TOOL_NAMES = (
    "report_session_start",
    "report_chunk_submit",
    "report_session_sync",
    "report_session_finalize",
)


def assert_strict_objects(testcase, schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            testcase.assertIs(schema.get("additionalProperties"), False)
        for value in schema.values():
            assert_strict_objects(testcase, value)
    elif isinstance(schema, list):
        for value in schema:
            assert_strict_objects(testcase, value)


def valid_claim():
    return {
        "claim_id": "claim-runtime",
        "unit_id": "component:api:runtime",
        "section_key": "component_runtime",
        "subject_id": "deployable:api",
        "field": "runtime",
        "value": "Python 3.12",
        "status": "confirmed",
        "evidence": ["pyproject.toml:1"],
        "reason": "",
    }


def valid_submit_arguments():
    return {
        "session_id": "session-1",
        "lease_id": "lease-1",
        "expected_state_version": 0,
        "idempotency_key": "submit-key-1",
        "chunk_ordinal": 0,
        "subject_declarations": [
            {
                "subject_id": "deployable:api",
                "kind": "deployable",
                "display_name": "API",
            }
        ],
        "claims": [valid_claim()],
        "relationships": [],
        "continuation": "lease_complete",
    }


class ReportToolSchemaTests(unittest.TestCase):
    def test_exact_tool_names_and_strict_object_boundaries(self):
        self.assertEqual(report_tool_schemas.tool_names(), TOOL_NAMES)

        for name in TOOL_NAMES:
            schema = report_tool_schemas.schema_for(name)
            self.assertEqual(schema["type"], "function")
            self.assertEqual(schema["function"]["name"], name)
            self.assertIs(schema["function"]["strict"], True)
            assert_strict_objects(
                self, schema["function"]["parameters"]
            )

    def test_submit_schema_has_bounded_record_limits(self):
        parameters = report_tool_schemas.schema_for(
            "report_chunk_submit"
        )["function"]["parameters"]

        self.assertEqual(
            parameters["properties"]["subject_declarations"]["maxItems"], 32
        )
        self.assertEqual(parameters["properties"]["claims"]["maxItems"], 48)
        self.assertEqual(
            parameters["properties"]["relationships"]["maxItems"], 16
        )
        self.assertEqual(
            parameters["properties"]["claims"]["items"]["properties"][
                "evidence"
            ]["maxItems"],
            8,
        )

    def test_schema_has_no_filesystem_path_argument(self):
        forbidden = {
            "path",
            "file_path",
            "directory",
            "report_path",
            "repository_root",
            "workspace",
        }
        for name in TOOL_NAMES:
            parameters = report_tool_schemas.schema_for(name)[
                "function"
            ]["parameters"]
            self.assertTrue(
                forbidden.isdisjoint(parameters["properties"]),
                name,
            )

    def test_schema_for_returns_a_deep_copy(self):
        first = report_tool_schemas.schema_for("report_session_sync")
        first["function"]["parameters"]["properties"].clear()

        second = report_tool_schemas.schema_for("report_session_sync")

        self.assertIn(
            "session_id",
            second["function"]["parameters"]["properties"],
        )

    def test_parser_rejects_unknown_argument_and_unknown_tool(self):
        arguments = valid_submit_arguments()
        arguments["report_path"] = "/tmp/report.md"

        with self.assertRaisesRegex(ValueError, "unknown"):
            report_tool_commands.parse_tool_call(
                "report_chunk_submit", arguments
            )
        with self.assertRaisesRegex(ValueError, "unknown tool"):
            report_tool_commands.parse_tool_call("write_file", {})

    def test_parser_rejects_business_invalid_status_reason(self):
        arguments = valid_submit_arguments()
        arguments["claims"][0]["status"] = "inferred"

        with self.assertRaisesRegex(ValueError, "reason"):
            report_tool_commands.parse_tool_call(
                "report_chunk_submit", arguments
            )

    def test_parser_builds_typed_submit_command(self):
        command = report_tool_commands.parse_tool_call(
            "report_chunk_submit", valid_submit_arguments()
        )

        self.assertIsInstance(
            command, report_tool_commands.SubmitToolCommand
        )
        self.assertEqual(command.claims[0].field, "runtime")
        self.assertEqual(command.continuation, "lease_complete")

    def test_start_requires_hash_and_all_opaque_ids(self):
        schema = report_tool_schemas.schema_for("report_session_start")[
            "function"
        ]["parameters"]

        self.assertEqual(
            set(schema["required"]),
            {
                "target_ref",
                "target_sha256",
                "analysis_snapshot_id",
                "idempotency_key",
            },
        )
        with self.assertRaisesRegex(ValueError, "target_sha256"):
            report_tool_commands.parse_tool_call(
                "report_session_start",
                {
                    "target_ref": "target-1",
                    "target_sha256": "not-a-hash",
                    "analysis_snapshot_id": "snapshot-1",
                    "idempotency_key": "start-key-1",
                },
            )
