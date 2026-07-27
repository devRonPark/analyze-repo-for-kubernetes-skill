from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "tests" / "fixtures" / "black_box_repo"
EXPECTED = ROOT / "tests" / "fixtures" / "regression" / "black_box_expected.json"
LEGACY_EXPECTED = ROOT / "tests" / "fixtures" / "regression" / "expected.json"
REPORT_FIXTURE = ROOT / "tests" / "fixtures" / "regression" / "black_box_report.md"
NORMALIZE_PATH = ROOT / "scripts" / "normalize_report.py"
RUNNER_PATH = ROOT / "scripts" / "run_black_box_eval.py"
REGRESSION_PATH = ROOT / "scripts" / "validate_regression.py"
VALIDATE_REPORT_PATH = ROOT / "scripts" / "validate_report.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REPORT = REPORT_FIXTURE.read_text(encoding="utf-8")


class BlackBoxEvalTests(unittest.TestCase):
    def write_report(self, directory: Path, text: str = REPORT) -> Path:
        report = directory / "black-box-report.md"
        report.write_text(text, encoding="utf-8")
        return report

    def test_report_fixture_passes_report_validator_before_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.write_report(Path(tmp))
            result = subprocess.run(
                [
                    "python3",
                    str(VALIDATE_REPORT_PATH),
                    str(report),
                    "--mode",
                    "summary",
                    "--repo-root",
                    str(REPO),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_normalizer_extracts_core_semantic_fields(self):
        normalizer = load_module("normalize_report", NORMALIZE_PATH)

        normalized = normalizer.normalize_markdown(REPORT)

        self.assertEqual(normalized["workload_candidates"], ["api"])
        self.assertEqual(normalized["workload_kinds"], {"api": "HTTP 서버"})
        self.assertEqual(normalized["repository_defined_runtime_dependencies"], ["postgres"])
        self.assertEqual(normalized["external_runtime_dependencies"], [])
        self.assertEqual(normalized["excluded_candidates"], ["shared-utils"])
        self.assertEqual(
            normalized["repository_launch_definitions"],
            ["docker-compose service api", "package script start"],
        )
        self.assertEqual(normalized["target_environment_baseline"], "미확인")
        self.assertEqual(normalized["design_input_verdict"], "추가 정보 필요")

    def test_regression_comparison_fails_when_expected_semantics_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = self.write_report(tmp_path)
            good = subprocess.run(
                [
                    "python3",
                    str(REGRESSION_PATH),
                    str(EXPECTED),
                    "--actual-report",
                    str(report),
                    "--repo-root",
                    str(REPO),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            mutated_expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
            mutated_expected["expected"]["repository_defined_runtime_dependencies"] = ["redis"]
            mutated_path = tmp_path / "mutated-expected.json"
            mutated_path.write_text(json.dumps(mutated_expected, ensure_ascii=False), encoding="utf-8")
            bad = subprocess.run(
                [
                    "python3",
                    str(REGRESSION_PATH),
                    str(mutated_path),
                    "--actual-report",
                    str(report),
                    "--repo-root",
                    str(REPO),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("repository_defined_runtime_dependencies", bad.stdout)

    def test_legacy_static_fixture_is_schema_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self.write_report(Path(tmp))
            result = subprocess.run(
                [
                    "python3",
                    str(REGRESSION_PATH),
                    str(LEGACY_EXPECTED),
                    "--actual-report",
                    str(report),
                    "--repo-root",
                    str(REPO),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("black_box_expected.json", result.stdout)

    def test_black_box_runner_records_metadata_and_writes_normalized_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = self.write_report(tmp_path)
            output = tmp_path / "result.json"
            result = subprocess.run(
                [
                    "python3",
                    str(RUNNER_PATH),
                    "--repo",
                    str(REPO),
                    "--report",
                    str(report),
                    "--expected",
                    str(EXPECTED),
                    "--output",
                    str(output),
                    "--model",
                    "deterministic-test",
                    "--runtime",
                    "fixture-report",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["metadata"]["model"], "deterministic-test")
        self.assertEqual(payload["metadata"]["runtime"], "fixture-report")
        self.assertIn("skill_commit", payload["metadata"])
        self.assertTrue(payload["comparison"]["passed"])
        self.assertEqual(payload["normalized_actual"]["workload_candidates"], ["api"])

    def test_live_runtime_execution_requires_explicit_opt_in(self):
        blocked = subprocess.run(
            [
                "python3",
                str(RUNNER_PATH),
                "--repo",
                str(REPO),
                "--expected",
                str(EXPECTED),
                "--live-command",
                "python3 -c 'print(1)'",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("--live-command requires --allow-live-runtime", blocked.stderr)


if __name__ == "__main__":
    unittest.main()
