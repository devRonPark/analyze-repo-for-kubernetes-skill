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
        ]:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_shell_scripts_are_valid(self):
        for rel in ["scripts/install-qwen.sh", "scripts/update-qwen.sh", "scripts/install-codex.sh"]:
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

    def test_install_script_creates_qwen_skill_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/install-qwen.sh")],
                cwd=ROOT,
                env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            installed = home / ".qwen/skills/analyze-repo-for-kubernetes"
            self.assertTrue(installed.is_symlink())
            self.assertEqual(installed.resolve(), ROOT.resolve())

    def test_markdown_commands_do_not_use_shell_line_continuations(self):
        for path in ROOT.rglob("*.md"):
            for line in path.read_text(encoding="utf-8").splitlines():
                self.assertFalse(line.rstrip().endswith("\\"), f"{path}: {line}")


if __name__ == "__main__":
    unittest.main()
