from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / "scripts" / "run_repository_e2e_eval.py"
SOURCE_REPOSITORY = ROOT / "tests" / "fixtures" / "black_box_repo"
SOURCE_REPORT = ROOT / "tests" / "fixtures" / "regression" / "black_box_report.md"


class RepositoryE2EEvalTests(unittest.TestCase):
    def run_process(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def create_corpus(self, root: Path) -> tuple[Path, Path, Path]:
        repository = root / "source"
        shutil.copytree(SOURCE_REPOSITORY, repository)
        for command in [
            ["git", "init", str(repository)],
            ["git", "-C", str(repository), "add", "."],
            [
                "git", "-C", str(repository), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                "commit", "-m", "fixture",
            ],
        ]:
            result = self.run_process(command)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        revision = self.run_process(["git", "-C", str(repository), "rev-parse", "HEAD"])
        self.assertEqual(revision.returncode, 0, revision.stdout + revision.stderr)

        manifest = root / "corpus.json"
        manifest.write_text(
            json.dumps(
                {
                    "fixtures": [
                        {
                            "id": "node-api",
                            "upstream": repository.as_uri(),
                            "commit": revision.stdout.strip(),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        reports = root / "reports"
        reports.mkdir()
        shutil.copyfile(SOURCE_REPORT, reports / "node-api.md")
        return manifest, reports, repository

    def test_evaluates_pinned_repository_report_from_report_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest, reports, _repository = self.create_corpus(root)
            output = root / "result.json"

            result = self.run_process(
                [
                    "python3", str(EVALUATOR), "--manifest", str(manifest), "--report-dir", str(reports),
                    "--allow-network", "--output", str(output),
                ]
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(payload["summary"]["passed"])
        self.assertEqual(payload["summary"]["total"], 1)
        evaluation = payload["repositories"][0]
        self.assertEqual(evaluation["id"], "node-api")
        self.assertTrue(evaluation["checkout"]["passed"])
        self.assertTrue(evaluation["report_validation"]["passed"])
        self.assertFalse(evaluation["comparison"]["performed"])
        self.assertEqual(evaluation["normalized_actual"]["workload_candidates"], ["api"])

    def test_reports_expected_field_difference(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest, reports, _repository = self.create_corpus(root)
            expectations = root / "expectations.json"
            expectations.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "comparison_fields": ["design_input_verdict"],
                        "repositories": {"node-api": {"design_input_verdict": "설계 입력 충분"}},
                    }
                ),
                encoding="utf-8",
            )
            output = root / "result.json"

            result = self.run_process(
                [
                    "python3", str(EVALUATOR), "--manifest", str(manifest), "--report-dir", str(reports),
                    "--expectations", str(expectations), "--allow-network", "--output", str(output),
                ]
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(payload["summary"]["passed"])
        self.assertFalse(payload["repositories"][0]["comparison"]["passed"])
        self.assertIn("design_input_verdict", payload["repositories"][0]["comparison"]["differences"][0])

    def test_requires_explicit_network_permission(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest, reports, _repository = self.create_corpus(root)

            result = self.run_process(
                ["python3", str(EVALUATOR), "--manifest", str(manifest), "--report-dir", str(reports)]
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--allow-network", result.stderr)

    def test_runs_live_command_only_with_explicit_permission(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest, _reports, _repository = self.create_corpus(root)
            output = root / "result.json"
            command = (
                "python3 -c \"from pathlib import Path; "
                f"print(Path({str(SOURCE_REPORT)!r}).read_text(encoding='utf-8'), end='')\""
            )

            blocked = self.run_process(
                [
                    "python3", str(EVALUATOR), "--manifest", str(manifest), "--live-command", command,
                    "--allow-network",
                ]
            )
            allowed = self.run_process(
                [
                    "python3", str(EVALUATOR), "--manifest", str(manifest), "--live-command", command,
                    "--allow-network", "--allow-live-runtime", "--output", str(output),
                ]
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("--allow-live-runtime", blocked.stderr)
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        self.assertEqual(payload["repositories"][0]["report_source"], "live-command")

    def test_rejects_live_command_that_modifies_checkout(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest, _reports, _repository = self.create_corpus(root)
            output = root / "result.json"
            command = (
                "python3 -c \"from pathlib import Path; Path('unexpected.txt').write_text('x'); "
                f"print(Path({str(SOURCE_REPORT)!r}).read_text(encoding='utf-8'), end='')\""
            )

            result = self.run_process(
                [
                    "python3", str(EVALUATOR), "--manifest", str(manifest), "--live-command", command,
                    "--allow-network", "--allow-live-runtime", "--output", str(output),
                ]
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(payload["repositories"][0]["report_validation"]["passed"])
        self.assertIn("checkout을 변경", payload["repositories"][0]["report_validation"]["errors"][0])


if __name__ == "__main__":
    unittest.main()
