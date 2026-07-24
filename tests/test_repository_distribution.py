import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RepositoryDistributionTests(unittest.TestCase):
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
            "hooks.json",
        ]:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_shell_scripts_are_valid(self):
        for rel in ["scripts/install-qwen.sh", "scripts/update-qwen.sh", "scripts/install-codex.sh", "scripts/uninstall-codex.sh"]:
            result = subprocess.run(
                ["bash", "-n", str(ROOT / rel)],
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
            self.assertEqual(installed.resolve(), ROOT.resolve())

    def test_codex_install_registers_a_valid_managed_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            env = os.environ.copy()
            env["HOME"] = str(home)
            env.pop("CODEX_SKIP_HOOK", None)
            env.pop("CODEX_HOME", None)
            env.pop("USERPROFILE", None)
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/install-codex.sh")],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            config = (home / ".codex/config.toml").read_text(encoding="utf-8")
            self.assertIn("BEGIN analyze-repo-for-kubernetes target gate", config)
            self.assertIn("[[hooks.PreToolUse]]", config)
            self.assertIn("[[hooks.UserPromptSubmit]]", config)
            self.assertIn("timeout = 2", config)
            self.assertIn("statusMessage", config)
            self.assertIn("codex_target_gate_hook.py", config)

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

    def test_markdown_commands_do_not_use_shell_line_continuations(self):
        for path in ROOT.rglob("*.md"):
            for line in path.read_text(encoding="utf-8").splitlines():
                self.assertFalse(line.rstrip().endswith("\\"), f"{path}: {line}")


if __name__ == "__main__":
    unittest.main()
