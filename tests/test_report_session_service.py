import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from report_session_service import (
    ReportSessionService,
    StartCommand,
    SubmitChunkCommand,
    SyncCommand,
)
from report_session_store import SQLiteReportSessionStore
from report_work_units import AnalysisSnapshot


FIXTURE = ROOT / "tests/fixtures/report_records/jpetstore-summary.json"


def empty_payload():
    return {
        "mode": "summary",
        "subjects": [],
        "claims": [],
        "relationships": [],
    }


def global_payload():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["claims"] = [
        claim
        for claim in payload["claims"]
        if claim["section_key"] in {"scope", "readiness"}
    ]
    referenced = {claim["subject_id"] for claim in payload["claims"]}
    payload["subjects"] = [
        subject
        for subject in payload["subjects"]
        if subject["subject_id"] in referenced
    ]
    payload["relationships"] = []
    return payload


def start_command(
    *,
    session_id: str = "session-1",
    idempotency_key: str = "start-1",
    initial_payload=None,
    snapshot=None,
):
    return StartCommand(
        session_id=session_id,
        idempotency_key=idempotency_key,
        analysis_snapshot_id="snapshot-1",
        target_hash="sha256:target",
        mode="summary",
        analysis_snapshot=snapshot
        or AnalysisSnapshot(
            mode="summary",
            deployable_subject_ids=(),
            relationship_edge_ids=(),
        ),
        initial_payload=initial_payload or empty_payload(),
    )


class ReportSessionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.database = Path(self.temporary.name) / ".report-session/session.sqlite"
        self.store = SQLiteReportSessionStore(self.database)
        self.service = ReportSessionService(self.store)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def count(self, table: str) -> int:
        return self.store.transact(
            lambda connection: connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
        )

    def test_start_is_idempotent(self):
        command = start_command()

        first = self.service.start(command)
        second = self.service.start(command)

        self.assertEqual(first, second)
        self.assertEqual(self.count("sessions"), 1)
        self.assertEqual(first.status, "lease_issued")

    def test_fully_covered_start_is_rendering_ready_without_lease(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        command = start_command(
            initial_payload=payload,
            snapshot=AnalysisSnapshot(
                mode="summary",
                deployable_subject_ids=("deployable:jpetstore",),
                relationship_edge_ids=("edge:jpetstore:mysql",),
            ),
        )

        result = self.service.start(command)

        self.assertEqual(result.status, "rendering_ready")
        self.assertEqual(result.state, "READY")
        self.assertIsNone(result.lease)

    def test_stale_version_returns_sync_required_without_write(self):
        started = self.service.start(start_command())
        command = SubmitChunkCommand(
            session_id="session-1",
            lease_id=started.lease.lease_id,
            chunk_ordinal=0,
            idempotency_key="submit-stale",
            expected_state_version=99,
            unit_ids=started.lease.allowed_unit_ids,
            payload=global_payload(),
        )

        result = self.service.submit(command)

        self.assertEqual(result.status, "sync_required")
        self.assertEqual(self.service.sync(SyncCommand("session-1")).state_version, 0)
        self.assertEqual(self.count("claims"), 0)

    def test_invalid_unit_is_rejected_without_state_change(self):
        started = self.service.start(start_command())
        command = SubmitChunkCommand(
            session_id="session-1",
            lease_id=started.lease.lease_id,
            chunk_ordinal=0,
            idempotency_key="submit-invalid-unit",
            expected_state_version=0,
            unit_ids=("global:not-allowed",),
            payload=global_payload(),
        )

        result = self.service.submit(command)

        self.assertEqual(result.status, "rejected")
        self.assertEqual(self.service.sync(SyncCommand("session-1")).state_version, 0)
        self.assertEqual(self.count("claims"), 0)

    def test_lease_completion_advances_coverage_to_ready(self):
        started = self.service.start(start_command())
        command = SubmitChunkCommand(
            session_id="session-1",
            lease_id=started.lease.lease_id,
            chunk_ordinal=0,
            idempotency_key="submit-1",
            expected_state_version=0,
            unit_ids=started.lease.allowed_unit_ids,
            payload=global_payload(),
        )

        result = self.service.submit(command)

        self.assertEqual(result.status, "rendering_ready")
        self.assertEqual(result.state, "READY")
        self.assertEqual(result.state_version, 1)
        self.assertEqual(result.coverage, (2, 2))
        self.assertEqual(self.count("claims"), 10)

    def test_duplicate_submit_returns_original_result_after_version_advance(self):
        started = self.service.start(start_command())
        command = SubmitChunkCommand(
            session_id="session-1",
            lease_id=started.lease.lease_id,
            chunk_ordinal=0,
            idempotency_key="submit-1",
            expected_state_version=0,
            unit_ids=started.lease.allowed_unit_ids,
            payload=global_payload(),
        )

        first = self.service.submit(command)
        second = self.service.submit(command)

        self.assertEqual(first, second)
        self.assertEqual(self.count("chunk_results"), 1)
        self.assertEqual(self.count("claims"), 10)

    def test_duplicate_submit_result_survives_store_reopen(self):
        started = self.service.start(start_command())
        command = SubmitChunkCommand(
            session_id="session-1",
            lease_id=started.lease.lease_id,
            chunk_ordinal=0,
            idempotency_key="submit-reopen",
            expected_state_version=0,
            unit_ids=started.lease.allowed_unit_ids,
            payload=global_payload(),
        )
        first = self.service.submit(command)
        self.store.close()
        reopened_store = SQLiteReportSessionStore(self.database)

        second = ReportSessionService(reopened_store).submit(command)

        self.assertEqual(first, second)
        reopened_store.close()
        self.store = SQLiteReportSessionStore(self.database)

    def test_submit_rejects_claim_count_over_lease_cap_without_write(self):
        started = self.service.start(start_command())
        payload = global_payload()
        original = next(
            claim for claim in payload["claims"] if claim["field"] == "reason"
        )
        payload["claims"] = [
            {
                **original,
                "claim_id": f"readiness:reason:{index}",
            }
            for index in range(33)
        ]
        command = SubmitChunkCommand(
            session_id="session-1",
            lease_id=started.lease.lease_id,
            chunk_ordinal=0,
            idempotency_key="submit-over-cap",
            expected_state_version=0,
            unit_ids=started.lease.allowed_unit_ids,
            payload=payload,
        )

        result = self.service.submit(command)

        self.assertEqual(result.status, "rejected")
        self.assertIn("claim cap", result.message)
        self.assertEqual(self.count("claims"), 0)
        self.assertEqual(self.service.sync(SyncCommand("session-1")).state_version, 0)

    def test_partial_malformed_and_timeout_inputs_create_no_record_write(self):
        started = self.service.start(start_command())
        commands = (
            SubmitChunkCommand(
                session_id="session-1",
                lease_id=started.lease.lease_id,
                chunk_ordinal=0,
                idempotency_key="partial",
                expected_state_version=0,
                unit_ids=started.lease.allowed_unit_ids,
                payload='{"mode":"summary"',
                transport_status="partial",
            ),
            SubmitChunkCommand(
                session_id="session-1",
                lease_id=started.lease.lease_id,
                chunk_ordinal=0,
                idempotency_key="malformed",
                expected_state_version=0,
                unit_ids=started.lease.allowed_unit_ids,
                payload='{"mode":"summary"',
            ),
            SubmitChunkCommand(
                session_id="session-1",
                lease_id=started.lease.lease_id,
                chunk_ordinal=0,
                idempotency_key="timeout",
                expected_state_version=0,
                unit_ids=started.lease.allowed_unit_ids,
                payload=global_payload(),
                transport_status="timeout",
            ),
        )

        results = [self.service.submit(command) for command in commands]

        self.assertEqual([result.status for result in results], ["retryable"] * 3)
        self.assertEqual(self.count("claims"), 0)
        self.assertEqual(self.count("chunk_results"), 0)
        self.assertEqual(self.service.sync(SyncCommand("session-1")).state_version, 0)

    def test_reopen_preserves_active_lease_and_sync_result(self):
        started = self.service.start(start_command())
        self.store.close()

        reopened_store = SQLiteReportSessionStore(self.database)
        reopened_service = ReportSessionService(reopened_store)
        synced = reopened_service.sync(SyncCommand("session-1"))

        self.assertEqual(synced.lease, started.lease)
        self.assertEqual(synced.state_version, 0)
        reopened_store.close()
        self.store = SQLiteReportSessionStore(self.database)
