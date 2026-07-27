from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVAL_PATH = ROOT / "scripts" / "eval_trigger_precision.py"
CASES_PATH = ROOT / "tests" / "fixtures" / "eval" / "trigger_cases.json"

SPEC = importlib.util.spec_from_file_location("eval_trigger_precision", EVAL_PATH)
assert SPEC and SPEC.loader
EVAL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EVAL
SPEC.loader.exec_module(EVAL)


class TriggerPrecisionEvalTests(unittest.TestCase):
    def test_reviewed_cases_produce_exact_trigger_metrics_from_runtime_events(self):
        cases = EVAL.load_cases(CASES_PATH)

        self.assertEqual(len(cases), 12)
        self.assertEqual(sum(1 for case in cases if not case.should_trigger), 6)

        report = EVAL.evaluate_cases(cases)

        self.assertEqual(report.metrics.total, 12)
        self.assertEqual(report.metrics.true_positives, 6)
        self.assertEqual(report.metrics.false_positives, 0)
        self.assertEqual(report.metrics.true_negatives, 6)
        self.assertEqual(report.metrics.false_negatives, 0)
        self.assertEqual(report.metrics.precision, 1.0)
        self.assertEqual(report.metrics.recall, 1.0)
        self.assertTrue(all(result.observed_trigger == result.should_trigger for result in report.results))

    def test_cli_emits_json_and_markdown_reports(self):
        json_result = subprocess.run(
            ["python3", str(EVAL_PATH), str(CASES_PATH), "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        payload = json.loads(json_result.stdout)
        self.assertEqual(
            payload["metrics"],
            {
                "total": 12,
                "true_positives": 6,
                "false_positives": 0,
                "true_negatives": 6,
                "false_negatives": 0,
                "precision": 1.0,
                "recall": 1.0,
            },
        )
        self.assertEqual(len(payload["results"]), 12)

        markdown_result = subprocess.run(
            ["python3", str(EVAL_PATH), str(CASES_PATH), "--format", "markdown"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
        self.assertIn("# Trigger Precision Report", markdown_result.stdout)
        self.assertIn("- True positives: 6", markdown_result.stdout)
        self.assertIn("- False positives: 0", markdown_result.stdout)
        self.assertIn("- Precision: 1.000", markdown_result.stdout)
        self.assertIn("| negative-generate-yaml | false | false | pass |", markdown_result.stdout)

    def test_external_runtime_events_require_live_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_path = Path(tmp) / "runtime-events.json"
            events_path.write_text(
                json.dumps(
                    {
                        "negative-generate-yaml": [
                            {
                                "event": "skill_invocation",
                                "skill": "analyze-repo-for-kubernetes",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            blocked = subprocess.run(
                ["python3", str(EVAL_PATH), str(CASES_PATH), "--runtime-events", str(events_path)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("--runtime-events requires --allow-live-runtime", blocked.stderr)

            allowed = subprocess.run(
                [
                    "python3",
                    str(EVAL_PATH),
                    str(CASES_PATH),
                    "--runtime-events",
                    str(events_path),
                    "--allow-live-runtime",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            payload = json.loads(allowed.stdout)
            self.assertEqual(payload["metrics"]["false_positives"], 1)
            self.assertEqual(payload["metrics"]["precision"], 6 / 7)

    def test_skill_description_declares_non_target_boundary(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        description = re.search(r"^description: (.+)$", skill, re.MULTILINE).group(1)

        for required in [
            "manifest/Helm generation or editing",
            "live-cluster troubleshooting",
            "existing-manifest-only review",
            "general Kubernetes explanations",
            "app/containerization changes",
        ]:
            self.assertIn(required, description)


if __name__ == "__main__":
    unittest.main()
