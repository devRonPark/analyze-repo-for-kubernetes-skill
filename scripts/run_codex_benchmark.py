#!/usr/bin/env python3
"""Run an isolated Codex CLI benchmark and classify runtime bottlenecks."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import time
from typing import Any


SKILL_NAME = "analyze-repo-for-kubernetes"
REPORT_TITLES = (
    "# Kubernetes 설계 입력 요약",
    "# Kubernetes 설계 입력 상세 평가",
    "# Kubernetes 이관 요약",
    "# Kubernetes 이관 상세 평가",
)
VERDICTS = {"설계 입력 충분", "추가 정보 필요", "분석 불가"}


class BenchmarkError(ValueError):
    """Raised when the isolated benchmark cannot be configured safely."""


def initialize_runtime_home(
    skill_root: Path,
    runtime_home: Path,
    auth_file: Path | None = None,
) -> Path:
    if runtime_home.exists() or runtime_home.is_symlink():
        raise BenchmarkError("runtime home은 존재하지 않는 directory여야 합니다")
    if not (skill_root / "SKILL.md").is_file():
        raise BenchmarkError("skill root에서 SKILL.md를 찾을 수 없습니다")
    runtime_home.mkdir(parents=True)
    (runtime_home / "workspace").mkdir()
    codex_home = runtime_home / ".codex"
    codex_home.mkdir()
    installed = runtime_home / ".agents" / "skills" / SKILL_NAME
    installed.parent.mkdir(parents=True)
    shutil.copytree(skill_root, installed)
    if auth_file is not None:
        if auth_file.is_symlink() or not auth_file.is_file():
            raise BenchmarkError("auth file은 symlink가 아닌 일반 파일이어야 합니다")
        destination = codex_home / "auth.json"
        shutil.copyfile(auth_file, destination)
        destination.chmod(0o600)
    return installed


def build_runtime_environment(
    base: dict[str, str],
    runtime_home: Path,
) -> dict[str, str]:
    environment = base.copy()
    resolved_home = runtime_home.resolve(strict=True)
    environment["HOME"] = str(resolved_home)
    environment["CODEX_HOME"] = str((resolved_home / ".codex").resolve(strict=True))
    return environment


def build_codex_command(
    *,
    codex: str,
    model: str,
    cwd: Path,
    prompt: str,
    final_output: Path,
    sandbox: str = "read-only",
) -> list[str]:
    command = [
        codex,
        "-a",
        "never",
        "-m",
        model,
        "-C",
        str(cwd),
        "-s",
        sandbox,
        "--disable",
        "plugins",
        "-c",
        'web_search="disabled"',
        "-c",
        "analytics.enabled=false",
        "-c",
        "model_context_window=128000",
        "-c",
        'model_reasoning_effort="low"',
    ]
    if sandbox == "workspace-write":
        command.extend(["-c", "sandbox_workspace_write.network_access=true"])
    command.extend([
        "exec",
        "--ignore-user-config",
        "--json",
        "--output-last-message",
        str(final_output),
        prompt,
    ])
    return command


def nested_usage(value: Any) -> dict[str, int] | None:
    if isinstance(value, dict):
        has_total = isinstance(value.get("total_tokens"), int)
        has_current_shape = isinstance(value.get("input_tokens"), int) and isinstance(
            value.get("output_tokens"), int
        )
        if has_total or has_current_shape:
            usage = {
                key: item
                for key, item in value.items()
                if key.endswith("_tokens") and isinstance(item, int)
            }
            if "total_tokens" not in usage:
                usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
            return usage
        for item in value.values():
            usage = nested_usage(item)
            if usage is not None:
                return usage
    elif isinstance(value, list):
        for item in value:
            usage = nested_usage(item)
            if usage is not None:
                return usage
    return None


def timeout_reason(
    *,
    now: float,
    started: float,
    last_event: float,
    total_timeout: int,
    idle_timeout: int,
) -> str | None:
    if now - started > total_timeout:
        return "total"
    if now - last_event > idle_timeout:
        return "idle"
    return None


def final_report_status(text: str) -> dict[str, bool]:
    stripped = text.strip()
    return {
        "looks_like_report": stripped.startswith(REPORT_TITLES),
        "verdict_only": stripped in VERDICTS,
    }


def summarize_run(events: list[dict[str, Any]], stderr: str) -> dict[str, Any]:
    completed_items = Counter(
        str(event.get("item", {}).get("type"))
        for event in events
        if event.get("type") == "item.completed" and event.get("item", {}).get("type")
    )
    usage: dict[str, int] = {}
    for event in reversed(events):
        found = nested_usage(event)
        if found is not None:
            usage = found
            break
    return {
        "events": dict(sorted(completed_items.items())),
        "usage": usage,
        "runtime_errors": {
            "model_cache_schema": stderr.count("missing field supports_reasoning_summaries"),
            "plugin_refresh": stderr.count("failed to refresh remote installed plugins cache"),
            "stream_disconnect": stderr.count("stream disconnected"),
        },
    }


def run_streaming(
    command: list[str],
    environment: dict[str, str],
    timeout_seconds: int,
    idle_timeout_seconds: int,
    events_path: Path,
    stderr_path: Path,
) -> tuple[int, str | None, float, list[dict[str, Any]], str]:
    started = time.monotonic()
    last_event = started
    process = subprocess.Popen(
        command,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    events: list[dict[str, Any]] = []
    stderr_lines: list[str] = []
    timed_out: str | None = None

    with events_path.open("w", encoding="utf-8") as event_output, stderr_path.open(
        "w", encoding="utf-8"
    ) as error_output:
        while selector.get_map():
            now = time.monotonic()
            timed_out = timeout_reason(
                now=now,
                started=started,
                last_event=last_event,
                total_timeout=timeout_seconds,
                idle_timeout=idle_timeout_seconds,
            )
            if timed_out is not None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                break
            ready = selector.select(timeout=0.25)
            for key, _mask in ready:
                line = key.fileobj.readline()
                if not line:
                    selector.unregister(key.fileobj)
                    continue
                last_event = time.monotonic()
                observed = round(last_event - started, 6)
                if key.data == "stderr":
                    stderr_lines.append(line)
                    error_output.write(line)
                    error_output.flush()
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    event = {"type": "unparsed_stdout", "text": line.rstrip("\n")}
                events.append(event)
                event_output.write(
                    json.dumps(
                        {"observed_at_seconds": observed, "event": event},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
                event_output.flush()

    if process.poll() is None:
        process.wait()
    elapsed = time.monotonic() - started
    return process.returncode, timed_out, elapsed, events, "".join(stderr_lines)


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description="Run Codex with an isolated home and emit JSON bottleneck metrics."
    )
    argument_parser.add_argument("--skill-root", type=Path, required=True)
    argument_parser.add_argument("--runtime-home", type=Path, required=True)
    argument_parser.add_argument("--output-dir", type=Path, required=True)
    argument_parser.add_argument("--auth-file", type=Path)
    argument_parser.add_argument("--model", required=True)
    argument_parser.add_argument("--prompt", required=True)
    argument_parser.add_argument("--codex", default="codex")
    argument_parser.add_argument("--sandbox", choices=["read-only", "workspace-write"], default="read-only")
    argument_parser.add_argument("--timeout-seconds", type=int, default=900)
    argument_parser.add_argument("--idle-timeout-seconds", type=int, default=120)
    return argument_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.timeout_seconds < 1:
        parser().error("--timeout-seconds must be positive")
    if args.idle_timeout_seconds < 1:
        parser().error("--idle-timeout-seconds must be positive")
    if args.output_dir.exists() or args.output_dir.is_symlink():
        parser().error("--output-dir must not exist")
    args.output_dir.mkdir(parents=True)

    try:
        installed = initialize_runtime_home(args.skill_root, args.runtime_home, args.auth_file)
    except (BenchmarkError, OSError) as error:
        print(f"실패: {error}", file=sys.stderr)
        return 2

    final_output = args.output_dir / "final.md"
    events_path = args.output_dir / "events.jsonl"
    stderr_path = args.output_dir / "stderr.log"
    command = build_codex_command(
        codex=args.codex,
        model=args.model,
        cwd=args.runtime_home / "workspace",
        prompt=args.prompt,
        final_output=final_output,
        sandbox=args.sandbox,
    )
    environment = build_runtime_environment(dict(os.environ), args.runtime_home)

    try:
        exit_code, timed_out, elapsed, events, stderr = run_streaming(
            command,
            environment,
            args.timeout_seconds,
            args.idle_timeout_seconds,
            events_path,
            stderr_path,
        )
    except OSError as error:
        print(f"실패: Codex CLI를 실행할 수 없습니다: {error}", file=sys.stderr)
        return 2

    summary = summarize_run(events, stderr)
    final_text = final_output.read_text(encoding="utf-8") if final_output.is_file() else ""
    final_status = final_report_status(final_text)
    metrics = {
        "schema_version": 1,
        "command": command,
        "model": args.model,
        "installed_skill": str(installed),
        "execution_cwd": str(args.runtime_home / "workspace"),
        "elapsed_seconds": round(elapsed, 6),
        "exit_code": exit_code,
        "timed_out": timed_out is not None,
        "timeout_reason": timed_out,
        "final": {
            "exists": final_output.is_file(),
            "bytes": final_output.stat().st_size if final_output.is_file() else 0,
            **final_status,
        },
        **summary,
    }
    (args.output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    return 0 if exit_code == 0 and final_status["looks_like_report"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
