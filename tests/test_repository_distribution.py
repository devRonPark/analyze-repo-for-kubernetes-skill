import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RepositoryDistributionTests(unittest.TestCase):
    def write_executable(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)

    def test_public_repository_files_exist(self):
        for rel in [
            "LICENSE",
            "CHANGELOG.md",
            ".gitignore",
            ".github/workflows/test.yml",
            "scripts/install-qwen.sh",
            "scripts/update-qwen.sh",
            "scripts/uninstall-codex.sh",
            "scripts/codex_target_gate_hook.py",
            "scripts/compact_repository_evidence.py",
            "scripts/prepare_analysis_target.py",
            "scripts/run_codex_benchmark.py",
            "hooks.json",
        ]:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_plugin_distribution_docs_and_ci_contract(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/test.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Codex Plugin", readme)
        self.assertIn("skills/analyze-repo-for-kubernetes", readme)
        self.assertIn("Qwen compatibility", readme)
        self.assertIn("local marketplace", readme)
        self.assertIn("Tool Orchestration", readme)
        self.assertIn("Plugin root", agents)
        self.assertIn("skills/analyze-repo-for-kubernetes/SKILL.md", agents)
        self.assertIn("scripts/validate_plugin_package.py", workflow)
        self.assertNotIn("scripts/validate_skill.py", workflow)

    def test_repository_regression_entrypoint_validates_plugin_package(self):
        result = subprocess.run(
            ["python3", str(ROOT / "scripts/validate_regression.py"), str(ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "plugin"
            shutil.copytree(
                ROOT,
                package,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            (package / ".codex-plugin/plugin.json").unlink()
            invalid = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/validate_regression.py"),
                    str(package),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("Plugin manifest", invalid.stdout + invalid.stderr)

    def test_shell_scripts_are_valid(self):
        for rel in ["scripts/install-qwen.sh", "scripts/update-qwen.sh", "scripts/install-codex.sh", "scripts/uninstall-codex.sh"]:
            result = subprocess.run(
                ["bash", "-n", str(ROOT / rel)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_demo_git_credential_helper_is_syntax_valid(self):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(ROOT / "scripts/demo_git_readonly_clone.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_source_intake_helper_is_syntax_valid(self):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(ROOT / "scripts/source_intake.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_plain_remote_clone_helper_is_syntax_valid(self):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(ROOT / "scripts/plain_remote_git_clone.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_remote_git_auth_helper_is_syntax_valid(self):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(ROOT / "scripts/remote_git_auth.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_source_archive_helper_is_syntax_valid(self):
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(ROOT / "scripts/source_archive.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_bottleneck_helpers_are_syntax_valid(self):
        for rel in [
            "scripts/compact_repository_evidence.py",
            "scripts/prepare_analysis_target.py",
            "scripts/run_codex_benchmark.py",
        ]:
            result = subprocess.run(
                ["python3", "-m", "py_compile", str(ROOT / rel)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_install_script_creates_qwen_skill_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/install-qwen.sh")],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": "/usr/bin:/bin", "CODEX_SKIP_HOOK": "1"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            installed = home / ".qwen/skills/analyze-repo-for-kubernetes"
            self.assertTrue(installed.is_symlink())
            self.assertEqual(
                installed.resolve(),
                (ROOT / "skills/analyze-repo-for-kubernetes").resolve(),
            )
            self.assertNotIn("deprecated", result.stderr.lower())

    def test_update_script_preserves_nested_qwen_skill_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            plugin = temp_root / "plugin"
            shutil.copytree(
                ROOT,
                plugin,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            (plugin / ".git").mkdir()
            home = temp_root / "home"
            home.mkdir()
            fake_bin = temp_root / "bin"
            fake_bin.mkdir()
            command_log = temp_root / "commands.log"
            self.write_executable(
                fake_bin / "git",
                "#!/usr/bin/env bash\nexit 0\n",
            )
            self.write_executable(
                fake_bin / "python3",
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$COMMAND_LOG"\n'
                "exit 0\n",
            )
            env = {
                "HOME": str(home),
                "PATH": f"{fake_bin}:/usr/bin:/bin",
                "COMMAND_LOG": str(command_log),
            }
            result = subprocess.run(
                ["bash", str(plugin / "scripts/update-qwen.sh")],
                cwd=plugin,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            installed = home / ".qwen/skills/analyze-repo-for-kubernetes"
            self.assertTrue(installed.is_symlink())
            self.assertEqual(
                installed.resolve(),
                (plugin / "skills/analyze-repo-for-kubernetes").resolve(),
            )
            commands = command_log.read_text(encoding="utf-8")
            self.assertIn(
                f"{plugin}/scripts/validate_plugin_package.py {plugin}",
                commands,
            )

    def test_codex_install_only_prints_plugin_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/install-codex.sh")],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((home / ".agents").exists())
            self.assertFalse((home / ".codex").exists())
            self.assertIn("Codex Plugin", result.stdout)
            self.assertIn("local marketplace", result.stdout)
            self.assertIn("변경하지 않았습니다", result.stdout)

    def test_hook_manifest_has_codex_event_shape(self):
        manifest = json.loads((ROOT / "hooks.json").read_text(encoding="utf-8"))
        hooks = manifest["hooks"]
        self.assertIn("PreToolUse", hooks)
        self.assertIn("UserPromptSubmit", hooks)
        handler = hooks["PreToolUse"][0]["hooks"][0]
        self.assertEqual(handler["type"], "command")
        self.assertEqual(handler["timeout"], 2)

    def test_codex_uninstall_removes_only_managed_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            config_dir = home / ".codex"
            config_dir.mkdir(parents=True)
            config = config_dir / "config.toml"
            config.write_text(
                "model = \"gpt-5.5\"\n"
                "# BEGIN analyze-repo-for-kubernetes target gate\n"
                "[[hooks.PreToolUse]]\n"
                "matcher = \".*\"\n"
                "# END analyze-repo-for-kubernetes target gate\n"
                "[tui]\n",
                encoding="utf-8",
            )
            installed = home / ".agents/skills/analyze-repo-for-kubernetes"
            installed.mkdir(parents=True)
            sibling = home / ".agents/skills/another-skill"
            sibling.mkdir()
            cache_marker = (
                home / ".cache/analyze-repo-for-kubernetes/preserve-me.txt"
            )
            cache_marker.parent.mkdir(parents=True)
            cache_marker.write_text("user-owned", encoding="utf-8")
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/uninstall-codex.sh")],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": os.environ["PATH"]},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            remaining = config.read_text(encoding="utf-8")
            self.assertIn("model", remaining)
            self.assertIn("[tui]", remaining)
            self.assertNotIn("analyze-repo-for-kubernetes target gate", remaining)
            self.assertFalse(installed.exists())
            self.assertTrue(sibling.is_dir())
            self.assertTrue(cache_marker.is_file())
            self.assertEqual(
                cache_marker.read_text(encoding="utf-8"),
                "user-owned",
            )

    def test_markdown_commands_do_not_use_shell_line_continuations(self):
        for path in ROOT.rglob("*.md"):
            for line in path.read_text(encoding="utf-8").splitlines():
                self.assertFalse(line.rstrip().endswith("\\"), f"{path}: {line}")


if __name__ == "__main__":
    unittest.main()
