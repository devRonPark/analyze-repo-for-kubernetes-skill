from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/report_records"
EVIDENCE_REPOSITORY = FIXTURES / "repository"
sys.path.insert(0, str(ROOT / "scripts"))
import report_contract
import report_records
import report_renderer


def load_fixture(name: str) -> report_records.ReportDocument:
    return report_records.load_report_document(FIXTURES / name)


def reverse_record_order(
    document: report_records.ReportDocument,
) -> report_records.ReportDocument:
    return replace(
        document,
        subjects=tuple(reversed(document.subjects)),
        claims=tuple(reversed(document.claims)),
        relationships=tuple(reversed(document.relationships)),
    )


class ReportRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = report_contract.load_report_contract()

    def test_render_is_independent_of_input_record_order(self):
        document = load_fixture("jpetstore-summary.json")

        first = report_renderer.render_report(document, self.contract)
        second = report_renderer.render_report(
            reverse_record_order(document), self.contract
        )

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("# Kubernetes 설계 입력 요약\n"))

    def test_render_uses_korean_status_reason_and_one_verdict(self):
        rendered = report_renderer.render_report(
            load_fixture("jpetstore-summary.json"), self.contract
        )

        self.assertIn("상태: 추정됨", rendered)
        self.assertIn("/ 판단: build plugin으로 추론", rendered)
        self.assertEqual(rendered.count("- 판정: "), 1)

    def test_detailed_render_has_matrix_graph_and_detailed_only_sections(self):
        rendered = report_renderer.render_report(
            load_fixture("jpetstore-detailed.json"), self.contract
        )

        self.assertIn("### Dependency matrix", rendered)
        self.assertIn("### Text dependency graph", rendered)
        self.assertIn("## 6. 설정과 상태 상세", rendered)
        self.assertIn("## 7. 제외 항목과 설계 차단 항목 상세", rendered)

    def test_both_modes_pass_new_contract_validator(self):
        with TemporaryDirectory() as directory:
            for mode in ("summary", "detailed"):
                document = load_fixture(f"jpetstore-{mode}.json")
                diagnostics = report_records.validate_document(
                    document,
                    self.contract,
                    repository_root=EVIDENCE_REPOSITORY,
                )
                self.assertEqual(diagnostics, ())
                report = Path(directory) / f"{mode}.md"
                report.write_text(
                    report_renderer.render_report(document, self.contract),
                    encoding="utf-8",
                )

                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts/validate_report.py"),
                        str(report),
                        "--mode",
                        mode,
                        "--contract",
                        "new",
                        "--repo-root",
                        str(EVIDENCE_REPOSITORY),
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_evidence_is_rejected_before_render(self):
        document = load_fixture("jpetstore-summary.json")
        first = document.claims[0]
        invalid = replace(
            document,
            claims=(
                replace(first, evidence=("missing/file.yml:1",)),
                *document.claims[1:],
            ),
        )

        diagnostics = report_records.validate_document(
            invalid,
            self.contract,
            repository_root=EVIDENCE_REPOSITORY,
        )

        self.assertIn("MISSING_EVIDENCE_FILE", [item.code for item in diagnostics])
