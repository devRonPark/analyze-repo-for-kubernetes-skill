from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import report_contract
import validate_report


class ReportContractTests(unittest.TestCase):
    def test_new_summary_contract_has_the_expected_title_and_ordered_headings(self):
        contract = report_contract.load_report_contract()

        self.assertEqual(contract.schema_version, "report-contract/v1")
        self.assertEqual(report_contract.title_for("summary"), "Kubernetes 설계 입력 요약")
        self.assertEqual(
            report_contract.headings_for("summary"),
            (
                "## 1. 분석 범위",
                "## 2. 배포 대상 후보",
                "## 3. 배포 대상별 실행 정보",
                "## 4. 구성과 관계",
                "## 5. 운영 환경 배포 근거",
                "## 6. Kubernetes 설계 입력 상태",
            ),
        )

    def test_detailed_contract_has_the_expected_title_and_ordered_headings(self):
        self.assertEqual(report_contract.title_for("detailed"), "Kubernetes 설계 입력 상세 평가")
        self.assertEqual(
            report_contract.headings_for("detailed")[-2:],
            (
                "## 7. 제외 항목과 설계 차단 항목 상세",
                "## 8. Kubernetes 설계 입력 상태",
            ),
        )

    def test_loader_rejects_missing_required_mode(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-report-contract.json"
            path.write_text(
                '{"schema_version":"report-contract/v1","modes":{"summary":{"title":"summary","sections":[{"key":"scope","heading":"## scope","renderer_type":"scope"}]}}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "detailed"):
                report_contract.load_report_contract(path)

    def test_validator_new_section_constants_come_from_report_contract(self):
        summary_headings = ("## contract summary",)
        detailed_headings = ("## contract detailed",)
        with patch.object(
            report_contract,
            "headings_for",
            side_effect=lambda mode: summary_headings if mode == "summary" else detailed_headings,
        ), patch.object(
            report_contract,
            "title_for",
            side_effect=lambda mode: f"contract {mode}",
        ):
            import importlib

            reloaded = importlib.reload(validate_report)
            self.assertEqual(tuple(reloaded.NEW_SUMMARY_SECTIONS), summary_headings)
            self.assertEqual(tuple(reloaded.NEW_DETAILED_SECTIONS), detailed_headings)
            self.assertEqual(reloaded.NEW_REPORT_TITLES["summary"], "contract summary")
        importlib.reload(validate_report)
