from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repository_evidence.py"


class RepositoryEvidenceTests(unittest.TestCase):
    def run_collector(self, repository: Path, *extra: str) -> dict:
        result = subprocess.run(
            ["python3", str(SCRIPT), str(repository), *extra],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_snapshot_to_evidence_json_excludes_noise_and_records_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "package.json").write_text(
                '{"scripts":{"start":"node src/server.js"}}\n',
                encoding="utf-8",
            )
            src = repo / "src"
            src.mkdir()
            (src / "server.js").write_text(
                "const express = require('express')\n"
                "app.listen(process.env.PORT || 3000)\n",
                encoding="utf-8",
            )
            (repo / "node_modules").mkdir()
            (repo / "node_modules" / "ignored.js").write_text("ignored\n", encoding="utf-8")
            (repo / "vendor").mkdir()
            (repo / "vendor" / "ignored.py").write_text("ignored\n", encoding="utf-8")
            (repo / "logo.png").write_bytes(b"\x89PNG\x00binary")

            payload = self.run_collector(repo)

        files = {entry["path"] for entry in payload["snapshot"]["files"]}
        self.assertIn("package.json", files)
        self.assertIn("src/server.js", files)
        self.assertNotIn("node_modules/ignored.js", files)
        self.assertNotIn("vendor/ignored.py", files)
        self.assertNotIn("logo.png", files)

        evidence = payload["evidence"]
        self.assertTrue(
            any(item["kind"] == "manifest" and item["evidence"] == "package.json:1" for item in evidence)
        )
        self.assertTrue(
            any(item["kind"] == "runtime_entrypoint_hint" and item["evidence"] == "src/server.js:2" for item in evidence)
        )
        self.assertTrue(
            any(
                item["kind"] == "absence"
                and item["evidence"] == "검색(scope=., pattern=Dockerfile|Containerfile, result=없음)"
                for item in evidence
            )
        )

    def test_secret_values_are_redacted_before_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / ".env.example").write_text(
                "DATABASE_URL=postgres://localhost/app\n"
                "API_TOKEN=do-not-leak-this-token\n",
                encoding="utf-8",
            )

            payload = self.run_collector(repo)

        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertIn("API_TOKEN", rendered)
        self.assertIn("[REDACTED]", rendered)
        self.assertNotIn("do-not-leak-this-token", rendered)

    def test_subdirectory_must_stay_inside_repository_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()

            result = subprocess.run(
                ["python3", str(SCRIPT), str(repo), "--subdirectory", "../outside"],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("analysis root must stay inside repository root", result.stderr)


if __name__ == "__main__":
    unittest.main()
