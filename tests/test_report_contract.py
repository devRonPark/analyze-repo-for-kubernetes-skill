import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import report_contract
import validate_report


def template_h2_headings(path: Path) -> tuple[str, ...]:
    return tuple(re.findall(r"(?m)^## .+$", path.read_text(encoding="utf-8")))


class ReportContractTests(unittest.TestCase):
    def test_component_runtime_fields_are_ordered_and_required(self):
        fields = report_contract.load_report_contract().fields_for("component_runtime")

        self.assertEqual(
            [field.field_id for field in fields[:4]],
            ["execution_form", "path", "language", "framework"],
        )
        self.assertTrue(all(field.required for field in fields))
        self.assertEqual(fields[-1].label, "상태 확인")

    def test_field_lookup_rejects_unknown_renderer_metadata(self):
        payload = json.loads(
            report_contract.DEFAULT_CONTRACT_PATH.read_text(encoding="utf-8")
        )
        payload["field_groups"]["scope"][0]["renderer"] = "model_markdown"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-report-contract.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "renderer"):
                report_contract.load_report_contract(path)

    def test_loader_rejects_missing_required_field_group(self):
        payload = json.loads(
            report_contract.DEFAULT_CONTRACT_PATH.read_text(encoding="utf-8")
        )
        del payload["field_groups"]["readiness"]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-report-contract.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "readiness"):
                report_contract.load_report_contract(path)

    def test_loader_rejects_duplicate_field_id(self):
        payload = json.loads(
            report_contract.DEFAULT_CONTRACT_PATH.read_text(encoding="utf-8")
        )
        payload["field_groups"]["scope"][1]["field_id"] = "target_type"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-report-contract.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "중복 field ID"):
                report_contract.load_report_contract(path)

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
        payload = json.loads(
            report_contract.DEFAULT_CONTRACT_PATH.read_text(encoding="utf-8")
        )
        del payload["modes"]["detailed"]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-report-contract.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "detailed"):
                report_contract.load_report_contract(path)

    def test_loader_rejects_malformed_root(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-report-contract.json"
            path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "root"):
                report_contract.load_report_contract(path)

    def test_loader_rejects_duplicate_section_key(self):
        payload = json.loads(
            report_contract.DEFAULT_CONTRACT_PATH.read_text(encoding="utf-8")
        )
        payload["modes"]["summary"]["sections"][1]["key"] = "scope"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-report-contract.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "중복 section"):
                report_contract.load_report_contract(path)

    def test_mode_rejects_unknown_section(self):
        mode = report_contract.load_report_contract().mode("summary")

        with self.assertRaisesRegex(ValueError, "지원하지 않는 section.*unknown"):
            mode.section("unknown")

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

    def test_summary_template_h2_headings_match_the_contract(self):
        self.assertEqual(
            template_h2_headings(
                ROOT
                / "skills/analyze-repo-for-kubernetes/assets/migration-summary-template.md"
            ),
            report_contract.headings_for("summary"),
        )

    def test_detailed_template_h2_headings_match_the_contract(self):
        self.assertEqual(
            template_h2_headings(
                ROOT
                / "skills/analyze-repo-for-kubernetes/assets/migration-assessment-template.md"
            ),
            report_contract.headings_for("detailed"),
        )
