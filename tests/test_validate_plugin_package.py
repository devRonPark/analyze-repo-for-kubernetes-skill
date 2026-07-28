from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts/validate_plugin_package.py"
SKILL_REL = Path("skills/analyze-repo-for-kubernetes")


class ValidatePluginPackageTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.package = Path(self.tempdir.name) / "plugin"
        shutil.copytree(
            ROOT,
            self.package,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )

    def load_validator(self) -> types.ModuleType:
        self.assertTrue(
            VALIDATOR_PATH.is_file(),
            "scripts/validate_plugin_package.py must provide the package validator",
        )
        spec = importlib.util.spec_from_file_location(
            "validate_plugin_package", VALIDATOR_PATH
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def validate(self) -> tuple[str, ...]:
        return self.load_validator().validate_plugin_package(self.package)

    def manifest(self) -> dict:
        path = self.package / ".codex-plugin/plugin.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def write_manifest(self, manifest: dict) -> None:
        path = self.package / ".codex-plugin/plugin.json"
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def skill_path(self) -> Path:
        return self.package / SKILL_REL / "SKILL.md"

    def test_valid_copied_plugin_package_has_no_errors(self):
        self.assertEqual(self.validate(), ())

    def test_missing_mcp_config_and_server_are_rejected(self):
        (self.package / ".mcp.json").unlink()
        (self.package / "mcp/report_tool_server.py").unlink()

        errors = "\n".join(self.validate())

        self.assertIn(".mcp.json", errors)
        self.assertIn("mcp/report_tool_server.py", errors)

    def test_manifest_and_mcp_config_register_local_stdio_server(self):
        manifest = self.manifest()
        config = json.loads(
            (self.package / ".mcp.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        server = config["mcpServers"]["report-tools"]
        self.assertEqual(server["type"], "stdio")
        self.assertEqual(server["command"], "python3")
        self.assertIn("report_tool_server.py", server["args"][0])
        self.assertNotIn("url", server)

    def test_missing_manifest_is_rejected(self):
        (self.package / ".codex-plugin/plugin.json").unlink()

        self.assertIn("Plugin manifest", "\n".join(self.validate()))

    def test_manifest_requires_strict_semver_and_exact_skills_path(self):
        manifest = self.manifest()
        manifest["version"] = "v1"
        manifest["skills"] = "skills"
        self.write_manifest(manifest)

        errors = "\n".join(self.validate())
        self.assertIn("strict semver", errors)
        self.assertIn("./skills/", errors)

    def test_plugin_and_skill_names_must_match(self):
        skill = self.skill_path()
        skill.write_text(
            skill.read_text(encoding="utf-8").replace(
                "name: analyze-repo-for-kubernetes",
                "name: renamed-skill",
                1,
            ),
            encoding="utf-8",
        )

        self.assertIn("name", "\n".join(self.validate()))

    def test_root_skill_and_missing_nested_metadata_are_rejected(self):
        shutil.copy2(self.skill_path(), self.package / "SKILL.md")
        (self.package / SKILL_REL / "agents/openai.yaml").unlink()

        errors = "\n".join(self.validate())
        self.assertIn("root SKILL.md", errors)
        self.assertIn("agents/openai.yaml", errors)

    def test_broken_nested_resource_link_is_rejected(self):
        skill = self.skill_path()
        skill.write_text(
            skill.read_text(encoding="utf-8")
            + "\n[missing](references/does-not-exist.md)\n",
            encoding="utf-8",
        )

        self.assertIn("does-not-exist.md", "\n".join(self.validate()))

    def test_resource_link_cannot_escape_nested_skill_root(self):
        skill = self.skill_path()
        skill.write_text(
            skill.read_text(encoding="utf-8") + "\n[outside](../../README.md)\n",
            encoding="utf-8",
        )

        self.assertIn("escapes nested Skill root", "\n".join(self.validate()))

    def test_required_manifest_metadata_is_rejected_when_missing(self):
        manifest = self.manifest()
        del manifest["interface"]["longDescription"]
        del manifest["author"]["name"]
        self.write_manifest(manifest)

        errors = "\n".join(self.validate())
        self.assertIn("author.name", errors)
        self.assertIn("interface.longDescription", errors)

    def test_compatibility_wrapper_delegates_with_deprecation_notice(self):
        result = subprocess.run(
            [
                "python3",
                str(ROOT / "scripts/validate_skill.py"),
                str(self.package),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("deprecated", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
