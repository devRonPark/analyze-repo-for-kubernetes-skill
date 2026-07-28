from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import report_contract


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
