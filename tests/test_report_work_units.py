from dataclasses import replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import report_contract
import report_records
import report_work_units


def snapshot(mode: str = "summary") -> report_work_units.AnalysisSnapshot:
    return report_work_units.AnalysisSnapshot(
        mode=mode,
        deployable_subject_ids=(
            "deployable:api",
            "deployable:worker",
        ),
        relationship_edge_ids=(
            "edge:api:database",
            "edge:worker:queue",
        ),
    )


class ReportWorkUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = report_contract.load_report_contract()

    def test_summary_units_have_global_component_relationship_and_readiness_shape(self):
        units = report_work_units.build_work_units(
            self.contract, snapshot("summary")
        )

        self.assertEqual(sum(unit.unit_id == "global:scope" for unit in units), 1)
        for subject_id in snapshot().deployable_subject_ids:
            component_units = [
                unit
                for unit in units
                if unit.subject_id == subject_id
                and unit.unit_type.startswith("component_")
            ]
            self.assertEqual(len(component_units), 6)
        self.assertEqual(
            [unit.unit_id for unit in units if unit.unit_type == "relationship"],
            [
                "relationship:edge:api:database",
                "relationship:edge:worker:queue",
            ],
        )
        self.assertEqual(sum(unit.unit_id == "global:readiness" for unit in units), 1)

    def test_detailed_mode_adds_configuration_and_exclusion_units(self):
        summary_ids = {
            unit.unit_id
            for unit in report_work_units.build_work_units(
                self.contract, snapshot("summary")
            )
        }
        detailed_ids = {
            unit.unit_id
            for unit in report_work_units.build_work_units(
                self.contract, snapshot("detailed")
            )
        }

        self.assertEqual(
            detailed_ids - summary_ids,
            {"global:configuration-detail", "global:exclusions-and-blockers"},
        )

    def test_complete_structured_records_are_rendering_ready(self):
        document = report_records.load_report_document(
            ROOT / "tests/fixtures/report_records/jpetstore-summary.json"
        )
        units = report_work_units.build_work_units(
            self.contract,
            report_work_units.AnalysisSnapshot(
                mode="summary",
                deployable_subject_ids=("deployable:jpetstore",),
                relationship_edge_ids=("edge:jpetstore:mysql",),
            ),
        )

        coverage = report_work_units.calculate_coverage(units, document)

        self.assertTrue(coverage.rendering_ready)
        self.assertEqual(coverage.completed_units, coverage.total_units)

    def test_unknown_claim_counts_as_covered_but_missing_claim_does_not(self):
        document = report_records.load_report_document(
            ROOT / "tests/fixtures/report_records/jpetstore-summary.json"
        )
        health = next(
            claim for claim in document.claims if claim.field == "health_check"
        )
        self.assertEqual(health.status, "unknown")
        units = report_work_units.build_work_units(
            self.contract,
            report_work_units.AnalysisSnapshot(
                mode="summary",
                deployable_subject_ids=("deployable:jpetstore",),
                relationship_edge_ids=("edge:jpetstore:mysql",),
            ),
        )

        covered = report_work_units.calculate_coverage(units, document)
        missing = report_work_units.calculate_coverage(
            units,
            replace(
                document,
                claims=tuple(
                    claim
                    for claim in document.claims
                    if claim.claim_id != health.claim_id
                ),
            ),
        )

        self.assertTrue(covered.rendering_ready)
        self.assertFalse(missing.rendering_ready)
        self.assertIn(
            "component:deployable:jpetstore:runtime",
            missing.missing_unit_ids,
        )

    def test_unit_order_is_independent_of_snapshot_inventory_order(self):
        original = snapshot("detailed")
        reversed_snapshot = replace(
            original,
            deployable_subject_ids=tuple(
                reversed(original.deployable_subject_ids)
            ),
            relationship_edge_ids=tuple(
                reversed(original.relationship_edge_ids)
            ),
        )

        first = report_work_units.build_work_units(self.contract, original)
        second = report_work_units.build_work_units(
            self.contract, reversed_snapshot
        )

        self.assertEqual(first, second)
