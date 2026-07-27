from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "research" / "navigation-corpus"
sys.path.insert(0, str(ROOT / "scripts"))
import validate_navigation_corpus


class NavigationCorpusTests(unittest.TestCase):
    def load_manifest(self) -> dict[str, object]:
        return json.loads((CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"))

    def test_manifest_has_ten_repositories_per_language(self):
        manifest = self.load_manifest()
        repositories = manifest["repositories"]
        self.assertEqual(len(repositories), 40)
        self.assertEqual(
            Counter(item["language"] for item in repositories),
            {"node": 10, "java": 10, "python": 10, "go": 10},
        )
        self.assertEqual(len({item["id"] for item in repositories}), 40)
        self.assertEqual(len({item["repository"] for item in repositories}), 40)

    def test_pinned_repositories_have_valid_observations(self):
        manifest = self.load_manifest()
        pinned = [item for item in manifest["repositories"] if item["revision_status"] == "pinned"]
        self.assertGreaterEqual(len(pinned), 1)
        for item in pinned:
            with self.subTest(corpus_id=item["id"]):
                self.assertRegex(item["revision"], r"^[0-9a-f]{40}$")
                observation_path = ROOT / item["observation"]
                self.assertTrue(observation_path.is_file())
                observation = json.loads(observation_path.read_text(encoding="utf-8"))
                self.assertEqual(validate_navigation_corpus.validate_observation(observation, item), [])

    def test_full_corpus_validator_accepts_checked_in_data(self):
        self.assertEqual(validate_navigation_corpus.validate_corpus(CORPUS_ROOT), [])

    def test_observation_rejects_non_contiguous_navigation_order(self):
        manifest = self.load_manifest()
        item = next(entry for entry in manifest["repositories"] if entry["id"] == "node-nest")
        observation = json.loads((ROOT / item["observation"]).read_text(encoding="utf-8"))
        observation["navigation_steps"][1]["order"] = 5
        errors = validate_navigation_corpus.validate_observation(observation, item)
        self.assertIn("navigation_steps order must be contiguous and start at 1", errors)


if __name__ == "__main__":
    unittest.main()
