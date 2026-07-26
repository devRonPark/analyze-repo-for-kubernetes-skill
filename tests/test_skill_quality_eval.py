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
REGRESSION_EXPECTED = ROOT / "tests" / "fixtures" / "regression" / "black_box_expected.json"
SKILL_ON_REPORT = ROOT / "tests" / "fixtures" / "regression" / "black_box_report.md"
QUALITY_DIR = ROOT / "tests" / "fixtures" / "quality_eval"
QUALITY_EXPECTED = QUALITY_DIR / "expected_facts.json"
SKILL_OFF_REPORT = QUALITY_DIR / "skill_off_report.md"
COMPARE_PATH = ROOT / "scripts" / "compare_skill_quality.py"
NORMALIZE_PATH = ROOT / "scripts" / "normalize_report.py"
RUNNER_PATH = ROOT / "scripts" / "run_black_box_eval.py"

PROMPT = "Use Local path: tests/fixtures/black_box_repo and produce Kubernetes design inputs."
REVISION = "fixture@abc123"
RUNTIME_OPTIONS = '{"mode":"summary","temperature":0}'
TOOL_PERMISSIONS = "read-only-repository"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SkillQualityEvalTests(unittest.TestCase):
    def test_normalizer_extracts_quality_eval_fields(self):
        normalizer = load_module("normalize_report_quality", NORMALIZE_PATH)

        normalized = normalizer.normalize_markdown(SKILL_ON_REPORT.read_text(encoding="utf-8"))

        self.assertIn("production_startup_commands", normalized)
        self.assertIn("listener_ports", normalized)
        self.assertEqual(normalized["production_startup_commands"], {"api": "npm start"})
        self.assertEqual(normalized["listener_ports"], {"api": ["8080"]})

    def test_black_box_runner_records_skill_mode_and_comparable_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "skill-on-result.json"
            result = subprocess.run(
                [
                    "python3",
                    str(RUNNER_PATH),
                    "--repo",
                    str(REPO),
                    "--report",
                    str(SKILL_ON_REPORT),
                    "--expected",
                    str(REGRESSION_EXPECTED),
                    "--output",
                    str(output),
                    "--model",
                    "deterministic-test",
                    "--runtime",
                    "fixture-report",
                    "--skill-mode",
                    "skill-on",
                    "--prompt",
                    PROMPT,
                    "--repository-revision",
                    REVISION,
                    "--runtime-options",
                    RUNTIME_OPTIONS,
                    "--tool-permissions",
                    TOOL_PERMISSIONS,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["metadata"]["skill_mode"], "skill-on")
        self.assertEqual(payload["metadata"]["prompt"], PROMPT)
        self.assertEqual(payload["metadata"]["repository_revision"], REVISION)
        self.assertEqual(payload["metadata"]["runtime_options"], {"mode": "summary", "temperature": 0})
        self.assertEqual(payload["metadata"]["tool_permissions"], TOOL_PERMISSIONS)

    def test_quality_comparison_cli_reports_scores_deltas_outputs_and_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output = tmp_path / "quality.json"
            markdown = tmp_path / "quality.md"
            result = subprocess.run(
                [
                    "python3",
                    str(COMPARE_PATH),
                    "--repo",
                    str(REPO),
                    "--expected",
                    str(QUALITY_EXPECTED),
                    "--skill-on-report",
                    str(SKILL_ON_REPORT),
                    "--skill-off-report",
                    str(SKILL_OFF_REPORT),
                    "--output",
                    str(output),
                    "--markdown-output",
                    str(markdown),
                    "--model",
                    "deterministic-test",
                    "--runtime",
                    "fixture-report",
                    "--prompt",
                    PROMPT,
                    "--repository-revision",
                    REVISION,
                    "--runtime-options",
                    RUNTIME_OPTIONS,
                    "--tool-permissions",
                    TOOL_PERMISSIONS,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
            markdown_text = markdown.read_text(encoding="utf-8") if markdown.exists() else ""

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["shared_run_context"]["prompt"], PROMPT)
        self.assertEqual(payload["shared_run_context"]["repository_revision"], REVISION)
        self.assertEqual(payload["shared_run_context"]["runtime_options"], {"mode": "summary", "temperature": 0})
        self.assertEqual(payload["shared_run_context"]["tool_permissions"], TOOL_PERMISSIONS)
        self.assertEqual(payload["runs"]["skill_on"]["metadata"]["skill_mode"], "skill-on")
        self.assertEqual(payload["runs"]["skill_off"]["metadata"]["skill_mode"], "skill-off")
        self.assertEqual(payload["runs"]["skill_on"]["normalized_actual"]["workload_candidates"], ["api"])
        self.assertEqual(payload["runs"]["skill_off"]["normalized_actual"]["workload_candidates"], ["api", "shared-utils"])

        on_scores = payload["runs"]["skill_on"]["scores"]
        off_scores = payload["runs"]["skill_off"]["scores"]
        self.assertEqual(on_scores["deployable_component_precision"], 1.0)
        self.assertEqual(on_scores["deployable_component_recall"], 1.0)
        self.assertEqual(off_scores["deployable_component_precision"], 0.5)
        self.assertEqual(off_scores["deployable_component_recall"], 1.0)
        self.assertEqual(off_scores["runtime_dependency_precision"], 0.5)
        self.assertEqual(off_scores["runtime_dependency_recall"], 1.0)
        self.assertEqual(off_scores["production_startup_command_correctness"], 0.0)
        self.assertEqual(off_scores["listener_port_correctness"], 0.0)
        self.assertGreater(payload["runs"]["skill_off"]["measurements"]["unsupported_claim_count"], 0)
        self.assertLess(off_scores["valid_citation_location_rate"], on_scores["valid_citation_location_rate"])
        self.assertEqual(off_scores["design_input_verdict_correctness"], 0.0)
        self.assertEqual(payload["outcome"], "improvement")
        self.assertGreater(payload["aggregate"]["delta"], payload["threshold"])
        self.assertIn("normalized_actual", payload["runs"]["skill_on"])
        self.assertIn("normalized_actual", payload["runs"]["skill_off"])
        self.assertIn("Outcome: improvement", markdown_text)
        self.assertIn("Skill ON", markdown_text)
        self.assertIn("Skill OFF", markdown_text)

    def test_quality_delta_classification_distinguishes_all_outcomes(self):
        self.assertTrue(COMPARE_PATH.is_file(), "compare_skill_quality.py should provide threshold classification")
        comparator = load_module("compare_skill_quality", COMPARE_PATH)

        self.assertEqual(comparator.classify_quality_delta(0.06, 0.05), "improvement")
        self.assertEqual(comparator.classify_quality_delta(0.01, 0.05), "no_measurable_improvement")
        self.assertEqual(comparator.classify_quality_delta(-0.06, 0.05), "regression")


if __name__ == "__main__":
    unittest.main()
