from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_start_handoff import (
    HandoffError,
    MAX_SNAPSHOT_BYTES,
    MAX_TARGET_BYTES,
    ReportStartResolver,
    create_start_handoff,
)
from report_session_service import ReportSessionService
from report_session_store import SQLiteReportSessionStore
from report_tool_commands import StartToolCommand
from report_tool_handler import ReportToolHandler


class Call:
    name = "report_session_start"

    def __init__(self, arguments):
        self.arguments = arguments


def write_target(workspace: Path, *, mode: str = "summary") -> Path:
    target = workspace / "target.json"
    target.write_text(
        json.dumps(
            {
                "mode": mode,
                "artifacts": {"report": str(workspace / "report.md")},
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return target


class ReportStartHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.target = write_target(self.workspace)
        self.database = self.workspace / ".report-session/session.sqlite"
        self.store = SQLiteReportSessionStore(self.database)
        self.addCleanup(self.store.close)
        self.service = ReportSessionService(self.store)

    def count(self, table: str) -> int:
        return self.store.transact(
            lambda connection: connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
        )

    def handoff(self) -> dict[str, str]:
        return create_start_handoff(
            self.target,
            deployable_subject_ids=(
                "deployable:worker",
                "deployable:api",
                "deployable:api",
            ),
            relationship_edge_ids=("edge:api:database",),
        )

    def handler(self) -> ReportToolHandler:
        return ReportToolHandler(
            self.service,
            start_resolver=ReportStartResolver(
                self.service,
                workspace_root=self.workspace,
                configured_target_json=self.target,
            ),
        )

    def test_helper_writes_one_content_addressed_snapshot_and_four_fields(self):
        first = self.handoff()
        snapshot = (
            self.workspace
            / ".report-session/snapshots"
            / f"{first['analysis_snapshot_id']}.json"
        )
        first_bytes = snapshot.read_bytes()

        second = self.handoff()

        self.assertEqual(
            set(first),
            {
                "target_ref",
                "target_sha256",
                "analysis_snapshot_id",
                "idempotency_key",
            },
        )
        self.assertEqual(first, second)
        self.assertEqual(snapshot.read_bytes(), first_bytes)
        self.assertEqual(
            json.loads(first_bytes),
            {
                "mode": "summary",
                "deployable_subject_ids": [
                    "deployable:api",
                    "deployable:worker",
                ],
                "relationship_edge_ids": ["edge:api:database"],
            },
        )
        self.assertEqual(len(first["target_sha256"]), 64)
        self.assertEqual(len(first["analysis_snapshot_id"]), 64)
        self.assertEqual(
            list((snapshot.parent).glob("*.json")),
            [snapshot],
        )

    def test_analysis_helper_cli_outputs_only_the_handoff(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/report_start_handoff.py"),
                "--target-ref",
                str(self.target),
                "--deployable-subject-id",
                "deployable:api",
                "--relationship-edge-id",
                "edge:api:database",
            ],
            capture_output=True,
            text=True,
            cwd=self.workspace,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            set(json.loads(result.stdout)),
            {
                "target_ref",
                "target_sha256",
                "analysis_snapshot_id",
                "idempotency_key",
            },
        )

    def test_helper_rejects_snapshot_directory_escape(self):
        with TemporaryDirectory() as outside_temporary:
            outside = Path(outside_temporary)
            workspace = self.workspace / "escaped"
            workspace.mkdir()
            target = write_target(workspace)
            (workspace / ".report-session").symlink_to(
                outside, target_is_directory=True
            )

            with self.assertRaises(HandoffError):
                create_start_handoff(
                    target,
                    deployable_subject_ids=("deployable:api",),
                    relationship_edge_ids=(),
                )

            self.assertEqual(list(outside.rglob("*.json")), [])

    def test_resolver_creates_typed_empty_document_and_configures_lifecycle(self):
        handoff = self.handoff()
        resolver = ReportStartResolver(
            self.service,
            workspace_root=self.workspace,
            configured_target_json=self.target,
        )

        command = resolver(StartToolCommand(**handoff))

        self.assertEqual(command.target_hash, handoff["target_sha256"])
        self.assertEqual(
            command.analysis_snapshot_id,
            handoff["analysis_snapshot_id"],
        )
        self.assertEqual(command.mode, "summary")
        self.assertEqual(
            command.analysis_snapshot.deployable_subject_ids,
            ("deployable:api", "deployable:worker"),
        )
        self.assertEqual(
            command.analysis_snapshot.relationship_edge_ids,
            ("edge:api:database",),
        )
        self.assertEqual(
            command.initial_payload,
            {
                "mode": "summary",
                "subjects": [],
                "claims": [],
                "relationships": [],
            },
        )
        self.assertEqual(self.service.lifecycle.target_json, self.target)

    def test_idempotent_start_retry_returns_one_session(self):
        handoff = self.handoff()
        handler = self.handler()

        first = handler.execute_tool_call(Call(handoff))
        second = handler.execute_tool_call(Call(handoff))

        self.assertTrue(first["ok"], first)
        self.assertEqual(first, second)
        self.assertEqual(self.count("sessions"), 1)
        document = self.service.load_document(first["session_id"])
        self.assertEqual(document.mode, "summary")
        self.assertEqual(document.subjects, ())
        self.assertEqual(document.claims, ())
        self.assertEqual(document.relationships, ())

    def test_conflicting_retry_does_not_rebind_session_lifecycle(self):
        first_workspace = self.workspace / "first"
        second_workspace = self.workspace / "second"
        first_workspace.mkdir()
        second_workspace.mkdir()
        first_target = write_target(first_workspace)
        second_target = write_target(second_workspace)
        first_handoff = create_start_handoff(
            first_target,
            deployable_subject_ids=("deployable:first",),
            relationship_edge_ids=(),
        )
        second_handoff = create_start_handoff(
            second_target,
            deployable_subject_ids=("deployable:second",),
            relationship_edge_ids=(),
        )
        second_handoff["idempotency_key"] = first_handoff[
            "idempotency_key"
        ]
        handler = ReportToolHandler(
            self.service,
            start_resolver=ReportStartResolver(
                self.service,
                workspace_root=self.workspace,
            ),
        )

        first = handler.execute_tool_call(Call(first_handoff))
        second = handler.execute_tool_call(Call(second_handoff))

        self.assertTrue(first["ok"], first)
        self.assertFalse(second["ok"])
        self.assertEqual(
            self.service.lifecycle.target_json, first_target
        )
        self.assertEqual(self.count("sessions"), 1)

    def test_hash_mismatch_rejects_without_session_state(self):
        handoff = self.handoff()
        target_result = self.handler().execute_tool_call(
            Call({**handoff, "target_sha256": "0" * 64})
        )
        snapshot = (
            self.workspace
            / ".report-session/snapshots"
            / f"{handoff['analysis_snapshot_id']}.json"
        )
        snapshot.write_bytes(b'{"mode":"summary"}\n')
        snapshot_result = self.handler().execute_tool_call(Call(handoff))

        self.assertFalse(target_result["ok"])
        self.assertFalse(snapshot_result["ok"])
        self.assertEqual(
            target_result["diagnostics"][0]["code"], "SERVICE_ERROR"
        )
        self.assertEqual(self.count("sessions"), 0)
        self.assertEqual(self.count("start_results"), 0)

    def test_outside_target_and_snapshot_symlink_are_rejected_without_state(self):
        with TemporaryDirectory() as outside_temporary:
            outside = Path(outside_temporary)
            outside_target = write_target(outside)
            outside_handoff = create_start_handoff(
                outside_target,
                deployable_subject_ids=("deployable:outside",),
                relationship_edge_ids=(),
            )
            outside_result = self.handler().execute_tool_call(
                Call(outside_handoff)
            )

            handoff = self.handoff()
            snapshot = (
                self.workspace
                / ".report-session/snapshots"
                / f"{handoff['analysis_snapshot_id']}.json"
            )
            snapshot_bytes = snapshot.read_bytes()
            snapshot.unlink()
            outside_snapshot = outside / "snapshot.json"
            outside_snapshot.write_bytes(snapshot_bytes)
            snapshot.symlink_to(outside_snapshot)
            snapshot_result = self.handler().execute_tool_call(Call(handoff))

        self.assertFalse(outside_result["ok"])
        self.assertFalse(snapshot_result["ok"])
        self.assertEqual(self.count("sessions"), 0)
        self.assertEqual(self.count("work_units"), 0)

    def test_missing_target_and_snapshot_are_rejected_without_state(self):
        handoff = self.handoff()
        missing_target_result = self.handler().execute_tool_call(
            Call(
                {
                    **handoff,
                    "target_ref": str(self.workspace / "missing.json"),
                }
            )
        )
        snapshot = (
            self.workspace
            / ".report-session/snapshots"
            / f"{handoff['analysis_snapshot_id']}.json"
        )
        snapshot.unlink()
        missing_snapshot_result = self.handler().execute_tool_call(
            Call(handoff)
        )

        self.assertFalse(missing_target_result["ok"])
        self.assertFalse(missing_snapshot_result["ok"])
        self.assertEqual(self.count("sessions"), 0)
        self.assertEqual(self.count("start_results"), 0)

    def test_malformed_and_oversized_inputs_never_create_session_state(self):
        valid_handoff = self.handoff()
        valid_target_bytes = self.target.read_bytes()
        snapshot = (
            self.workspace
            / ".report-session/snapshots"
            / f"{valid_handoff['analysis_snapshot_id']}.json"
        )
        malformed_snapshot = b'{"mode":"summary"}\n'
        malformed_id = sha256(malformed_snapshot).hexdigest()
        malformed_path = snapshot.parent / f"{malformed_id}.json"
        malformed_path.write_bytes(malformed_snapshot)
        oversized_snapshot = b" " * (MAX_SNAPSHOT_BYTES + 1)
        oversized_id = sha256(oversized_snapshot).hexdigest()
        oversized_path = snapshot.parent / f"{oversized_id}.json"
        oversized_path.write_bytes(oversized_snapshot)
        cases = (
            (
                "malformed target",
                b"{not-json}",
                valid_handoff["analysis_snapshot_id"],
            ),
            (
                "oversized target",
                b" " * (MAX_TARGET_BYTES + 1),
                valid_handoff["analysis_snapshot_id"],
            ),
            ("malformed snapshot", valid_target_bytes, malformed_id),
            ("oversized snapshot", valid_target_bytes, oversized_id),
        )

        for label, target_bytes, snapshot_id in cases:
            with self.subTest(label=label):
                self.target.write_bytes(target_bytes)
                handoff = {
                    **valid_handoff,
                    "target_sha256": sha256(target_bytes).hexdigest(),
                    "analysis_snapshot_id": snapshot_id,
                }
                result = self.handler().execute_tool_call(Call(handoff))
                self.assertFalse(result["ok"])
                self.assertEqual(self.count("sessions"), 0)
                self.assertEqual(self.count("start_results"), 0)
                self.assertEqual(self.count("work_units"), 0)

    def test_service_error_never_contains_source_or_absolute_paths(self):
        handoff = self.handoff()
        invalid = replace(
            StartToolCommand(**handoff),
            target_sha256="f" * 64,
        )

        result = self.handler().execute_tool_call(
            Call(
                {
                    "target_ref": invalid.target_ref,
                    "target_sha256": invalid.target_sha256,
                    "analysis_snapshot_id": invalid.analysis_snapshot_id,
                    "idempotency_key": invalid.idempotency_key,
                }
            )
        )

        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(str(self.workspace), serialized)
        self.assertNotIn("target.json", serialized)
        self.assertNotIn("source", serialized)


if __name__ == "__main__":
    unittest.main()
