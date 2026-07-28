import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import report_contract
from report_diagnostics import Diagnostic
from report_lifecycle import ReportLifecycle
import report_records
import report_renderer
from report_session_service import (
    ReportSessionService,
    StartCommand,
    SubmitChunkCommand,
)
from report_session_store import SQLiteReportSessionStore
from report_tool_commands import FinalizeToolCommand
import report_work_units
from report_work_units import AnalysisSnapshot, WorkUnit


FIXTURES = ROOT / "tests/fixtures/report_records"
DOCUMENT_PATH = FIXTURES / "jpetstore-summary.json"
EVIDENCE_REPOSITORY = FIXTURES / "repository"
TARGET_GUARD = ROOT / "scripts/validate_target_report.py"
REPORT_VALIDATOR = ROOT / "scripts/validate_report.py"


class RepairUnitMappingTests(unittest.TestCase):
    def setUp(self):
        self.units = (
            WorkUnit(
                "component:deployable:web:runtime",
                "component_runtime",
                "deployable:web",
                ("runtime", "startup_command"),
            ),
            WorkUnit(
                "component:deployable:web:configuration-state",
                "component_configuration_state",
                "deployable:web",
                ("configuration",),
            ),
            WorkUnit(
                "relationship:edge:web:db",
                "relationship",
                None,
                (),
                relationship_edge_id="edge:web:db",
            ),
        )

    def test_missing_startup_command_maps_only_to_runtime_field(self):
        diagnostics = (
            Diagnostic(
                "MISSING_REQUIRED_FIELD",
                "component_runtime",
                "deployable:web",
                "startup_command",
                "startup command missing",
            ),
        )

        repair = report_work_units.diagnostics_to_repair_units(
            diagnostics, self.units
        )

        self.assertEqual(
            repair,
            (
                WorkUnit(
                    "component:deployable:web:runtime",
                    "component_runtime",
                    "deployable:web",
                    ("startup_command",),
                ),
            ),
        )

    def test_relationship_diagnostic_maps_only_to_edge_unit(self):
        diagnostics = (
            Diagnostic(
                "MISSING_RELATIONSHIP_FIELD",
                "relationships",
                "edge:web:db",
                "mechanism",
                "relationship mechanism missing",
            ),
        )

        repair = report_work_units.diagnostics_to_repair_units(
            diagnostics, self.units
        )

        self.assertEqual(repair, (self.units[2],))

    def test_infrastructure_diagnostic_has_no_repair_unit(self):
        diagnostics = (
            Diagnostic(
                "VALIDATOR_INFRASTRUCTURE_ERROR",
                "",
                "",
                "",
                "validator unavailable",
            ),
        )

        repair = report_work_units.diagnostics_to_repair_units(
            diagnostics, self.units
        )

        self.assertEqual(repair, ())


class ReportRepairLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.database = self.workspace / ".report-session/session.sqlite"
        self.store = SQLiteReportSessionStore(self.database)
        self.addCleanup(self.store.close)
        self.document = report_records.load_report_document(DOCUMENT_PATH)
        self.contract = report_contract.load_report_contract()
        self.canonical = self.workspace / "analysis.md"
        self.old_bytes = b"# previous canonical\n"
        self.canonical.write_bytes(self.old_bytes)
        self.target = self.workspace / "target.json"
        self.target.write_text(
            json.dumps(
                {
                    "mode": "summary",
                    "analysis_root": str(EVIDENCE_REPOSITORY),
                    "artifacts": {"report": str(self.canonical)},
                    "validation": {
                        "command": [
                            sys.executable,
                            str(TARGET_GUARD),
                            str(self.target),
                        ],
                        "report_command": [
                            sys.executable,
                            str(REPORT_VALIDATOR),
                            str(self.canonical),
                            "--mode",
                            "summary",
                            "--contract",
                            "new",
                            "--repo-root",
                            str(EVIDENCE_REPOSITORY),
                        ],
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.service = ReportSessionService(self.store)
        started = self.service.start(
            StartCommand(
                session_id="session-1",
                idempotency_key="start-key",
                analysis_snapshot_id="snapshot-1",
                target_hash="a" * 64,
                mode="summary",
                analysis_snapshot=AnalysisSnapshot(
                    mode="summary",
                    deployable_subject_ids=("deployable:jpetstore",),
                    relationship_edge_ids=("edge:jpetstore:mysql",),
                ),
                initial_payload=json.loads(
                    DOCUMENT_PATH.read_text(encoding="utf-8")
                ),
            )
        )
        self.assertEqual(started.state, "READY")

    def lifecycle(self, renderer):
        return ReportLifecycle(
            store=self.store,
            target_json=self.target,
            document_loader=lambda session_id: self.store.transact(
                lambda connection: self.service._load_document(
                    connection, session_id
                )
            ),
            contract=self.contract,
            renderer=renderer,
        )

    def test_validation_failure_issues_exact_repair_lease_then_refinalizes(self):
        def missing_startup(document, contract):
            rendered = report_renderer.render_report(document, contract)
            return "\n".join(
                line
                for line in rendered.splitlines()
                if not line.startswith("- 운영 기동 명령:")
            ) + "\n"

        self.service.lifecycle = self.lifecycle(missing_startup)
        failed = self.service.finalize(
            FinalizeToolCommand("session-1", 0, "finalize-1")
        )

        self.assertEqual(failed.status, "lease_issued")
        self.assertEqual(failed.state, "COLLECTING")
        self.assertEqual(
            failed.lease.allowed_unit_ids,
            ("component:deployable:jpetstore:runtime",),
        )
        self.assertEqual(
            failed.lease.allowed_fields,
            (
                (
                    "component:deployable:jpetstore:runtime",
                    ("startup_command",),
                ),
            ),
        )
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)

        repair_claim = next(
            claim
            for claim in json.loads(
                DOCUMENT_PATH.read_text(encoding="utf-8")
            )["claims"]
            if claim["field"] == "startup_command"
        )
        repair_subject = next(
            subject
            for subject in json.loads(
                DOCUMENT_PATH.read_text(encoding="utf-8")
            )["subjects"]
            if subject["subject_id"] == repair_claim["subject_id"]
        )
        submitted = self.service.submit(
            SubmitChunkCommand(
                session_id="session-1",
                lease_id=failed.lease.lease_id,
                chunk_ordinal=0,
                idempotency_key="repair-submit-1",
                expected_state_version=failed.state_version,
                unit_ids=failed.lease.allowed_unit_ids,
                payload={
                    "mode": "summary",
                    "subjects": [repair_subject],
                    "claims": [repair_claim],
                    "relationships": [],
                },
            )
        )
        self.assertEqual(submitted.status, "rendering_ready")

        self.service.lifecycle = self.lifecycle(report_renderer.render_report)
        completed = self.service.finalize(
            FinalizeToolCommand(
                "session-1", submitted.state_version, "finalize-2"
            )
        )

        self.assertEqual(completed.status, "complete")
        self.assertEqual(completed.state, "COMPLETE")
        self.assertEqual(completed.artifact["path"], str(self.canonical))
        self.assertEqual(completed.artifact["validation"], "passed")
        self.assertEqual(len(completed.artifact["sha256"]), 64)
        self.assertEqual(
            completed.artifact["byte_size"],
            len(self.canonical.read_bytes()),
        )

    def test_unmapped_validation_error_enters_failed_without_repair_lease(self):
        self.store.transact(
            lambda connection: connection.execute(
                "UPDATE sessions SET state = 'REPAIRING', state_version = 1 "
                "WHERE session_id = 'session-1'"
            )
        )

        result = self.service.route_repair_diagnostics(
            "session-1",
            (
                Diagnostic(
                    "VALIDATOR_INFRASTRUCTURE_ERROR",
                    "",
                    "",
                    "",
                    "validator unavailable",
                ),
            ),
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.state, "FAILED")
        self.assertIsNone(result.lease)
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)

    def test_repair_routing_outside_repairing_state_is_rejected(self):
        result = self.service.route_repair_diagnostics(
            "session-1",
            (
                Diagnostic(
                    "MISSING_REQUIRED_FIELD",
                    "component_runtime",
                    "deployable:jpetstore",
                    "startup_command",
                    "startup command missing",
                ),
            ),
        )

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.state, "READY")
        self.assertIsNone(result.lease)

    def test_repair_budget_exhaustion_is_terminal_without_record_rewrite(self):
        def exhaust_budget(connection):
            connection.execute(
                "UPDATE sessions SET state = 'REPAIRING', state_version = 7 "
                "WHERE session_id = 'session-1'"
            )
            connection.executemany(
                "INSERT INTO audit_events("
                "session_id, event_type, state_version, details_json"
                ") VALUES ('session-1', 'REPAIR_LEASE_ISSUED', ?, '{}')",
                ((2,), (4,), (6,)),
            )

        self.store.transact(exhaust_budget)
        claims_before = self.store.transact(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM claims "
                "WHERE session_id = 'session-1'"
            ).fetchone()[0]
        )

        result = self.service.route_repair_diagnostics(
            "session-1",
            (
                Diagnostic(
                    "MISSING_REQUIRED_FIELD",
                    "component_runtime",
                    "deployable:jpetstore",
                    "startup_command",
                    "startup command missing",
                ),
            ),
        )

        claims_after = self.store.transact(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM claims "
                "WHERE session_id = 'session-1'"
            ).fetchone()[0]
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.state, "FAILED")
        self.assertIn("budget", result.message)
        self.assertIsNone(result.lease)
        self.assertEqual(claims_after, claims_before)


if __name__ == "__main__":
    unittest.main()
