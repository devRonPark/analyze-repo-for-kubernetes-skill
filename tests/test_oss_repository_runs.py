from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "oss_runtime"
SCRIPT = ROOT / "scripts" / "repository_evidence.py"
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repository_evidence


@unittest.skipUnless(
    os.environ.get("RUN_OSS_REPOSITORY_E2E") == "1",
    "set RUN_OSS_REPOSITORY_E2E=1 to clone and analyze the pinned OSS repositories",
)
class OssRepositoryRunTests(unittest.TestCase):
    def load_manifest(self) -> list[dict[str, object]]:
        raw = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(raw), {"fixtures"})
        fixtures = raw["fixtures"]
        self.assertIsInstance(fixtures, list)
        self.assertEqual(len(fixtures), 8)
        return fixtures

    def run_process(self, command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            timeout=timeout,
        )

    def clone_at_pinned_commit(self, fixture: dict[str, object], destination: Path) -> None:
        clone = self.run_process(
            ["git", "clone", "--filter=blob:none", "--no-checkout", str(fixture["upstream"]), str(destination)],
            timeout=180,
        )
        self.assertEqual(clone.returncode, 0, clone.stdout + clone.stderr)
        checkout = self.run_process(
            ["git", "-C", str(destination), "checkout", "--detach", str(fixture["commit"])],
            timeout=90,
        )
        self.assertEqual(checkout.returncode, 0, checkout.stdout + checkout.stderr)

    def collect_evidence(self, repository: Path) -> dict[str, object]:
        result = self.run_process(["python3", str(SCRIPT), str(repository), "--no-cache"], timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_each_pinned_oss_repository_completes_with_valid_evidence(self):
        with tempfile.TemporaryDirectory(prefix="oss-repository-run-") as temporary_directory:
            root = Path(temporary_directory)
            for fixture in self.load_manifest():
                with self.subTest(fixture=fixture["id"]):
                    repository = root / str(fixture["id"])
                    self.clone_at_pinned_commit(fixture, repository)
                    payload = self.collect_evidence(repository)

                    self.assertEqual(validate_repository_evidence.validate_payload(payload), [])
                    self.assertEqual(payload["snapshot"]["revision"], fixture["commit"])
                    snapshot_paths = {record["path"] for record in payload["snapshot"]["files"]}
                    self.assertIn(fixture["upstream_path"], snapshot_paths)

                    extracted = [record for record in payload["evidence"] if record["provenance"] == "EXTRACTED"]
                    extracted_kinds = {record["kind"] for record in extracted}
                    self.assertTrue(
                        all(kind in extracted_kinds for kind in fixture["expected_runtime_kinds"]),
                        extracted,
                    )
                    for kind in fixture["expected_runtime_kinds"]:
                        self.assertTrue(
                            any(
                                record["kind"] == kind
                                and record["source"]["path"] == fixture["upstream_path"]
                                for record in extracted
                            ),
                            extracted,
                        )


if __name__ == "__main__":
    unittest.main()
