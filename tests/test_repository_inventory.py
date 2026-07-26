from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SCRIPT = ROOT / "scripts" / "repository_evidence.py"
INVENTORY_SCRIPT = ROOT / "scripts" / "repository_inventory.py"
EVIDENCE_VALIDATOR = ROOT / "scripts" / "validate_repository_evidence.py"


class RepositoryInventoryTests(unittest.TestCase):
    def create_inventory_fixture(self, root: Path) -> None:
        (root / "package.json").write_text(
            '{"scripts":{"start":"node src/server.js"},"packageManager":"pnpm@9"}\n',
            encoding="utf-8",
        )
        src = root / "src"
        src.mkdir()
        (src / "server.js").write_text(
            "const http = require('http')\n"
            "server.listen(process.env.PORT || 3000)\n",
            encoding="utf-8",
        )
        (src / "notes.tmp").write_text("safe but not a scanner input\n", encoding="utf-8")
        (root / ".env").write_text("API_TOKEN=do-not-read-this-secret\n", encoding="utf-8")
        (root / "logo.png").write_bytes(b"\x89PNG\x00binary")
        (root / "bundle.min.js").write_text("app.listen(9999)\n", encoding="utf-8")
        (root / "node_modules" / "pkg").mkdir(parents=True)
        (root / "node_modules" / "pkg" / "index.js").write_text("app.listen(1111)\n", encoding="utf-8")
        (root / "vendor").mkdir()
        (root / "vendor" / "helper.py").write_text("print('vendored')\n", encoding="utf-8")
        (root / ".git").mkdir()
        (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
        logs = root / "logs"
        logs.mkdir()
        (logs / "large.txt").write_text("x" * 1_048_577, encoding="utf-8")

        outside = root.parent / "outside-secret.js"
        outside.write_text("server.listen(4545)\n", encoding="utf-8")
        (root / "linked-outside.js").symlink_to(outside)

    def run_inventory(self, repository: Path) -> dict:
        result = subprocess.run(
            ["python3", str(INVENTORY_SCRIPT), str(repository)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_inventory_classifies_every_discovered_path_with_stable_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            self.create_inventory_fixture(repo)

            first = self.run_inventory(repo)
            second = self.run_inventory(repo)

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], "repository-inventory/v1")
        self.assertEqual(first["summary"]["total_paths"], len(first["paths"]))
        self.assertEqual(sum(first["summary"]["by_disposition"].values()), first["summary"]["total_paths"])
        self.assertTrue(first["summary"]["reconciled"])

        by_path = {entry["path"]: entry for entry in first["paths"]}
        for entry in first["paths"]:
            self.assertEqual(PurePosixPath(entry["path"]).as_posix(), entry["path"])
            self.assertFalse(PurePosixPath(entry["path"]).is_absolute())
            self.assertNotIn("..", PurePosixPath(entry["path"]).parts)
            self.assertIn("disposition", entry)
            self.assertIn("reason", entry)
            self.assertIsInstance(entry["reason"], str)
            self.assertTrue(entry["reason"])

        expected_dispositions = {
            "package.json": "included",
            "src/server.js": "included",
            "src/notes.tmp": "unclassified",
            ".env": "sensitive",
            "logo.png": "binary",
            "bundle.min.js": "generated",
            "node_modules": "dependency_cache",
            "vendor": "vendored",
            ".git": "ignored",
            "logs/large.txt": "too_large",
            "linked-outside.js": "symlink",
        }
        for path, disposition in expected_dispositions.items():
            self.assertEqual(by_path[path]["disposition"], disposition, path)

        self.assertIn("content_sha256", by_path["src/server.js"])
        self.assertNotIn("content_sha256", by_path[".env"])
        self.assertNotIn("content_sha256", by_path["linked-outside.js"])
        self.assertEqual(by_path["package.json"]["language"], "node")
        self.assertTrue(by_path[".env"]["is_config"])

    def test_evidence_cli_writes_inventory_and_keeps_skipped_paths_out_of_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            self.create_inventory_fixture(repo)
            inventory_output = Path(tmp) / "inventory.json"

            result = subprocess.run(
                [
                    "python3",
                    str(EVIDENCE_SCRIPT),
                    str(repo),
                    "--inventory-output",
                    str(inventory_output),
                    "--diagnostics",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            evidence_payload = json.loads(result.stdout)
            inventory_payload = json.loads(inventory_output.read_text(encoding="utf-8"))

            validation_file = Path(tmp) / "evidence.json"
            validation_file.write_text(json.dumps(evidence_payload, ensure_ascii=False), encoding="utf-8")
            validation = subprocess.run(
                ["python3", str(EVIDENCE_VALIDATOR), str(validation_file)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)

        snapshot_files = {entry["path"] for entry in evidence_payload["snapshot"]["files"]}
        self.assertEqual(snapshot_files, {"package.json", "src/server.js"})
        rendered_evidence = json.dumps(evidence_payload, ensure_ascii=False)
        self.assertNotIn("do-not-read-this-secret", rendered_evidence)
        self.assertNotIn("4545", rendered_evidence)
        self.assertNotIn("9999", rendered_evidence)
        self.assertIn("inventory:", result.stderr)
        self.assertEqual(inventory_payload["summary"]["by_disposition"]["included"], 2)


if __name__ == "__main__":
    unittest.main()
