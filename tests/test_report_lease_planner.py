from dataclasses import replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from report_lease_planner import (
    DynamicLeasePlanner,
    LeaseLimitExceeded,
    LeaseMetrics,
    LeasePlanningSnapshot,
    next_budget,
)
from report_session_models import Lease
from report_work_units import WorkUnit


def field_unit(count: int = 40) -> WorkUnit:
    return WorkUnit(
        unit_id="component:deployable:api:runtime",
        unit_type="component_runtime",
        subject_id="deployable:api",
        required_fields=tuple(f"field_{index:02d}" for index in range(count)),
    )


def relationship_unit(index: int) -> WorkUnit:
    return WorkUnit(
        unit_id=f"relationship:edge-{index:02d}",
        unit_type="relationship",
        subject_id=None,
        required_fields=(),
        relationship_edge_id=f"edge-{index:02d}",
    )


class DynamicLeasePlannerTests(unittest.TestCase):
    def setUp(self):
        self.planner = DynamicLeasePlanner()

    def test_initial_lease_uses_default_budget_and_hard_caps(self):
        lease = self.planner.issue_or_resume(
            LeasePlanningSnapshot(
                session_id="session-1",
                state_version=0,
                pending_units=(field_unit(),),
            ),
            LeaseMetrics(),
        )

        self.assertEqual(lease.output_token_budget, 1024)
        self.assertEqual(lease.max_argument_bytes, 8192)
        self.assertEqual(lease.max_claims, 32)
        self.assertEqual(lease.max_relationships, 8)

    def test_field_heavy_unit_is_split_only_at_field_boundaries(self):
        lease = self.planner.issue_or_resume(
            LeasePlanningSnapshot(
                session_id="session-1",
                state_version=0,
                pending_units=(field_unit(),),
            ),
            LeaseMetrics(),
        )

        self.assertEqual(
            lease.allowed_fields,
            (
                (
                    "component:deployable:api:runtime",
                    tuple(f"field_{index:02d}" for index in range(16)),
                ),
            ),
        )

    def test_relationship_count_is_capped_at_eight(self):
        lease = self.planner.issue_or_resume(
            LeasePlanningSnapshot(
                session_id="session-1",
                state_version=0,
                pending_units=tuple(
                    relationship_unit(index) for index in range(12)
                ),
            ),
            LeaseMetrics(),
        )

        self.assertEqual(len(lease.allowed_unit_ids), 8)

    def test_active_lease_is_resumed_before_new_issue(self):
        active = Lease(
            lease_id="lease-active",
            session_id="session-1",
            allowed_unit_ids=("global:scope",),
            output_token_budget=768,
            max_argument_bytes=8192,
            max_claims=32,
            max_relationships=8,
        )

        resumed = self.planner.issue_or_resume(
            LeasePlanningSnapshot(
                session_id="session-1",
                state_version=9,
                pending_units=(field_unit(),),
                active_lease=active,
            ),
            LeaseMetrics(current_budget=1280),
        )

        self.assertIs(resumed, active)

    def test_latency_budget_is_clamped_and_rate_limited(self):
        self.assertEqual(next_budget(1024, 16.0, 4.0), 1280)
        self.assertEqual(next_budget(1024, 16.0, 64.0), 512)
        self.assertEqual(next_budget(1536, 16.0, 64.0), 768)
        self.assertEqual(next_budget(512, 16.0, 1.0), 640)

    def test_argument_plan_stays_within_eight_kibibytes(self):
        verbose = tuple(
            WorkUnit(
                unit_id=f"component:{'x' * 300}:{index}",
                unit_type="component_runtime",
                subject_id=f"deployable:{index}",
                required_fields=tuple(f"{'f' * 300}-{field}" for field in range(4)),
            )
            for index in range(20)
        )

        lease = self.planner.issue_or_resume(
            LeasePlanningSnapshot(
                session_id="session-1",
                state_version=0,
                pending_units=verbose,
            ),
            LeaseMetrics(current_budget=1536),
        )

        self.assertLessEqual(self.planner.argument_size(lease), 8192)

    def test_transport_retry_limit_is_three(self):
        lease = self.planner.issue_or_resume(
            LeasePlanningSnapshot(
                session_id="session-1",
                state_version=0,
                pending_units=(field_unit(1),),
            ),
            LeaseMetrics(),
        )

        for expected_retry in (1, 2, 3):
            lease = self.planner.record_transport_failure(lease)
            self.assertEqual(lease.retry_count, expected_retry)
        with self.assertRaises(LeaseLimitExceeded):
            self.planner.record_transport_failure(lease)

    def test_same_payload_without_coverage_hits_no_progress_limit(self):
        lease = self.planner.issue_or_resume(
            LeasePlanningSnapshot(
                session_id="session-1",
                state_version=0,
                pending_units=(field_unit(1),),
            ),
            LeaseMetrics(),
        )

        lease = self.planner.record_success(
            lease,
            observed_duration=16.0,
            coverage_increased=False,
            repeated_payload=True,
        )
        lease = self.planner.record_success(
            lease,
            observed_duration=16.0,
            coverage_increased=False,
            repeated_payload=True,
        )
        with self.assertRaises(LeaseLimitExceeded):
            self.planner.record_success(
                lease,
                observed_duration=16.0,
                coverage_increased=False,
                repeated_payload=True,
            )

    def test_success_adjusts_next_budget_and_resets_progress_counter(self):
        lease = replace(
            self.planner.issue_or_resume(
                LeasePlanningSnapshot(
                    session_id="session-1",
                    state_version=0,
                    pending_units=(field_unit(1),),
                ),
                LeaseMetrics(),
            ),
            no_progress_count=2,
        )

        adjusted = self.planner.record_success(
            lease,
            observed_duration=8.0,
            coverage_increased=True,
            repeated_payload=False,
        )

        self.assertEqual(adjusted.output_token_budget, 1280)
        self.assertEqual(adjusted.no_progress_count, 0)
