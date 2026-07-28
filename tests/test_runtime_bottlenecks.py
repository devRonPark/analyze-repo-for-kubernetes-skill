from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "analyze-repo-for-kubernetes"
PREPARE = ROOT / "scripts" / "prepare_analysis_target.py"
BENCHMARK = ROOT / "scripts" / "run_codex_benchmark.py"
COMPACTOR = ROOT / "scripts" / "compact_repository_evidence.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RuntimeBottleneckTests(unittest.TestCase):
    def create_repository(self, root: Path) -> Path:
        repository = root / "repository"
        repository.mkdir()
        (repository / "Dockerfile").write_text(
            "FROM python:3.12-slim\nEXPOSE 8000\nCMD [\"python\", \"app.py\"]\n",
            encoding="utf-8",
        )
        (repository / "app.py").write_text("print('ready')\n", encoding="utf-8")
        for command in [
            ["git", "init", str(repository)],
            ["git", "-C", str(repository), "add", "."],
            [
                "git",
                "-C",
                str(repository),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.test",
                "commit",
                "-m",
                "fixture",
            ],
        ]:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return repository

    def run_prepare(self, repository: Path, workspace: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(PREPARE),
                "--local-checkout",
                str(repository),
                "--workspace",
                str(workspace),
                "--mode",
                "detailed",
                *extra,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_skill_routes_remote_git_through_one_preparation_command(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        body = skill.split("---", 2)[2]
        detailed_template = (SKILL_ROOT / "assets" / "migration-assessment-template.md").read_text(
            encoding="utf-8"
        )
        summary_template = (SKILL_ROOT / "assets" / "migration-summary-template.md").read_text(
            encoding="utf-8"
        )

        self.assertLessEqual(len(body.splitlines()), 90)
        self.assertIn("scripts/prepare_analysis_target.py", skill)
        self.assertIn("before any repository web or search tool", skill)
        self.assertIn("Do not use web search after preparation succeeds", skill)
        self.assertIn("evidence-digest.json", skill)
        self.assertIn("Use `focus_files`", skill)
        self.assertIn("Do not run `rg --files` or broad recursive searches", skill)
        self.assertIn("at most 20 targeted repository files", skill)
        self.assertIn("Read each targeted file once with line numbers", skill)
        self.assertIn("Never use Markdown links or absolute paths for evidence", skill)
        self.assertIn("Read exactly one selected report template", skill)
        self.assertIn(
            "Do not read `<plugin-root>/scripts/validate_report.py`",
            skill,
        )
        self.assertIn("A verdict-only response is invalid", skill)
        for template in (summary_template, detailed_template):
            self.assertIn("모든 `- 키: 값` bullet", template)
            self.assertIn(
                "— 상태: 추정됨 / 근거: <file:line 또는 검색(...)> / 판단: <추론 이유>",
                template,
            )
            self.assertIn("bare `- 키: 값`", template)
            self.assertIn("Never use Markdown links or absolute paths", template)
            card = template.split("### 배포 대상: <이름>", 1)[1].split("## 4.", 1)[0]
            for line in card.splitlines():
                if line.startswith("- "):
                    self.assertIn(" — 상태:", line)
                    self.assertIn(" / 근거: <file:line 또는 검색(...)>", line)

    def test_prepare_local_checkout_creates_evidence_and_only_selected_template(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository = self.create_repository(root)
            workspace = root / "analysis"

            result = self.run_prepare(repository, workspace)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            target = json.loads((workspace / "target.json").read_text(encoding="utf-8"))
            evidence = Path(payload["artifacts"]["evidence"])
            evidence_digest = Path(payload["artifacts"]["evidence_digest"])
            report = Path(payload["artifacts"]["report"])
            self.assertEqual(payload["state"], "prepared")
            self.assertEqual(target["mode"], "detailed")
            self.assertTrue(evidence.is_file())
            self.assertTrue(evidence_digest.is_file())
            self.assertTrue(report.is_file())
            self.assertLess(evidence_digest.stat().st_size, evidence.stat().st_size)
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("# Kubernetes 설계 입력 상세 평가", report_text)
            self.assertNotIn("# Kubernetes 설계 입력 요약", report_text)
            self.assertNotIn("migration-summary-template.md", json.dumps(payload, ensure_ascii=False))
            self.assertEqual(
                target["validation"]["command"],
                [
                    "python3",
                    str(ROOT / "scripts" / "validate_report.py"),
                    str(report),
                    "--mode",
                    "detailed",
                    "--repo-root",
                    str(repository.resolve()),
                ],
            )

    def test_prepare_resume_reuses_checkpoint_without_rescanning(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository = self.create_repository(root)
            workspace = root / "analysis"

            first = self.run_prepare(repository, workspace)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            evidence = workspace / "evidence.json"
            first_mtime = evidence.stat().st_mtime_ns

            resumed = self.run_prepare(repository, workspace, "--resume")

            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            self.assertTrue(json.loads(resumed.stdout)["reused"])
            self.assertEqual(evidence.stat().st_mtime_ns, first_mtime)

    def test_compact_evidence_omits_lock_rows_and_generic_config_noise(self):
        compactor = load_module("compact_repository_evidence", COMPACTOR)
        noisy = [
            {
                "kind": "python_dependency_or_lock",
                "evidence": f"uv.lock:{line}",
                "status": "confirmed",
                "data": {"path": "uv.lock", "line": line},
            }
            for line in range(1, 1501)
        ]
        noisy.extend(
            {
                "kind": "config_key",
                "evidence": f".github/workflows/ci.yml:{line}",
                "status": "confirmed",
                "data": {"path": ".github/workflows/ci.yml", "key": f"key-{line}"},
            }
            for line in range(1, 934)
        )
        important = {
            "kind": "runtime_listener",
            "evidence": "app.py:10",
            "status": "confirmed",
            "data": {"path": "app.py", "port": 8000},
        }
        misleading_lock_manifest = {
            "kind": "language_manifest",
            "evidence": "uv.lock:1",
            "status": "confirmed",
            "data": {"path": "uv.lock"},
        }
        misleading_test_signal = {
            "kind": "runtime_listener",
            "evidence": "tests/e2e/test_app.py:20",
            "status": "confirmed",
            "data": {"path": "tests/e2e/test_app.py", "port": 9000},
        }
        misleading_ide_signal = {
            "kind": "runtime_entrypoint_hint",
            "evidence": ".vscode/launch.json:4",
            "status": "confirmed",
            "data": {"path": ".vscode/launch.json"},
        }
        payload = {
            "schema_version": "repository-evidence/v2",
            "snapshot": {
                "repository_root": "/tmp/repo",
                "analysis_root": "/tmp/repo",
                "subdirectory": ".",
                "revision": "a" * 40,
                "files": [
                    {
                        "path": "app.py",
                        "language": "python",
                        "line_count": 10,
                        "content_sha256": "secretly-unneeded",
                    }
                ],
            },
            "evidence": [
                *noisy,
                important,
                misleading_lock_manifest,
                misleading_test_signal,
                misleading_ide_signal,
            ],
            "diagnostics": {"runtime_extraction": []},
        }

        digest = compactor.compact_evidence(payload)
        rendered = json.dumps(digest, ensure_ascii=False)

        self.assertEqual(digest["summary"]["input_evidence"], 2437)
        self.assertEqual(digest["summary"]["selected_evidence"], 4)
        self.assertEqual(
            digest["summary"]["omitted_by_kind"],
            {"config_key": 933, "python_dependency_or_lock": 1500},
        )
        self.assertEqual(
            digest["evidence"],
            [misleading_ide_signal, important, misleading_test_signal, misleading_lock_manifest],
        )
        self.assertEqual(digest["focus_files"], ["app.py"])
        self.assertNotIn("content_sha256", rendered)
        self.assertLess(len(rendered.encode("utf-8")), 16_000)

    def test_prepare_rejects_subdirectory_escape(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            repository = self.create_repository(root)

            result = self.run_prepare(repository, root / "analysis", "--subdirectory", "../outside")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("subdirectory", result.stderr)

    def test_benchmark_summary_classifies_known_runtime_bottlenecks(self):
        benchmark = load_module("run_codex_benchmark", BENCHMARK)
        events = [
            {"type": "item.completed", "item": {"type": "web_search", "query": "one"}},
            {"type": "item.completed", "item": {"type": "web_search", "query": "two"}},
            {"type": "item.completed", "item": {"type": "command_execution", "command": "git clone"}},
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500},
            },
        ]
        stderr = "\n".join(
            [
                "failed to load models cache: missing field supports_reasoning_summaries",
                "failed to refresh remote installed plugins cache",
                "stream disconnected - retrying sampling request",
            ]
        )

        summary = benchmark.summarize_run(events, stderr)

        self.assertEqual(summary["events"]["web_search"], 2)
        self.assertEqual(summary["events"]["command_execution"], 1)
        self.assertEqual(summary["usage"]["total_tokens"], 1500)
        self.assertEqual(summary["runtime_errors"]["model_cache_schema"], 1)
        self.assertEqual(summary["runtime_errors"]["plugin_refresh"], 1)
        self.assertEqual(summary["runtime_errors"]["stream_disconnect"], 1)

    def test_benchmark_summary_computes_total_for_current_codex_usage_shape(self):
        benchmark = load_module("run_codex_benchmark_current_usage", BENCHMARK)
        events = [
            {
                "type": "turn.completed",
                "usage": {
                    "cached_input_tokens": 373_248,
                    "input_tokens": 406_180,
                    "output_tokens": 21_044,
                    "reasoning_output_tokens": 1_010,
                },
            }
        ]

        summary = benchmark.summarize_run(events, "")

        self.assertEqual(summary["usage"]["total_tokens"], 427_224)
        self.assertEqual(summary["usage"]["cached_input_tokens"], 373_248)

    def test_benchmark_runtime_home_excludes_shared_cache_and_plugins(self):
        benchmark = load_module("run_codex_benchmark_home", BENCHMARK)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            runtime_home = root / "runtime-home"

            installed = benchmark.initialize_runtime_home(SKILL_ROOT, runtime_home)

            self.assertEqual(
                installed,
                runtime_home / ".agents" / "skills" / "analyze-repo-for-kubernetes",
            )
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((runtime_home / ".codex").is_dir())
            self.assertTrue((runtime_home / "workspace").is_dir())
            self.assertFalse((runtime_home / ".codex" / "models_cache.json").exists())
            self.assertFalse((runtime_home / ".codex" / "plugins").exists())
            self.assertFalse((runtime_home / ".codex" / "config.toml").exists())

            environment = benchmark.build_runtime_environment(
                {"PATH": os.environ["PATH"], "HOME": "/real/home", "CODEX_HOME": "/real/codex"},
                runtime_home,
            )
            self.assertEqual(environment["HOME"], str(runtime_home.resolve()))
            self.assertEqual(environment["CODEX_HOME"], str((runtime_home / ".codex").resolve()))

    def test_benchmark_command_ignores_user_config_and_captures_json_events(self):
        benchmark = load_module("run_codex_benchmark_command", BENCHMARK)

        command = benchmark.build_codex_command(
            codex="codex",
            model="gpt-test-mini",
            cwd=ROOT,
            prompt="analyze",
            final_output=Path("/tmp/final.md"),
            sandbox="workspace-write",
        )

        self.assertIn("--ignore-user-config", command)
        self.assertIn("--disable", command)
        self.assertIn("plugins", command)
        self.assertIn("--json", command)
        self.assertIn("--output-last-message", command)
        self.assertIn("sandbox_workspace_write.network_access=true", command)
        self.assertIn('web_search="disabled"', command)
        self.assertIn("analytics.enabled=false", command)
        self.assertIn("model_context_window=128000", command)
        self.assertIn('model_reasoning_effort="low"', command)
        self.assertNotIn("--ephemeral", command)

    def test_benchmark_timeout_reason_distinguishes_total_and_idle_stalls(self):
        benchmark = load_module("run_codex_benchmark_timeout", BENCHMARK)

        self.assertEqual(
            benchmark.timeout_reason(
                now=101.0,
                started=0.0,
                last_event=90.0,
                total_timeout=100,
                idle_timeout=30,
            ),
            "total",
        )
        self.assertEqual(
            benchmark.timeout_reason(
                now=91.0,
                started=0.0,
                last_event=30.0,
                total_timeout=100,
                idle_timeout=60,
            ),
            "idle",
        )
        self.assertIsNone(
            benchmark.timeout_reason(
                now=89.0,
                started=0.0,
                last_event=30.0,
                total_timeout=100,
                idle_timeout=60,
            )
        )

    def test_benchmark_rejects_verdict_only_final_output(self):
        benchmark = load_module("run_codex_benchmark_final", BENCHMARK)

        self.assertEqual(
            benchmark.final_report_status("설계 입력 충분\n"),
            {"looks_like_report": False, "verdict_only": True},
        )
        self.assertEqual(
            benchmark.final_report_status(
                "# Kubernetes 설계 입력 상세 평가\n\n## 1. 분석 범위\n"
            ),
            {"looks_like_report": True, "verdict_only": False},
        )


if __name__ == "__main__":
    unittest.main()
