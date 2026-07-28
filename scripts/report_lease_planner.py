from __future__ import annotations

from dataclasses import dataclass, replace
import json

from report_session_models import Lease
from report_work_units import WorkUnit


MIN_OUTPUT_TOKENS = 512
MAX_OUTPUT_TOKENS = 1536
INITIAL_OUTPUT_TOKENS = 1024
MAX_ARGUMENT_BYTES = 8192
MAX_CLAIMS = 32
MAX_RELATIONSHIPS = 8
TOKENS_PER_FIELD = 64
MAX_RETRIES = 3
MAX_NO_PROGRESS = 3


class LeaseLimitExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class LeaseMetrics:
    current_budget: int = INITIAL_OUTPUT_TOKENS
    target_duration: float = 16.0


@dataclass(frozen=True)
class LeasePlanningSnapshot:
    session_id: str
    state_version: int
    pending_units: tuple[WorkUnit, ...]
    active_lease: Lease | None = None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def next_budget(
    current: int,
    target_duration: float,
    observed_duration: float,
) -> int:
    if observed_duration <= 0:
        raise ValueError("observed_duration은 0보다 커야 합니다")
    raw = _clamp(
        current * target_duration / observed_duration,
        MIN_OUTPUT_TOKENS,
        MAX_OUTPUT_TOKENS,
    )
    rate_limited = _clamp(raw, current * 0.5, current * 1.25)
    return int(
        _clamp(
            round(rate_limited),
            MIN_OUTPUT_TOKENS,
            MAX_OUTPUT_TOKENS,
        )
    )


class DynamicLeasePlanner:
    def argument_size(self, lease: Lease) -> int:
        payload = {
            "lease_id": lease.lease_id,
            "allowed_unit_ids": lease.allowed_unit_ids,
            "allowed_fields": lease.allowed_fields,
            "output_token_budget": lease.output_token_budget,
            "max_claims": lease.max_claims,
            "max_relationships": lease.max_relationships,
        }
        return len(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )

    def issue_or_resume(
        self,
        snapshot: LeasePlanningSnapshot,
        metrics: LeaseMetrics,
    ) -> Lease:
        if snapshot.active_lease is not None:
            return snapshot.active_lease
        if not snapshot.pending_units:
            raise ValueError("pending work unit이 없습니다")

        budget = int(
            _clamp(
                metrics.current_budget,
                MIN_OUTPUT_TOKENS,
                MAX_OUTPUT_TOKENS,
            )
        )
        field_capacity = max(1, min(MAX_CLAIMS, budget // TOKENS_PER_FIELD))
        allowed_ids: list[str] = []
        allowed_fields: list[tuple[str, tuple[str, ...]]] = []
        relationship_count = 0
        field_count = 0

        for unit in sorted(snapshot.pending_units, key=lambda item: item.unit_id):
            if unit.relationship_edge_id is not None:
                if relationship_count >= MAX_RELATIONSHIPS:
                    continue
                candidate_ids = (*allowed_ids, unit.unit_id)
                candidate = Lease(
                    lease_id=f"lease:{snapshot.state_version + 1}",
                    session_id=snapshot.session_id,
                    allowed_unit_ids=tuple(candidate_ids),
                    allowed_fields=tuple(allowed_fields),
                    output_token_budget=budget,
                    max_argument_bytes=MAX_ARGUMENT_BYTES,
                    max_claims=MAX_CLAIMS,
                    max_relationships=MAX_RELATIONSHIPS,
                )
                if self.argument_size(candidate) > MAX_ARGUMENT_BYTES:
                    break
                allowed_ids.append(unit.unit_id)
                relationship_count += 1
                continue

            remaining = field_capacity - field_count
            if remaining <= 0:
                break
            selected = unit.required_fields[:remaining]
            if not selected:
                continue
            candidate_fields = (*allowed_fields, (unit.unit_id, selected))
            candidate_ids = (
                (*allowed_ids, unit.unit_id)
                if unit.unit_id not in allowed_ids
                else tuple(allowed_ids)
            )
            candidate = Lease(
                lease_id=f"lease:{snapshot.state_version + 1}",
                session_id=snapshot.session_id,
                allowed_unit_ids=tuple(candidate_ids),
                allowed_fields=tuple(candidate_fields),
                output_token_budget=budget,
                max_argument_bytes=MAX_ARGUMENT_BYTES,
                max_claims=MAX_CLAIMS,
                max_relationships=MAX_RELATIONSHIPS,
            )
            if self.argument_size(candidate) > MAX_ARGUMENT_BYTES:
                break
            allowed_fields.append((unit.unit_id, selected))
            if unit.unit_id not in allowed_ids:
                allowed_ids.append(unit.unit_id)
            field_count += len(selected)

        if not allowed_ids:
            raise ValueError("hard cap 안에 work-unit을 배치할 수 없습니다")
        return Lease(
            lease_id=f"lease:{snapshot.state_version + 1}",
            session_id=snapshot.session_id,
            allowed_unit_ids=tuple(allowed_ids),
            allowed_fields=tuple(allowed_fields),
            output_token_budget=budget,
            max_argument_bytes=MAX_ARGUMENT_BYTES,
            max_claims=MAX_CLAIMS,
            max_relationships=MAX_RELATIONSHIPS,
        )

    def record_transport_failure(self, lease: Lease) -> Lease:
        if lease.retry_count >= MAX_RETRIES:
            raise LeaseLimitExceeded(
                f"lease retry limit을 초과했습니다: {lease.lease_id}"
            )
        flattened = [
            (unit_id, field)
            for unit_id, fields in lease.allowed_fields
            for field in fields
        ]
        keep = max(1, len(flattened) // 2) if flattened else 0
        retained: dict[str, list[str]] = {}
        for unit_id, field in flattened[:keep]:
            retained.setdefault(unit_id, []).append(field)
        allowed_fields = tuple(
            (unit_id, tuple(fields)) for unit_id, fields in retained.items()
        )
        allowed_ids = tuple(
            unit_id
            for unit_id in lease.allowed_unit_ids
            if not lease.allowed_fields or unit_id in retained
        )
        if not allowed_ids:
            allowed_ids = lease.allowed_unit_ids[:1]
        return replace(
            lease,
            allowed_unit_ids=allowed_ids,
            allowed_fields=allowed_fields,
            output_token_budget=max(
                MIN_OUTPUT_TOKENS, lease.output_token_budget // 2
            ),
            retry_count=lease.retry_count + 1,
        )

    def record_success(
        self,
        lease: Lease,
        *,
        observed_duration: float,
        coverage_increased: bool,
        repeated_payload: bool,
    ) -> Lease:
        no_progress = (
            lease.no_progress_count + 1
            if repeated_payload and not coverage_increased
            else 0
        )
        if no_progress >= MAX_NO_PROGRESS:
            raise LeaseLimitExceeded(
                f"lease no-progress limit을 초과했습니다: {lease.lease_id}"
            )
        return replace(
            lease,
            output_token_budget=next_budget(
                lease.output_token_budget,
                16.0,
                observed_duration,
            ),
            no_progress_count=no_progress,
        )
