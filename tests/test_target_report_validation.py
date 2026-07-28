import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/validate_target_report.py"
REPORT_VALIDATOR = ROOT / "scripts/validate_report.py"
VALID_REPORT = ROOT / "tests/fixtures/regression/black_box_report.md"
BLACK_BOX_REPO = ROOT / "tests/fixtures/black_box_repo"
SUMMARY_TEMPLATE = (
    ROOT
    / "skills/analyze-repo-for-kubernetes/assets/migration-summary-template.md"
)


class TargetReportValidationTests(unittest.TestCase):
    def write_target(
        self,
        workspace: Path,
        canonical: Path,
        *,
        report_command=None,
    ) -> Path:
        target = workspace / "target.json"
        target.write_text(
            json.dumps(
                {
                    "artifacts": {"report": str(canonical)},
                    "validation": {
                        "report_command": report_command
                        or [
                            sys.executable,
                            str(REPORT_VALIDATOR),
                            str(canonical),
                            "--mode",
                            "summary",
                            "--repo-root",
                            str(BLACK_BOX_REPO),
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return target

    def run_validator(self, target: Path):
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(target)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_template_canonical_and_populated_alternate_both_fail(self):
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            canonical = workspace / "report.md"
            canonical.write_text(
                SUMMARY_TEMPLATE.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            alternate = workspace / "final-report.md"
            alternate.write_text(
                VALID_REPORT.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            result = self.run_validator(
                self.write_target(workspace, canonical)
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("canonical report validation failed", result.stdout)
        self.assertIn("alternate report-like file exists", result.stdout)
        self.assertIn(str(alternate), result.stdout)

    def test_populated_canonical_with_alternate_is_not_complete(self):
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            canonical = workspace / "report.md"
            canonical.write_text(
                VALID_REPORT.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            alternate = workspace / "analysis-report.md"
            alternate.write_text("# alternate\n", encoding="utf-8")

            result = self.run_validator(
                self.write_target(workspace, canonical)
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn(str(alternate), result.stdout)

    def test_report_command_must_include_canonical_path(self):
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            canonical = workspace / "report.md"
            canonical.write_text(
                VALID_REPORT.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            result = self.run_validator(
                self.write_target(
                    workspace,
                    canonical,
                    report_command=[
                        sys.executable,
                        str(REPORT_VALIDATOR),
                        str(workspace / "other.md"),
                    ],
                )
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("artifacts.report", result.stdout)

    def test_valid_canonical_prints_only_canonical_path(self):
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            canonical = workspace / "report.md"
            canonical.write_text(
                VALID_REPORT.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            result = self.run_validator(
                self.write_target(workspace, canonical)
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, f"{canonical}\n")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
