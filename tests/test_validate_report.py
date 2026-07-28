from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import report_contract
from tests.test_package import NEW_VALID_SUMMARY


class CommandLineTests(unittest.TestCase):
    def run_validator(self, text: str, *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.md"
            report.write_text(text, encoding="utf-8")
            return subprocess.run(
                ["python3", str(ROOT / "scripts" / "validate_report.py"), str(report), *args],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_new_summary_title_is_accepted_from_report_contract(self):
        title = report_contract.title_for("summary")
        text = NEW_VALID_SUMMARY.replace("# Kubernetes 설계 입력 요약", f"# {title}", 1)

        result = self.run_validator(text, "--mode", "summary")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("계약: NEW_SUMMARY", result.stdout)

    def test_json_format_emits_structured_missing_field_diagnostic(self):
        text = NEW_VALID_SUMMARY.replace(
            "- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1\n",
            "",
        )

        result = self.run_validator(
            text, "--mode", "summary", "--format", "json"
        )

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["valid"], False)
        self.assertEqual(
            [
                error
                for error in payload["errors"]
                if error["field"] == "startup_command"
            ],
            [
                {
                    "code": "MISSING_REQUIRED_FIELD",
                    "section_key": "component_runtime",
                    "subject_id": "deployable:web",
                    "field": "startup_command",
                    "message": (
                        "### 배포 대상: web에 필수 속성이 없습니다: "
                        "운영 기동 명령"
                    ),
                }
            ],
        )
        self.assertEqual(result.stderr, "")

    def test_json_format_emits_only_valid_result_for_valid_report(self):
        result = self.run_validator(
            NEW_VALID_SUMMARY,
            "--mode",
            "summary",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            json.loads(result.stdout),
            {"valid": True, "errors": []},
        )
        self.assertNotIn("계약:", result.stdout)

    def test_default_text_format_preserves_existing_output(self):
        text = NEW_VALID_SUMMARY.replace(
            "- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1\n",
            "",
        )

        result = self.run_validator(text, "--mode", "summary")

        self.assertEqual(
            result.stdout,
            "계약: NEW_SUMMARY (감지: 섹션명 매칭: 분석 범위 (6/6))\n"
            "실패: ### 배포 대상: web에 필수 속성이 없습니다: "
            "운영 기동 명령\n",
        )
