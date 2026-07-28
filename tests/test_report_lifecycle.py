import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import report_contract
import report_records
import report_renderer
from report_lifecycle import ReportLifecycle
from report_session_service import (
    ReportSessionService,
    StartCommand,
)
from report_session_store import SQLiteReportSessionStore
from report_work_units import AnalysisSnapshot


FIXTURES = ROOT / "tests/fixtures/report_records"
EVIDENCE_REPOSITORY = FIXTURES / "repository"
DOCUMENT_PATH = FIXTURES / "jpetstore-summary.json"
TARGET_GUARD = ROOT / "scripts/validate_target_report.py"
REPORT_VALIDATOR = ROOT / "scripts/validate_report.py"


class SimulatedCrash(RuntimeError):
    pass


class ReportLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.database = self.workspace / ".report-session/session.sqlite"
        self.store = SQLiteReportSessionStore(self.database)
        self.addCleanup(self.store.close)
        self.document = report_records.load_report_document(DOCUMENT_PATH)
        self.contract = report_contract.load_report_contract()
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
        self.initial_version = started.state_version
        self.canonical = self.workspace / "report.md"
        self.old_bytes = b"# existing canonical\n"
        self.canonical.write_bytes(self.old_bytes)
        self.target = self.workspace / "target.json"
        self.write_target()

    def write_target(self):
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

    def lifecycle(self, **overrides):
        options = {
            "store": self.store,
            "target_json": self.target,
            "document_loader": lambda session_id: self.document,
            "contract": self.contract,
        }
        options.update(overrides)
        return ReportLifecycle(**options)

    def finalize(self, lifecycle=None, **overrides):
        values = {
            "session_id": "session-1",
            "expected_state_version": self.initial_version,
            "idempotency_key": "finalize-key",
        }
        values.update(overrides)
        return (lifecycle or self.lifecycle()).finalize(**values)

    def test_successful_validation_atomically_replaces_canonical(self):
        result = self.finalize()

        expected = report_renderer.render_report(
            self.document, self.contract
        ).encode("utf-8")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.state, "COMPLETE")
        self.assertEqual(self.canonical.read_bytes(), expected)
        self.assertEqual(result.artifact["path"], str(self.canonical))
        self.assertEqual(result.artifact["byte_size"], len(expected))
        self.assertEqual(result.artifact["validation"], "passed")
        self.assertEqual(len(result.artifact["sha256"]), 64)
        self.assertFalse(
            (self.workspace / ".candidate-session-1.tmp").exists()
        )
        self.assertFalse(
            (self.workspace / ".previous-session-1.tmp").exists()
        )

    def test_candidate_validation_failure_preserves_old_canonical_bytes(self):
        lifecycle = self.lifecycle(
            renderer=lambda document, contract: "# invalid candidate\n"
        )

        result = self.finalize(lifecycle)

        self.assertEqual(result.status, "validation_failed")
        self.assertEqual(result.state, "REPAIRING")
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)

    def test_target_guard_failure_rolls_back_old_canonical(self):
        (self.workspace / "final-report.md").write_text(
            "# alternate\n", encoding="utf-8"
        )

        result = self.finalize()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.state, "FAILED")
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)

    def test_restart_after_candidate_creation_recovers_same_finalize(self):
        def crash(phase):
            if phase == "candidate_written":
                raise SimulatedCrash("process stopped")

        lifecycle = self.lifecycle(crash_hook=crash)
        with self.assertRaises(SimulatedCrash):
            self.finalize(lifecycle)
        self.store.close()
        reopened = SQLiteReportSessionStore(self.database)
        self.store = reopened

        result = self.finalize(self.lifecycle())

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.state, "COMPLETE")

    def test_duplicate_finalize_returns_same_artifact_without_new_version(self):
        first = self.finalize()
        version = self.store.load("session-1").state_version

        second = self.finalize()

        self.assertEqual(first, second)
        self.assertEqual(
            self.store.load("session-1").state_version,
            version,
        )

    def test_stale_finalize_does_not_write_candidate_or_change_state(self):
        result = self.finalize(expected_state_version=99)

        self.assertEqual(result.status, "sync_required")
        self.assertEqual(
            self.store.load("session-1").state_version,
            self.initial_version,
        )
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)
        self.assertFalse(
            (self.workspace / ".candidate-session-1.tmp").exists()
        )


if __name__ == "__main__":
    unittest.main()
