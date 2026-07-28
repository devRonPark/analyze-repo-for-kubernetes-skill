import fcntl
import json
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import time
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
        self.canonical = self.workspace / "report.md"
        self.old_bytes = b"# existing canonical\n"
        self.canonical.write_bytes(self.old_bytes)
        self.target = self.workspace / "target.json"
        self.write_target()
        self.service = ReportSessionService(self.store)
        started = self.service.start(
            StartCommand(
                session_id="session-1",
                idempotency_key="start-key",
                analysis_snapshot_id="snapshot-1",
                target_hash=sha256(self.target.read_bytes()).hexdigest(),
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
            "recovery_session_id": "session-1",
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

    def test_verified_payload_preserves_lexical_target_identity(self):
        target_bytes = self.target.read_bytes()
        target_payload = json.loads(target_bytes)
        outside = self.workspace / "outside"
        outside.mkdir()
        outside_target = outside / "target.json"
        outside_target.write_bytes(target_bytes)
        self.target.unlink()
        self.target.symlink_to(outside_target)

        lifecycle = self.lifecycle(
            target_payload=target_payload,
            verified_target_bytes=target_bytes,
        )

        self.assertEqual(lifecycle.target_json, self.target)
        self.assertEqual(lifecycle.workspace, self.workspace)

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

    def test_restart_after_begin_transition_recovers_same_finalize(self):
        def crash(phase):
            if phase == "begin_started":
                raise SimulatedCrash("process stopped after begin")

        lifecycle = self.lifecycle(crash_hook=crash)
        with self.assertRaises(SimulatedCrash):
            self.finalize(lifecycle)
        self.assertEqual(
            self.store.load("session-1").state.value,
            "ASSEMBLING",
        )

        result = self.finalize(self.lifecycle())

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.state, "COMPLETE")

    def test_restart_after_rollback_preserves_restored_canonical(self):
        self.old_bytes = report_renderer.render_report(
            self.document, self.contract
        ).encode("utf-8")
        self.canonical.write_bytes(self.old_bytes)
        (self.workspace / "alternate-report.md").write_text(
            "# alternate\n", encoding="utf-8"
        )

        def crash(phase):
            if phase == "rollback_completed":
                raise SimulatedCrash("process stopped after rollback")

        lifecycle = self.lifecycle(crash_hook=crash)
        with self.assertRaises(SimulatedCrash):
            self.finalize(lifecycle)
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)
        (self.workspace / "alternate-report.md").unlink()

        result = self.finalize(self.lifecycle())

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.state, "FAILED")
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)

    def test_restart_after_validation_diagnostics_recovers_repairing(self):
        def crash(phase):
            if phase == "validation_failure_recorded":
                raise SimulatedCrash(
                    "process stopped after diagnostics journal"
                )

        lifecycle = self.lifecycle(
            renderer=lambda document, contract: "# invalid candidate\n",
            crash_hook=crash,
        )
        with self.assertRaises(SimulatedCrash):
            self.finalize(lifecycle)
        self.assertEqual(
            self.store.load("session-1").state.value,
            "VALIDATING",
        )

        result = self.finalize(
            self.lifecycle(
                renderer=lambda document, contract: "# invalid candidate\n"
            )
        )

        self.assertEqual(result.status, "validation_failed")
        self.assertEqual(result.state, "REPAIRING")

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

    def test_changed_target_hash_fails_before_candidate_write(self):
        self.target.write_text(
            self.target.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )

        result = self.finalize()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.state, "FAILED")
        self.assertIn("target hash", result.message)
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)
        self.assertFalse(
            (self.workspace / ".candidate-session-1.tmp").exists()
        )

    def test_canonical_path_outside_target_workspace_is_rejected(self):
        outside = self.workspace.parent / "outside-analysis.md"
        self.target.write_text(
            json.dumps(
                {
                    "mode": "summary",
                    "artifacts": {"report": str(outside)},
                    "validation": {
                        "command": [
                            sys.executable,
                            str(TARGET_GUARD),
                            str(self.target),
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "workspace"):
            self.lifecycle()

    def test_finalize_waits_for_cross_process_workspace_lock(self):
        lock_path = (
            self.canonical.parent / ".report-session/finalize.lock"
        )
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_stream = lock_path.open("a+b")
        self.addCleanup(lock_stream.close)
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        started = threading.Event()
        outcomes = []

        def finalize_in_worker():
            worker_store = SQLiteReportSessionStore(self.database)
            try:
                lifecycle = ReportLifecycle(
                    store=worker_store,
                    target_json=self.target,
                    document_loader=lambda session_id: self.document,
                    contract=self.contract,
                )
                started.set()
                outcomes.append(
                    lifecycle.finalize(
                        "session-1",
                        self.initial_version,
                        "worker-finalize",
                    )
                )
            finally:
                worker_store.close()

        worker = threading.Thread(target=finalize_in_worker)
        worker.start()
        self.assertTrue(started.wait(timeout=1))
        time.sleep(0.1)
        self.assertTrue(worker.is_alive())
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)

        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
        worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(outcomes[0].status, "complete")

    def test_changed_target_cannot_fail_another_journal_owner(self):
        def crash(phase):
            if phase == "begin_started":
                raise SimulatedCrash("owner stopped after begin")

        with self.assertRaises(SimulatedCrash):
            self.finalize(self.lifecycle(crash_hook=crash))
        second = self.service.start(
            StartCommand(
                session_id="session-2",
                idempotency_key="start-key-2",
                analysis_snapshot_id="snapshot-2",
                target_hash=sha256(self.target.read_bytes()).hexdigest(),
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
        self.assertEqual(second.state, "READY")
        self.target.write_text(
            self.target.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )

        result = self.lifecycle().finalize(
            "session-2", second.state_version, "finalize-session-2"
        )

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.session_id, "session-2")
        self.assertEqual(
            self.store.load("session-1").state.value,
            "ASSEMBLING",
        )
        self.assertEqual(
            self.store.load("session-2").state.value,
            "READY",
        )

    def test_changed_canonical_path_recovers_original_journal_paths(self):
        def crash(phase):
            if phase == "candidate_written":
                raise SimulatedCrash("owner stopped after candidate")

        original_lifecycle = self.lifecycle(crash_hook=crash)
        original_candidate = original_lifecycle.candidate_path(
            "session-1"
        )
        with self.assertRaises(SimulatedCrash):
            self.finalize(original_lifecycle)
        self.assertTrue(original_candidate.exists())

        changed_directory = self.workspace / "changed"
        changed_directory.mkdir()
        changed_canonical = changed_directory / "analysis.md"
        changed_canonical.write_text(
            "# unrelated canonical\n", encoding="utf-8"
        )
        target_payload = json.loads(
            self.target.read_text(encoding="utf-8")
        )
        target_payload["artifacts"]["report"] = str(changed_canonical)
        self.target.write_text(
            json.dumps(target_payload),
            encoding="utf-8",
        )

        result = self.lifecycle().finalize(
            "session-1",
            self.initial_version,
            "finalize-key",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)
        self.assertEqual(
            changed_canonical.read_text(encoding="utf-8"),
            "# unrelated canonical\n",
        )
        self.assertFalse(original_candidate.exists())
        self.assertFalse(
            (
                self.workspace
                / ".report-session/finalize-journal.json"
            ).exists()
        )

    def test_malformed_target_after_crash_recovers_original_journal(self):
        def crash(phase):
            if phase == "candidate_written":
                raise SimulatedCrash("owner stopped after candidate")

        original_lifecycle = self.lifecycle(crash_hook=crash)
        original_candidate = original_lifecycle.candidate_path(
            "session-1"
        )
        with self.assertRaises(SimulatedCrash):
            self.finalize(original_lifecycle)
        self.target.write_text("{not-json", encoding="utf-8")

        result = self.lifecycle().finalize(
            "session-1",
            self.initial_version,
            "finalize-key",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.state, "FAILED")
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)
        self.assertFalse(original_candidate.exists())
        self.assertFalse(
            (
                self.workspace
                / ".report-session/finalize-journal.json"
            ).exists()
        )

    def test_malformed_target_journal_cannot_recover_other_session(self):
        def crash(phase):
            if phase == "candidate_written":
                raise SimulatedCrash("owner stopped after candidate")

        with self.assertRaises(SimulatedCrash):
            self.finalize(self.lifecycle(crash_hook=crash))
        self.target.write_text("{not-json", encoding="utf-8")

        with self.assertRaises(ValueError):
            self.lifecycle(recovery_session_id="session-2")

    def test_outside_target_path_after_crash_recovers_original_journal(self):
        def crash(phase):
            if phase == "candidate_written":
                raise SimulatedCrash("owner stopped after candidate")

        original_lifecycle = self.lifecycle(crash_hook=crash)
        original_candidate = original_lifecycle.candidate_path(
            "session-1"
        )
        with self.assertRaises(SimulatedCrash):
            self.finalize(original_lifecycle)
        outside = self.workspace.parent / "outside-after-crash.md"
        outside.write_text("# outside\n", encoding="utf-8")
        target_payload = json.loads(
            self.target.read_text(encoding="utf-8")
        )
        target_payload["artifacts"]["report"] = str(outside)
        self.target.write_text(
            json.dumps(target_payload),
            encoding="utf-8",
        )

        result = self.lifecycle().finalize(
            "session-1",
            self.initial_version,
            "finalize-key",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.state, "FAILED")
        self.assertEqual(self.canonical.read_bytes(), self.old_bytes)
        self.assertEqual(
            outside.read_text(encoding="utf-8"),
            "# outside\n",
        )
        self.assertFalse(original_candidate.exists())
        self.assertFalse(
            (
                self.workspace
                / ".report-session/finalize-journal.json"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
