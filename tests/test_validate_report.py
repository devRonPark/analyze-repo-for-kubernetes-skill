from pathlib import Path
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
