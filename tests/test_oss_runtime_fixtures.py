from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "oss_runtime"
SCRIPT = ROOT / "scripts" / "repository_evidence.py"
sys.path.insert(0, str(ROOT / "scripts"))
import repository_evidence
import validate_repository_evidence


class OssRuntimeFixtureTests(unittest.TestCase):
    def run_collector(self, repository: Path) -> dict[str, object]:
        result = subprocess.run(
            ["python3", str(SCRIPT), str(repository), "--no-cache"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def load_manifest(self) -> list[dict[str, object]]:
        raw = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(raw), {"fixtures"})
        self.assertIsInstance(raw["fixtures"], list)
        return raw["fixtures"]

    def test_manifest_describes_exactly_two_fixtures_per_language(self):
        fixtures = self.load_manifest()
        self.assertEqual(len(fixtures), 8)
        self.assertEqual(
            Counter(item["language"] for item in fixtures),
            {"node": 2, "python": 2, "java": 2, "go": 2},
        )
        self.assertEqual(len({item["id"] for item in fixtures}), 8)
        for item in fixtures:
            self.assertRegex(item["commit"], r"^[0-9a-f]{40}$")
            self.assertTrue((FIXTURE_ROOT / item["fixture_path"] / item["source_path"]).is_file())
            self.assertTrue(item["upstream"].startswith("https://github.com/"))
            self.assertTrue(item["license"])
            self.assertEqual(len(item["upstream_lines"]), 2)

    def test_each_real_oss_fixture_completes_with_valid_evidence(self):
        for fixture in self.load_manifest():
            with self.subTest(fixture=fixture["id"]):
                payload = self.run_collector(FIXTURE_ROOT / fixture["fixture_path"])
                self.assertEqual(validate_repository_evidence.validate_payload(payload), [])
                languages = {record["language"] for record in payload["snapshot"]["files"]}
                self.assertIn(fixture["language"], languages)
                runtime = [record for record in payload["evidence"] if record["provenance"] == "EXTRACTED"]
                self.assertTrue(all(record["source"]["path"] == fixture["source_path"] for record in runtime))
                self.assertTrue(all(".." not in record["source"]["path"].split("/") for record in runtime))
                self.assertTrue(all(kind in {record["kind"] for record in runtime} for kind in fixture["expected_runtime_kinds"]))
                serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                self.assertEqual(serialized, repository_evidence.redact_sensitive_text(serialized))


if __name__ == "__main__":
    unittest.main()
