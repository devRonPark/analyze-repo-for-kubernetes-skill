#!/usr/bin/env python3
"""Prepare one repository analysis workspace without model-directed web discovery."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
SKILL_ROOT = ROOT / "skills" / "analyze-repo-for-kubernetes"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import plain_remote_git_clone
import compact_repository_evidence
import repository_evidence
import source_archive
import source_intake


class PreparationError(ValueError):
    """Raised when an analysis workspace cannot be prepared safely."""


TEMPLATES = {
    "summary": SKILL_ROOT / "assets" / "migration-summary-template.md",
    "detailed": SKILL_ROOT / "assets" / "migration-assessment-template.md",
}


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as output:
        json.dump(payload, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")
        temporary = Path(output.name)
    os.replace(temporary, path)


def safe_subdirectory(value: str) -> PurePosixPath:
    candidate = PurePosixPath(value or ".")
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PreparationError("subdirectory는 analysis root 내부의 상대 경로여야 합니다")
    return candidate


def resolve_analysis_subdirectory(root: Path, base: str, requested: str) -> str:
    base_path = safe_subdirectory(base)
    requested_path = safe_subdirectory(requested)
    combined = base_path / requested_path
    try:
        resolved = (root / combined).resolve(strict=True)
        relative = resolved.relative_to(root.resolve(strict=True))
    except (FileNotFoundError, ValueError) as error:
        raise PreparationError("subdirectory를 analysis root 내부에서 찾을 수 없습니다") from error
    if not resolved.is_dir():
        raise PreparationError("subdirectory는 directory여야 합니다")
    return relative.as_posix() or "."


def request_payload(args: argparse.Namespace) -> dict[str, str]:
    if args.remote_git:
        method, value = "remote_git", args.remote_git
    elif args.local_checkout:
        method, value = "local_checkout", str(Path(args.local_checkout).expanduser())
    else:
        method, value = "source_archive", str(Path(args.source_archive).expanduser())
    return {
        "source_method": method,
        "target_value": value,
        "revision": args.revision or "",
        "subdirectory": args.subdirectory,
        "mode": args.mode,
    }


def load_checkpoint(workspace: Path, request: dict[str, str]) -> dict[str, Any]:
    checkpoint = workspace / "target.json"
    try:
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PreparationError("재사용할 target.json checkpoint가 유효하지 않습니다") from error
    if payload.get("request") != request:
        raise PreparationError("checkpoint 요청이 현재 target, revision, subdirectory 또는 mode와 다릅니다")
    artifacts = payload.get("artifacts", {})
    required = [
        artifacts.get("evidence"),
        artifacts.get("evidence_digest"),
        artifacts.get("report"),
    ]
    if not all(isinstance(value, str) and Path(value).is_file() for value in required):
        raise PreparationError("checkpoint artifact가 없거나 완전하지 않습니다")
    return {**payload, "reused": True}


def create_workspace(path: Path) -> Path:
    if path.exists() or path.is_symlink():
        raise PreparationError("workspace는 존재하지 않는 disposable directory여야 합니다")
    try:
        parent = path.parent.resolve(strict=True)
    except FileNotFoundError as error:
        raise PreparationError("workspace parent directory가 존재해야 합니다") from error
    workspace = parent / path.name
    workspace.mkdir()
    return workspace.resolve(strict=True)


def resolve_source(args: argparse.Namespace, workspace: Path) -> tuple[dict[str, Any], Path, str]:
    if args.remote_git:
        source = plain_remote_git_clone.clone_plain(
            args.remote_git,
            workspace / "repository",
            args.revision,
        )
        root = Path(str(source["resolved_target"]))
        subdirectory = resolve_analysis_subdirectory(root, ".", args.subdirectory)
        return source, root, subdirectory

    if args.local_checkout:
        source = source_intake.resolve_local_checkout(args.local_checkout)
        root = Path(str(source["resolved_target"]))
        subdirectory = resolve_analysis_subdirectory(
            root,
            str(source.get("subdirectory", ".")),
            args.subdirectory,
        )
        return source, root, subdirectory

    source = source_archive.extract_source_archive(
        Path(args.source_archive),
        workspace / "repository",
    )
    root = Path(str(source["resolved_target"]))
    if source["state"] == "awaiting_subdirectory":
        if args.subdirectory == ".":
            candidates = ", ".join(str(item) for item in source["candidate_subdirectories"])
            raise PreparationError(f"source archive subdirectory 선택이 필요합니다: {candidates}")
        subdirectory = resolve_analysis_subdirectory(root, ".", args.subdirectory)
        source = {
            **source,
            "state": "resolved",
            "revision": f"archive-sha256:{source['archive_sha256']}",
            "subdirectory": subdirectory,
        }
        return source, root, subdirectory
    subdirectory = resolve_analysis_subdirectory(root, ".", args.subdirectory)
    return source, root, subdirectory


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    workspace_input = Path(args.workspace).expanduser()
    request = request_payload(args)
    if args.resume:
        workspace = workspace_input.resolve(strict=True)
        return load_checkpoint(workspace, request)

    workspace = create_workspace(workspace_input)
    source, repository_root, subdirectory = resolve_source(args, workspace)
    evidence_path = workspace / "evidence.json"
    evidence_digest_path = workspace / "evidence-digest.json"
    report_path = workspace / "report.md"
    cache_path = workspace / "cache"

    evidence = repository_evidence.scan_repository(
        repository_root,
        subdirectory,
        cache_directory=cache_path,
    )
    atomic_write_json(evidence_path, evidence)
    atomic_write_json(
        evidence_digest_path,
        compact_repository_evidence.compact_evidence(evidence),
    )
    shutil.copyfile(TEMPLATES[args.mode], report_path)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "state": "prepared",
        "reused": False,
        "request": request,
        "mode": args.mode,
        "source": source,
        "analysis_root": str(repository_root.resolve(strict=True)),
        "analysis_subdirectory": subdirectory,
        "artifacts": {
            "evidence": str(evidence_path),
            "evidence_digest": str(evidence_digest_path),
            "report": str(report_path),
            "cache": str(cache_path),
        },
        "validation": {
            "command": [
                "python3",
                str(ROOT / "scripts" / "validate_report.py"),
                str(report_path),
                "--mode",
                args.mode,
                "--repo-root",
                str(repository_root.resolve(strict=True)),
            ]
        },
    }
    atomic_write_json(workspace / "target.json", payload)
    return payload


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description="Resolve a source, collect deterministic evidence, and stage one report template."
    )
    source = argument_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--remote-git")
    source.add_argument("--local-checkout")
    source.add_argument("--source-archive")
    argument_parser.add_argument("--workspace", required=True, type=Path)
    argument_parser.add_argument("--revision")
    argument_parser.add_argument("--subdirectory", default=".")
    argument_parser.add_argument("--mode", choices=sorted(TEMPLATES), default="summary")
    argument_parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse a complete matching target.json checkpoint without cloning or scanning again.",
    )
    return argument_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        payload = prepare(args)
    except (
        OSError,
        PreparationError,
        plain_remote_git_clone.CloneError,
        source_archive.ArchiveError,
        source_intake.IntakeError,
        ValueError,
    ) as error:
        print(f"실패: {error}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
