from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repository_evidence.py"
VALIDATOR = ROOT / "scripts" / "validate_repository_evidence.py"
sys.path.insert(0, str(ROOT / "scripts"))
import repository_evidence as evidence_collector


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

    def run_collector_process(self, repository: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SCRIPT), str(repository), *extra],
            capture_output=True,
            text=True,
            check=False,
        )

    def cache_diagnostics(self, result: subprocess.CompletedProcess[str]) -> dict[str, int]:
        line = next((line for line in result.stderr.splitlines() if line.startswith("cache: ")), None)
        self.assertIsNotNone(line, result.stderr)
        return {
            key: int(value)
            for key, value in (
                part.split("=", 1) for part in line.removeprefix("cache: ").split()
            )
        }

    def run_validator(self, payload: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "repository-evidence.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return subprocess.run(
                ["python3", str(VALIDATOR), str(artifact)],
                capture_output=True,
                text=True,
                check=False,
            )

    def assert_validator_rejects(self, payload: dict, code: str) -> None:
        result = self.run_validator(payload)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail("validator did not emit machine-readable JSON: " + result.stdout + result.stderr)
        self.assertFalse(response["valid"])
        self.assertIn(code, {error["code"] for error in response["errors"]})

    def test_collector_emits_stable_schema_identity_source_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "package.json").write_text(
                '{"scripts":{"start":"node src/server.js"},"packageManager":"pnpm@9"}\n',
                encoding="utf-8",
            )
            src = repo / "src"
            src.mkdir()
            (src / "server.js").write_text(
                "const http = require('http')\n"
                "server.listen(process.env.PORT || 3000)\n",
                encoding="utf-8",
            )

            first = self.run_collector_process(repo)
            second = self.run_collector_process(repo)

        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        self.assertEqual(first.stdout, second.stdout)

        payload = json.loads(first.stdout)
        self.assertEqual(payload["schema_version"], "repository-evidence/v2")
        ids = [item["id"] for item in payload["evidence"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(any(identifier.startswith("ev-000") for identifier in ids))
        self.assertEqual({item["provenance"] for item in payload["evidence"]}, {"EXTRACTED", "INFERRED"})
        self.assertTrue(
            all(
                item["kind"].startswith("runtime_")
                for item in payload["evidence"]
                if item["provenance"] == "EXTRACTED"
            )
        )

        line_counts = {entry["path"]: entry["line_count"] for entry in payload["snapshot"]["files"]}
        positive_items = [item for item in payload["evidence"] if item["kind"] != "absence"]
        self.assertTrue(positive_items)
        for item in positive_items:
            source = item["source"]
            self.assertIn(source["path"], line_counts)
            self.assertGreaterEqual(source["start_line"], 1)
            self.assertGreaterEqual(source["end_line"], source["start_line"])
            self.assertLessEqual(source["end_line"], line_counts[source["path"]])
            self.assertEqual(item["evidence"], f"{source['path']}:{source['start_line']}")
            expected_extractor = "node_runtime_signals" if item["provenance"] == "EXTRACTED" else "repository_evidence"
            self.assertEqual(item["extractor"]["name"], expected_extractor)
            self.assertRegex(item["extractor"]["version"], r"^\d+\.\d+\.\d+$")

        absence = next(item for item in payload["evidence"] if item["kind"] == "absence")
        self.assertNotIn("source", absence)
        self.assertEqual(absence["absence"], {"scope": ".", "pattern": "Dockerfile|Containerfile", "result": "없음"})

        validation = self.run_validator(payload)
        self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)
        self.assertEqual(json.loads(validation.stdout), {"valid": True, "errors": []})

    def test_validator_rejects_malformed_repository_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "package.json").write_text('{"scripts":{"start":"node server.js"}}\n', encoding="utf-8")
            (repo / "server.js").write_text("app.listen(3000)\n", encoding="utf-8")
            payload = self.run_collector(repo)

        duplicate = json.loads(json.dumps(payload))
        duplicate["evidence"][1]["id"] = duplicate["evidence"][0]["id"]
        self.assert_validator_rejects(duplicate, "duplicate_id")

        positive_index = next(index for index, item in enumerate(payload["evidence"]) if item["kind"] != "absence")

        invalid_span = json.loads(json.dumps(payload))
        invalid_span["evidence"][positive_index]["source"]["end_line"] = 999
        self.assert_validator_rejects(invalid_span, "source_span_out_of_bounds")

        escaped_path = json.loads(json.dumps(payload))
        escaped_path["evidence"][positive_index]["source"]["path"] = "../secrets.env"
        self.assert_validator_rejects(escaped_path, "repository_root_escape")

        unknown_kind = json.loads(json.dumps(payload))
        unknown_kind["evidence"][positive_index]["kind"] = "llm_readiness_decision"
        self.assert_validator_rejects(unknown_kind, "unknown_evidence_kind")

        leaked_secret = json.loads(json.dumps(payload))
        leaked_secret["evidence"][positive_index]["data"]["snippet"] = "API_TOKEN=raw-secret-value"
        self.assert_validator_rejects(leaked_secret, "secret_value_leak")

        missing_provenance = json.loads(json.dumps(payload))
        missing_provenance["evidence"][positive_index].pop("provenance")
        self.assert_validator_rejects(missing_provenance, "invalid_provenance")

        invalid_extracted_provenance = json.loads(json.dumps(payload))
        record = invalid_extracted_provenance["evidence"][positive_index]
        record["provenance"] = "EXTRACTED"
        record["id"] = evidence_collector.stable_evidence_id(
            record["kind"],
            record["status"],
            record["data"],
            record["source"],
            provenance=record["provenance"],
        )
        self.assert_validator_rejects(invalid_extracted_provenance, "invalid_provenance")

    def test_validator_accepts_v1_payload_with_historical_identity(self):
        data = {"path": "package.json", "name": "package.json"}
        source = {"path": "package.json", "start_line": 1, "end_line": 1}
        payload = {
            "schema_version": "repository-evidence/v1",
            "snapshot": {
                "repository_root": "/tmp/repo",
                "analysis_root": "/tmp/repo",
                "subdirectory": ".",
                "revision": None,
                "files": [
                    {"path": "package.json", "size_bytes": 42, "extension": ".json", "line_count": 1},
                ],
            },
            "evidence": [
                {
                    "id": evidence_collector.stable_v1_evidence_id("manifest", "confirmed", data, source),
                    "kind": "manifest",
                    "status": "confirmed",
                    "evidence": "package.json:1",
                    "data": data,
                    "source": source,
                    "extractor": {"name": "repository_evidence", "version": "1.0.0"},
                }
            ],
        }

        result = self.run_validator(payload)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {"valid": True, "errors": []})

    def test_validator_accepts_current_legacy_evidence_shape(self):
        legacy = {
            "schema_version": 1,
            "snapshot": {
                "repository_root": "/tmp/repo",
                "analysis_root": "/tmp/repo",
                "subdirectory": ".",
                "revision": None,
                "files": [
                    {"path": "package.json", "size_bytes": 42, "extension": ".json", "line_count": 1},
                ],
            },
            "evidence": [
                {
                    "id": "ev-0001",
                    "kind": "manifest",
                    "status": "confirmed",
                    "evidence": "package.json:1",
                    "data": {"path": "package.json", "name": "package.json"},
                },
                {
                    "id": "ev-0002",
                    "kind": "absence",
                    "status": "confirmed",
                    "evidence": "검색(scope=., pattern=Dockerfile|Containerfile, result=없음)",
                    "data": {"scope": ".", "pattern": "Dockerfile|Containerfile", "result": "없음"},
                },
            ],
        }

        result = self.run_validator(legacy)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {"valid": True, "errors": []})

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

    def test_node_runtime_signals_are_extracted_from_explicit_source_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            source = repo / "src"
            source.mkdir()
            (source / "server.js").write_text(
                "const fs = require('fs')\n"
                "const { Client } = require('pg')\n"
                "const db = new Client({ connectionString: process.env.DATABASE_URL })\n"
                "server.listen(process.env.PORT || 3100, '0.0.0.0')\n"
                "fs.writeFile(process.env.DATA_PATH, 'value')\n"
                "setInterval(() => db.query('select 1'), 1000)\n"
                "// server.listen(9999)\n"
                "const example = 'fs.writeFile(\"/not-a-path\")'\n",
                encoding="utf-8",
            )
            tests = repo / "tests"
            tests.mkdir()
            (tests / "server.test.js").write_text(
                "server.listen(9876)\nfs.writeFile('/test-output', 'x')\n",
                encoding="utf-8",
            )
            (repo / "README.md").write_text("server.listen(8765)\n", encoding="utf-8")
            (repo / "package.json").write_text('{"dependencies":{"express":"*"}}\n', encoding="utf-8")

            payload = self.run_collector(repo, "--no-cache")

        expected_kinds = {
            "runtime_config_read",
            "runtime_listener",
            "runtime_outbound_connection",
            "runtime_writable_path",
            "runtime_background_registration",
        }
        runtime = [item for item in payload["evidence"] if item["kind"] in expected_kinds]
        self.assertEqual({item["kind"] for item in runtime}, expected_kinds)
        self.assertTrue(all(item["provenance"] == "EXTRACTED" for item in runtime))
        self.assertTrue(all(item["status"] == "confirmed" for item in runtime))
        self.assertTrue(all(item["data"]["language"] == "node" for item in runtime))
        self.assertTrue(all(item["source"]["path"] == "src/server.js" for item in runtime))
        listener = next(item for item in runtime if item["kind"] == "runtime_listener")
        self.assertEqual(listener["data"]["port"], 3100)
        self.assertEqual(listener["data"]["host"], "0.0.0.0")
        self.assertFalse(
            any(item["data"].get("port") in {8765, 9876, 9999} for item in runtime if item["kind"] == "runtime_listener")
        )
        writable = next(item for item in runtime if item["kind"] == "runtime_writable_path")
        self.assertEqual(writable["data"]["path_config_key"], "DATA_PATH")
        self.assertFalse(
            any(item["data"].get("path") == "/not-a-path" for item in runtime if item["kind"] == "runtime_writable_path")
        )

    def test_runtime_signals_can_be_disabled_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "server.js").write_text("server.listen(process.env.PORT || 3000)\n", encoding="utf-8")

            enabled = self.run_collector_process(repo, "--no-cache")
            disabled = self.run_collector_process(repo, "--no-cache", "--no-runtime-signals")

        self.assertEqual(enabled.returncode, 0, enabled.stderr + enabled.stdout)
        self.assertEqual(disabled.returncode, 0, disabled.stderr + disabled.stdout)
        enabled_payload = json.loads(enabled.stdout)
        disabled_payload = json.loads(disabled.stdout)
        self.assertTrue(any(item["kind"] == "runtime_listener" for item in enabled_payload["evidence"]))
        self.assertFalse(any(item["kind"].startswith("runtime_") and item["provenance"] == "EXTRACTED" for item in disabled_payload["evidence"]))
        self.assertTrue(any(item["kind"] == "runtime_entrypoint_hint" for item in disabled_payload["evidence"]))

    def test_python_runtime_signals_are_extracted_from_explicit_source_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "app.py").write_text(
                "import os\n"
                "import uvicorn\n"
                "import requests\n"
                "database_url = os.getenv('DATABASE_URL')\n"
                "requests.get(os.environ['API_URL'])\n"
                "open(os.environ['DATA_PATH'], 'w')\n"
                "scheduler.add_job(work, 'interval')\n"
                "uvicorn.run(app, host='0.0.0.0', port=8100)\n"
                "# uvicorn.run(app, port=9999)\n"
                "example = 'open(\"/not-a-path\", \"w\")'\n",
                encoding="utf-8",
            )
            payload = self.run_collector(repo, "--no-cache")

        expected_kinds = {
            "runtime_config_read", "runtime_listener", "runtime_outbound_connection",
            "runtime_writable_path", "runtime_background_registration",
        }
        runtime = [item for item in payload["evidence"] if item["kind"] in expected_kinds]
        self.assertEqual({item["kind"] for item in runtime}, expected_kinds)
        self.assertTrue(all(item["data"]["language"] == "python" for item in runtime))
        listener = next(item for item in runtime if item["kind"] == "runtime_listener")
        self.assertEqual(listener["data"], {"language": "python", "host": "0.0.0.0", "port": 8100})

    def test_per_file_cache_reuses_unchanged_evidence_and_matches_a_clean_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            cache = Path(tmp) / "cache"
            repo.mkdir()
            (repo / "package.json").write_text('{"scripts":{"start":"node src/server.js"}}\n', encoding="utf-8")
            (repo / "src").mkdir()
            (repo / "src" / "server.js").write_text("server.listen(3000)\n", encoding="utf-8")

            clean = self.run_collector_process(repo, "--no-cache", "--diagnostics")
            first = self.run_collector_process(repo, "--cache-dir", str(cache), "--diagnostics")
            second = self.run_collector_process(repo, "--cache-dir", str(cache), "--diagnostics")

        self.assertEqual(clean.returncode, 0, clean.stderr + clean.stdout)
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        self.assertEqual(clean.stdout, first.stdout)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(self.cache_diagnostics(clean), {"hit": 0, "miss": 0, "invalidated": 0, "corrupted": 0, "bypassed": 2})
        self.assertEqual(self.cache_diagnostics(first), {"hit": 0, "miss": 2, "invalidated": 0, "corrupted": 0, "bypassed": 0})
        self.assertEqual(self.cache_diagnostics(second), {"hit": 2, "miss": 0, "invalidated": 0, "corrupted": 0, "bypassed": 0})

    def test_per_file_cache_invalidates_only_changed_file_and_rule_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            cache = Path(tmp) / "cache"
            repo.mkdir()
            (repo / "package.json").write_text('{"scripts":{"start":"node src/server.js"}}\n', encoding="utf-8")
            (repo / "src").mkdir()
            server = repo / "src" / "server.js"
            server.write_text("server.listen(3000)\n", encoding="utf-8")

            initial = self.run_collector_process(repo, "--cache-dir", str(cache), "--diagnostics")
            server.write_text("server.listen(4000)\n", encoding="utf-8")
            changed = self.run_collector_process(repo, "--cache-dir", str(cache), "--diagnostics")
            changed_rules = self.run_collector_process(
                repo, "--cache-dir", str(cache), "--rule-fingerprint", "test-rules-v2", "--diagnostics"
            )

        self.assertEqual(initial.returncode, 0, initial.stderr + initial.stdout)
        self.assertEqual(changed.returncode, 0, changed.stderr + changed.stdout)
        self.assertEqual(changed_rules.returncode, 0, changed_rules.stderr + changed_rules.stdout)
        self.assertEqual(self.cache_diagnostics(changed), {"hit": 1, "miss": 1, "invalidated": 1, "corrupted": 0, "bypassed": 0})
        self.assertEqual(self.cache_diagnostics(changed_rules), {"hit": 0, "miss": 2, "invalidated": 2, "corrupted": 0, "bypassed": 0})

    def test_corrupted_cache_entry_is_rebuilt_without_storing_source_or_secret_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            cache = Path(tmp) / "cache"
            repo.mkdir()
            (repo / ".env.example").write_text("API_TOKEN=must-not-be-cached\n", encoding="utf-8")
            first = self.run_collector_process(repo, "--cache-dir", str(cache), "--diagnostics")
            entry = next(cache.glob("**/entries/*.json"))
            entry.write_text("{not-json", encoding="utf-8")
            rebuilt = self.run_collector_process(repo, "--cache-dir", str(cache), "--diagnostics")
            cached_text = "\n".join(path.read_text(encoding="utf-8") for path in cache.glob("**/*.json"))

        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr + rebuilt.stdout)
        self.assertEqual(self.cache_diagnostics(rebuilt), {"hit": 0, "miss": 1, "invalidated": 0, "corrupted": 1, "bypassed": 0})
        self.assertNotIn("must-not-be-cached", cached_text)

    def test_cached_scan_excludes_stale_evidence_after_a_rename_or_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            cache = Path(tmp) / "cache"
            repo.mkdir()
            (repo / "package.json").write_text('{"scripts":{"start":"node src/server.js"}}\n', encoding="utf-8")
            source = repo / "src"
            source.mkdir()
            server = source / "server.js"
            server.write_text("server.listen(3000)\n", encoding="utf-8")
            self.run_collector_process(repo, "--cache-dir", str(cache), "--diagnostics")

            renamed = source / "api.js"
            server.rename(renamed)
            renamed_run = self.run_collector_process(repo, "--cache-dir", str(cache), "--diagnostics")
            renamed_clean = self.run_collector_process(repo, "--no-cache")
            renamed.unlink()
            deleted_run = self.run_collector_process(repo, "--cache-dir", str(cache), "--diagnostics")
            deleted_clean = self.run_collector_process(repo, "--no-cache")

        self.assertEqual(renamed_run.returncode, 0, renamed_run.stderr + renamed_run.stdout)
        self.assertEqual(deleted_run.returncode, 0, deleted_run.stderr + deleted_run.stdout)
        self.assertEqual(renamed_run.stdout, renamed_clean.stdout)
        self.assertEqual(deleted_run.stdout, deleted_clean.stdout)
        self.assertNotIn("src/server.js", renamed_run.stdout)
        self.assertNotIn("src/api.js", deleted_run.stdout)
        self.assertEqual(self.cache_diagnostics(renamed_run), {"hit": 1, "miss": 1, "invalidated": 0, "corrupted": 0, "bypassed": 0})
        self.assertEqual(self.cache_diagnostics(deleted_run), {"hit": 1, "miss": 0, "invalidated": 0, "corrupted": 0, "bypassed": 0})

    def test_extractor_version_change_invalidates_cached_file_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            cache = Path(tmp) / "cache"
            repo.mkdir()
            (repo / "package.json").write_text('{"scripts":{"start":"node server.js"}}\n', encoding="utf-8")
            (repo / "server.js").write_text("server.listen(3000)\n", encoding="utf-8")
            first_diagnostics = evidence_collector.CacheDiagnostics()
            evidence_collector.scan_repository(repo, cache_directory=cache, cache_diagnostics=first_diagnostics)
            original_version = evidence_collector.EXTRACTOR_VERSION
            evidence_collector.EXTRACTOR_VERSION = "1.0.1"
            try:
                changed_diagnostics = evidence_collector.CacheDiagnostics()
                evidence_collector.scan_repository(repo, cache_directory=cache, cache_diagnostics=changed_diagnostics)
            finally:
                evidence_collector.EXTRACTOR_VERSION = original_version
            original_schema = evidence_collector.EVIDENCE_SCHEMA_VERSION
            evidence_collector.EVIDENCE_SCHEMA_VERSION = "repository-evidence/v2"
            try:
                schema_diagnostics = evidence_collector.CacheDiagnostics()
                evidence_collector.scan_repository(repo, cache_directory=cache, cache_diagnostics=schema_diagnostics)
            finally:
                evidence_collector.EVIDENCE_SCHEMA_VERSION = original_schema

        self.assertEqual(first_diagnostics.miss, 2)
        self.assertEqual(changed_diagnostics.hit, 0)
        self.assertEqual(changed_diagnostics.miss, 2)
        self.assertEqual(changed_diagnostics.invalidated, 2)
        self.assertEqual(schema_diagnostics.hit, 0)
        self.assertEqual(schema_diagnostics.miss, 2)
        self.assertEqual(schema_diagnostics.invalidated, 2)

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

    def test_language_and_platform_packs_collect_facts_without_component_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "pom.xml").write_text(
                "<project>\n<packaging>jar</packaging>\n<dependency>spring-boot</dependency>\n</project>\n",
                encoding="utf-8",
            )
            (repo / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
            (repo / "package.json").write_text(
                '{"packageManager":"pnpm@9","workspaces":["apps/*"],'
                '"scripts":{"start":"node src/server.js"}}\n',
                encoding="utf-8",
            )
            (repo / "yarn.lock").write_text("# lock\n", encoding="utf-8")
            (repo / "pyproject.toml").write_text("[project]\nname = 'lib'\n", encoding="utf-8")
            (repo / "go.mod").write_text("module example.com/service\ngo 1.22\n", encoding="utf-8")
            (repo / "web.csproj").write_text("<TargetFramework>net8.0</TargetFramework>\n", encoding="utf-8")
            (repo / "Gemfile").write_text("gem 'rails'\n", encoding="utf-8")
            (repo / "composer.json").write_text('{"require":{"laravel/framework":"*"}}\n', encoding="utf-8")
            (repo / "Cargo.toml").write_text("[package]\nname = 'worker'\n", encoding="utf-8")
            (repo / "Procfile").write_text("web: bundle exec puma\n", encoding="utf-8")
            (repo / "fly.toml").write_text("[http_service]\ninternal_port = 8080\n", encoding="utf-8")
            (repo / "render.yaml").write_text("services:\n  - type: web\n", encoding="utf-8")
            (repo / "railway.toml").write_text("[build]\nbuilder = 'NIXPACKS'\n", encoding="utf-8")
            (repo / "manifest.yml").write_text("applications:\n- name: cf-app\n", encoding="utf-8")
            (repo / "serverless.yml").write_text("functions:\n  api:\n", encoding="utf-8")
            (repo / "nx.json").write_text('{"extends":"nx/presets/npm.json"}\n', encoding="utf-8")
            (repo / "turbo.json").write_text('{"tasks":{"build":{}}}\n', encoding="utf-8")
            (repo / "Makefile").write_text("build:\n\tnpm run build\n", encoding="utf-8")
            (repo / "Taskfile.yml").write_text("tasks:\n  test:\n    cmds:\n      - pytest\n", encoding="utf-8")

            payload = self.run_collector(repo)

        evidence = payload["evidence"]
        languages = {item["data"].get("language") for item in evidence if item["kind"] == "language_manifest"}
        self.assertEqual(languages, {"java", "node", "python", "go", "dotnet", "ruby", "php", "rust"})
        managers = {item["data"].get("manager") for item in evidence if item["kind"] == "package_manager_hint"}
        self.assertTrue({"pnpm", "yarn"}.issubset(managers))
        platforms = {item["data"].get("platform") for item in evidence if item["kind"] == "platform_hint"}
        self.assertEqual(
            platforms,
            {"procfile", "fly", "render", "railway", "cloud_foundry", "serverless", "nx", "turbo", "make", "taskfile"},
        )
        self.assertFalse(any("deploy" in item["kind"] for item in evidence))

    def test_docker_compose_kubernetes_helm_and_kustomize_packs_collect_safe_typed_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "Dockerfile").write_text(
                "FROM python:3.12\nWORKDIR /app\nCOPY . .\nRUN docker login -u user -p short-password-secret\nUSER app\nENV API_TOKEN=secret-value\n"
                "EXPOSE 8080\nENTRYPOINT [\"python\"]\nCMD [\"app.py\", \"--token\", \"docker-secret\"]\n"
                "HEALTHCHECK CMD curl -u user:password -H \"Authorization: Bearer docker-bearer\" -H \"Authorization: Basic basic-secret-value\" http://localhost:8080/health\n",
                encoding="utf-8",
            )
            (repo / "compose.yaml").write_text(
                "services:\n  api:\n    image: example/api\n    build: .\n    command: python app.py\n"
                "    entrypoint: [python]\n    ports: [\"8080:8080\"]\n    environment:\n      API_TOKEN: compose-secret\n      - LIST_TOKEN=list-secret\n"
                "    depends_on: [db]\n    profiles: [dev]\n    volumes: [data:/data]\n    networks: [backend]\n",
                encoding="utf-8",
            )
            manifests = repo / "k8s"
            manifests.mkdir()
            (manifests / "app.yaml").write_text(
                "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\nspec:\n  template:\n"
                "    spec:\n      containers:\n        - name: api\n          image: example/api:1\n"
                "          command: [python]\n          args: [app.py, --token, kube-secret, \"Authorization: Bearer kube-bearer\"]\n          ports:\n            - containerPort: 8080\n"
                "          env:\n            - name: API_TOKEN\n              value: should-not-leak\n          livenessProbe:\n            httpGet:\n              path: /health\n"
                "          volumeMounts:\n            - name: data\n              mountPath: /data\n      volumes:\n        - name: data\n---\napiVersion: v1\nkind: Service\nmetadata:\n  name: api\nspec:\n  ports:\n    - port: 80\n      targetPort: 8080\n",
                encoding="utf-8",
            )
            chart = repo / "chart"
            (chart / "templates").mkdir(parents=True)
            (chart / "Chart.yaml").write_text("name: api\nappVersion: 1.0\n", encoding="utf-8")
            (chart / "values.yaml").write_text("image:\n  repository: example/api\n", encoding="utf-8")
            (chart / "templates" / "deployment.yaml").write_text("kind: Deployment\n", encoding="utf-8")
            overlay = repo / "overlays" / "dev"
            overlay.mkdir(parents=True)
            (overlay / "kustomization.yaml").write_text(
                "resources:\n  - ../../k8s/app.yaml\npatches:\n  - patch.yaml\nimages:\n  - name: api\n"
                "configMapGenerator:\n  - name: config\nsecretGenerator:\n  - name: secret\nnamespace: dev\ncommonLabels:\n  team: platform\n",
                encoding="utf-8",
            )

            payload = self.run_collector(repo)

        evidence = payload["evidence"]
        kinds = {item["kind"] for item in evidence}
        self.assertTrue({"docker_instruction", "docker_env_key", "compose_service", "compose_service_field"}.issubset(kinds))
        instructions = {item["data"]["instruction"] for item in evidence if item["kind"] == "docker_instruction"}
        self.assertTrue({"FROM", "WORKDIR", "COPY", "RUN", "USER", "ENV", "EXPOSE", "ENTRYPOINT", "CMD", "HEALTHCHECK"}.issubset(instructions))
        compose_env_keys = {item["data"]["key"] for item in evidence if item["kind"] == "compose_env_key"}
        self.assertTrue({"API_TOKEN", "LIST_TOKEN"}.issubset(compose_env_keys))
        kubernetes_env_keys = {item["data"]["key"] for item in evidence if item["kind"] == "kubernetes_env_key"}
        self.assertIn("API_TOKEN", kubernetes_env_keys)
        self.assertTrue({"kubernetes_resource", "kubernetes_container_field", "kubernetes_env_key", "kubernetes_probe", "kubernetes_volume", "kubernetes_service_exposure"}.issubset(kinds))
        self.assertTrue({"helm_chart", "helm_values_key", "helm_template_resource", "kustomize_composition"}.issubset(kinds))
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("compose-secret", rendered)
        self.assertNotIn("list-secret", rendered)
        self.assertNotIn("should-not-leak", rendered)
        self.assertNotIn("docker-secret", rendered)
        self.assertNotIn("kube-secret", rendered)
        self.assertNotIn("user:password", rendered)
        self.assertNotIn("docker-bearer", rendered)
        self.assertNotIn("kube-bearer", rendered)
        self.assertNotIn("short-password-secret", rendered)
        self.assertNotIn("basic-secret-value", rendered)

    def test_nested_node_manager_conflicts_are_scoped_and_platform_facts_are_typed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            app = repo / "apps" / "api"
            app.mkdir(parents=True)
            (repo / "yarn.lock").write_text("# root lock\n", encoding="utf-8")
            (app / "package.json").write_text(
                '{"packageManager":"pnpm@9","scripts":{"start":"node server.js --token script-secret -H Authorization: Bearer script-bearer"}}\n',
                encoding="utf-8",
            )
            (app / "yarn.lock").write_text("# conflicting lock\n", encoding="utf-8")
            (repo / "Procfile").write_text("web: node server.js --token procfile-secret -H Authorization: Bearer procfile-bearer\n", encoding="utf-8")
            (repo / "fly.toml").write_text("[http_service]\ninternal_port = 8080\n", encoding="utf-8")
            (repo / "settings.yaml").write_text("DATABASE_URL: postgres://user:password@db/app\n", encoding="utf-8")
            (repo / "appsettings.json").write_text('{"ConnectionStrings":{"Default":"ignored"},"Logging":{"LogLevel":"Information"}}\n', encoding="utf-8")
            (repo / "nx.json").write_text('{"extends":"nx/presets/npm.json","targetDefaults":{}}\n', encoding="utf-8")
            (repo / "turbo.json").write_text('{"tasks":{"build":{}}}\n', encoding="utf-8")

            payload = self.run_collector(repo)

        evidence = payload["evidence"]
        conflicts = [item for item in evidence if item["kind"] == "package_manager_conflict"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["data"]["scope"], "apps/api")
        process = next(item for item in evidence if item["kind"] == "platform_process")
        self.assertEqual(process["data"]["process_type"], "web")
        platform_fields = {item["data"].get("field") for item in evidence if item["kind"] == "platform_config_hint"}
        self.assertIn("internal_port", platform_fields)
        self.assertTrue({"extends", "tasks"}.issubset(platform_fields))
        config_keys = {item["data"].get("key") for item in evidence if item["kind"] == "config_key"}
        self.assertIn("DATABASE_URL", config_keys)
        self.assertTrue({"ConnectionStrings", "ConnectionStrings.Default"}.issubset(config_keys))
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("script-secret", rendered)
        self.assertNotIn("procfile-secret", rendered)
        self.assertNotIn("script-bearer", rendered)
        self.assertNotIn("procfile-bearer", rendered)
        self.assertNotIn("user:password", rendered)


if __name__ == "__main__":
    unittest.main()
