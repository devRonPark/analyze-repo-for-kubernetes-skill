from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SessionState(str, Enum):
    DISCOVERING = "DISCOVERING"
    COLLECTING = "COLLECTING"
    READY = "READY"
    ASSEMBLING = "ASSEMBLING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class NewSession:
    session_id: str
    start_idempotency_key: str
    analysis_snapshot_id: str
    target_hash: str
    mode: str


@dataclass(frozen=True)
class Lease:
    lease_id: str
    session_id: str
    allowed_unit_ids: tuple[str, ...]
    output_token_budget: int
    max_argument_bytes: int
    max_claims: int
    max_relationships: int
    allowed_fields: tuple[tuple[str, tuple[str, ...]], ...] = ()
    retry_count: int = 0
    no_progress_count: int = 0
    status: str = "ACTIVE"


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str
    start_idempotency_key: str
    analysis_snapshot_id: str
    target_hash: str
    mode: str
    state: SessionState
    state_version: int
    active_lease: Lease | None = None
