from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from report_session_models import Lease, NewSession, SessionState
from report_session_store import SQLiteReportSessionStore


def new_session(session_id: str = "session-1") -> NewSession:
    return NewSession(
        session_id=session_id,
        start_idempotency_key=f"start:{session_id}",
        analysis_snapshot_id="snapshot-1",
        target_hash="sha256:target",
        mode="summary",
    )


class ReportSessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.database = Path(self.temporary.name) / ".report-session/session.sqlite"

    def tearDown(self):
        self.temporary.cleanup()

    def test_session_survives_store_reopen(self):
        store = SQLiteReportSessionStore(self.database)
        created = store.create(new_session())
        store.close()

        reopened = SQLiteReportSessionStore(self.database)
        loaded = reopened.load(created.session_id)

        self.assertEqual(loaded.state, SessionState.DISCOVERING)
        self.assertEqual(loaded.state_version, 0)
        self.assertEqual(loaded.analysis_snapshot_id, "snapshot-1")
        reopened.close()

    def test_active_lease_survives_store_reopen(self):
        store = SQLiteReportSessionStore(self.database)
        store.create(new_session())
        store.save_lease(
            Lease(
                lease_id="lease-1",
                session_id="session-1",
                allowed_unit_ids=("global:scope",),
                output_token_budget=1024,
                max_argument_bytes=8192,
                max_claims=32,
                max_relationships=8,
            )
        )
        store.close()

        reopened = SQLiteReportSessionStore(self.database)
        loaded = reopened.load("session-1")

        self.assertEqual(loaded.active_lease.lease_id, "lease-1")
        self.assertEqual(loaded.active_lease.allowed_unit_ids, ("global:scope",))
        reopened.close()

    def test_schema_preserves_required_authoritative_tables(self):
        store = SQLiteReportSessionStore(self.database)

        tables = store.transact(
            lambda connection: {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        )

        self.assertTrue(
            {
                "sessions",
                "subjects",
                "claims",
                "relationships",
                "leases",
                "chunk_results",
                "work_units",
                "finalize_results",
                "audit_events",
            }.issubset(tables)
        )
        store.close()

    def test_store_enables_foreign_keys_wal_and_busy_timeout(self):
        store = SQLiteReportSessionStore(self.database)

        settings = store.transact(
            lambda connection: (
                connection.execute("PRAGMA foreign_keys").fetchone()[0],
                connection.execute("PRAGMA journal_mode").fetchone()[0],
                connection.execute("PRAGMA busy_timeout").fetchone()[0],
            )
        )

        self.assertEqual(settings, (1, "wal", 5000))
        store.close()

    def test_unique_idempotency_claim_edge_and_chunk_constraints(self):
        store = SQLiteReportSessionStore(self.database)
        store.create(new_session())
        store.save_lease(
            Lease(
                lease_id="lease-1",
                session_id="session-1",
                allowed_unit_ids=("global:scope",),
                output_token_budget=1024,
                max_argument_bytes=8192,
                max_claims=32,
                max_relationships=8,
            )
        )

        def insert_duplicates(connection):
            connection.execute(
                "INSERT INTO subjects(session_id, subject_id, kind, display_name) "
                "VALUES (?, ?, ?, ?)",
                ("session-1", "subject-1", "scope", "Repository"),
            )
            connection.execute(
                "INSERT INTO claims(session_id, claim_id, subject_id, payload_json) "
                "VALUES (?, ?, ?, ?)",
                ("session-1", "claim-1", "subject-1", "{}"),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO claims(session_id, claim_id, subject_id, payload_json) "
                    "VALUES (?, ?, ?, ?)",
                    ("session-1", "claim-1", "subject-1", "{}"),
                )
            connection.execute(
                "INSERT INTO relationships(session_id, edge_id, payload_json) "
                "VALUES (?, ?, ?)",
                ("session-1", "edge-1", "{}"),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO relationships(session_id, edge_id, payload_json) "
                    "VALUES (?, ?, ?)",
                    ("session-1", "edge-1", "{}"),
                )
            connection.execute(
                "INSERT INTO chunk_results("
                "session_id, lease_id, chunk_ordinal, idempotency_key, result_json"
                ") VALUES (?, ?, ?, ?, ?)",
                ("session-1", "lease-1", 0, "chunk-1", "{}"),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO chunk_results("
                    "session_id, lease_id, chunk_ordinal, idempotency_key, result_json"
                    ") VALUES (?, ?, ?, ?, ?)",
                    ("session-1", "lease-1", 1, "chunk-1", "{}"),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO chunk_results("
                    "session_id, lease_id, chunk_ordinal, idempotency_key, result_json"
                    ") VALUES (?, ?, ?, ?, ?)",
                    ("session-1", "lease-1", 0, "chunk-2", "{}"),
                )

        store.transact(insert_duplicates)
        store.close()
