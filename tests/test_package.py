from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SkillPackageTests(unittest.TestCase):
    def test_package_validator_passes(self):
        result = subprocess.run(
            ["python3", str(ROOT / "scripts/validate_skill.py"), str(ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_target_resolution_gate_contract(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        intake = (ROOT / "references/interview-first-intake.md").read_text(encoding="utf-8")
        combined = skill + "\n" + intake
        for term in [
            "Target Resolution Gate",
            "skill installation directory is not the analysis target",
            "before any repository discovery tool call",
            "stop the turn after asking",
            "Repository URL",
            "Local path",
            "list_directory",
            "read_file",
            "tests/fixtures",
        ]:
            self.assertIn(term, combined)

    def test_output_contract(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                ROOT / "SKILL.md",
                ROOT / "assets/migration-summary-template.md",
                ROOT / "assets/migration-assessment-template.md",
            ]
        )
        for term in [
            "Execution Locus",
            "Application Phase",
            "Confirmed",
            "Inferred",
            "Unknown",
            "Conflicting",
            "Ready",
            "Needs Input",
            "Blocked",
        ]:
            self.assertIn(term, text)

    def test_report_validator_accepts_minimal_summary(self):
        report_text = """# Kubernetes Migration Summary

## 1. Scope and Verdict
- Verdict: Needs Input
- Confirmed

## 2. Architecture at a Glance

## 3. Component Summary

## 4. Critical Dependency Matrix
Execution Locus

## 5. Configuration Timing Highlights
Application Phase

## 6. Kubernetes Mapping Summary

## 7. Risks and Required Inputs

## 8. Evidence Index
"""
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "summary.md"
            report.write_text(report_text, encoding="utf-8")
            result = subprocess.run(
                ["python3", str(ROOT / "scripts/validate_report.py"), str(report), "--mode", "summary"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
