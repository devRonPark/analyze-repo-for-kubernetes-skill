from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import sqlite3
from typing import TypeVar

from report_session_models import Lease, NewSession, SessionSnapshot, SessionState


T = TypeVar("T")
SCHEMA_VERSION = 4
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    start_idempotency_key TEXT NOT NULL UNIQUE,
    analysis_snapshot_id TEXT NOT NULL,
    target_hash TEXT NOT NULL,
    target_identity TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL,
    state TEXT NOT NULL,
    state_version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subjects (
    session_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    display_name TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (session_id, subject_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS claims (
    session_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (session_id, claim_id),
    FOREIGN KEY (session_id, subject_id)
        REFERENCES subjects(session_id, subject_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS relationships (
    session_id TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (session_id, edge_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS leases (
    session_id TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    allowed_unit_ids_json TEXT NOT NULL,
    allowed_fields_json TEXT NOT NULL DEFAULT '[]',
    output_token_budget INTEGER NOT NULL,
    max_argument_bytes INTEGER NOT NULL,
    max_claims INTEGER NOT NULL,
    max_relationships INTEGER NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    no_progress_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, lease_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_lease_per_session
ON leases(session_id) WHERE status = 'ACTIVE';

CREATE TABLE IF NOT EXISTS chunk_results (
    session_id TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    chunk_ordinal INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_hash TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, idempotency_key),
    UNIQUE (session_id, lease_id, chunk_ordinal),
    FOREIGN KEY (session_id, lease_id)
        REFERENCES leases(session_id, lease_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS start_results (
    session_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (idempotency_key),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS work_units (
    session_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    unit_type TEXT NOT NULL,
    subject_id TEXT,
    required_fields_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    PRIMARY KEY (session_id, unit_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS finalize_results (
    session_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, idempotency_key),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    state_version INTEGER NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
"""


class SQLiteReportSessionStore:
    def __init__(self, database: Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.database,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(SCHEMA)
        columns = {
            row[1]
            for row in self._connection.execute(
                "PRAGMA table_info(sessions)"
            )
        }
        if "target_identity" not in columns:
            self._connection.execute(
                "ALTER TABLE sessions ADD COLUMN "
                "target_identity TEXT NOT NULL DEFAULT ''"
            )
        self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        self._connection.close()

    def transact(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            result = operation(self._connection)
        except BaseException:
            self._connection.rollback()
            raise
        self._connection.commit()
        return result

    def create(self, session: NewSession) -> SessionSnapshot:
        def insert(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                INSERT INTO sessions(
                    session_id,
                    start_idempotency_key,
                    analysis_snapshot_id,
                    target_hash,
                    target_identity,
                    mode,
                    state,
                    state_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    session.session_id,
                    session.start_idempotency_key,
                    session.analysis_snapshot_id,
                    session.target_hash,
                    session.target_identity,
                    session.mode,
                    SessionState.DISCOVERING.value,
                ),
            )
            connection.execute(
                """
                INSERT INTO audit_events(
                    session_id, event_type, state_version, details_json
                ) VALUES (?, 'SESSION_CREATED', 0, '{}')
                """,
                (session.session_id,),
            )

        self.transact(insert)
        return self.load(session.session_id)

    def save_lease(self, lease: Lease) -> None:
        self.transact(
            lambda connection: connection.execute(
                """
                INSERT INTO leases(
                    session_id,
                    lease_id,
                    allowed_unit_ids_json,
                    allowed_fields_json,
                    output_token_budget,
                    max_argument_bytes,
                    max_claims,
                    max_relationships,
                    retry_count,
                    no_progress_count,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lease.session_id,
                    lease.lease_id,
                    json.dumps(
                        lease.allowed_unit_ids,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        lease.allowed_fields,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    lease.output_token_budget,
                    lease.max_argument_bytes,
                    lease.max_claims,
                    lease.max_relationships,
                    lease.retry_count,
                    lease.no_progress_count,
                    lease.status,
                ),
            )
        )

    def load(self, session_id: str) -> SessionSnapshot:
        row = self._connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"report session을 찾을 수 없습니다: {session_id}")
        lease_row = self._connection.execute(
            """
            SELECT * FROM leases
            WHERE session_id = ? AND status = 'ACTIVE'
            ORDER BY created_at, lease_id
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        active_lease = None
        if lease_row is not None:
            active_lease = Lease(
                lease_id=lease_row["lease_id"],
                session_id=lease_row["session_id"],
                allowed_unit_ids=tuple(
                    json.loads(lease_row["allowed_unit_ids_json"])
                ),
                output_token_budget=lease_row["output_token_budget"],
                max_argument_bytes=lease_row["max_argument_bytes"],
                max_claims=lease_row["max_claims"],
                max_relationships=lease_row["max_relationships"],
                allowed_fields=tuple(
                    (item[0], tuple(item[1]))
                    for item in json.loads(lease_row["allowed_fields_json"])
                ),
                retry_count=lease_row["retry_count"],
                no_progress_count=lease_row["no_progress_count"],
                status=lease_row["status"],
            )
        return SessionSnapshot(
            session_id=row["session_id"],
            start_idempotency_key=row["start_idempotency_key"],
            analysis_snapshot_id=row["analysis_snapshot_id"],
            target_hash=row["target_hash"],
            mode=row["mode"],
            state=SessionState(row["state"]),
            state_version=row["state_version"],
            active_lease=active_lease,
            target_identity=row["target_identity"],
        )
