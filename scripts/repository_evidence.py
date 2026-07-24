#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


EXCLUDED_PATH_PARTS = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".gradle",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "bower_components",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
    "vendor",
    "venv",
}
GENERATED_SUFFIXES = (".generated", ".min.js", ".min.css")
BINARY_EXTENSIONS = {
    ".7z",
    ".avif",
    ".bin",
    ".bmp",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".so",
    ".tar",
    ".tgz",
    ".webp",
    ".zip",
}
MANIFEST_FILES = {
    "Cargo.toml",
    "Gemfile",
    "composer.json",
    "go.mod",
    "package.json",
    "pom.xml",
    "pyproject.toml",
}
MANIFEST_SUFFIXES = (".csproj", ".fsproj", ".vbproj")
RUNTIME_HINT = re.compile(
    r"\b(app\.listen|server\.listen|SpringApplication\.run|FastAPI\(|uvicorn|gunicorn|"
    r"celery\s+-A|CMD\b|ENTRYPOINT\b|server\.port|PORT)\b"
)
DEPENDENCY_HINT = re.compile(
    r"\b(postgres|postgresql|mysql|mariadb|redis|rabbitmq|amqp|kafka|mongodb|jdbc:|s3://)\b",
    re.IGNORECASE,
)
CONFIG_FILE_NAMES = {
    ".env",
    ".env.example",
    ".env.sample",
    "application.properties",
    "application.yml",
    "application.yaml",
}
CONFIG_SUFFIXES = (".properties", ".env", ".yaml", ".yml", ".toml", ".json", ".xml")
SECRET_LINE = re.compile(
    r"(?i)^(\s*[\"']?[A-Za-z0-9_.-]*(?:password|passwd|secret|token|private[_-]?key|api[_-]?key|access[_-]?key)[A-Za-z0-9_.-]*[\"']?\s*[:=]\s*)(.+)$"
)


@dataclass(frozen=True)
class FileRecord:
    path: str
    size_bytes: int
    extension: str
    line_count: int


@dataclass(frozen=True)
class RepositorySnapshot:
    repository_root: str
    analysis_root: str
    subdirectory: str
    revision: str | None
    files: list[FileRecord]


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    kind: str
    status: str
    evidence: str
    data: dict[str, Any]


def resolve_roots(target: Path, subdirectory: str) -> tuple[Path, Path, str]:
    repository_root = target.resolve()
    if not repository_root.is_dir():
        raise ValueError(f"repository root does not exist: {repository_root}")
    normalized_subdirectory = subdirectory.strip() or "."
    analysis_root = (repository_root / normalized_subdirectory).resolve()
    try:
        analysis_root.relative_to(repository_root)
    except ValueError as error:
        raise ValueError("analysis root must stay inside repository root") from error
    if not analysis_root.is_dir():
        raise ValueError(f"analysis root does not exist: {analysis_root}")
    relative = analysis_root.relative_to(repository_root).as_posix()
    return repository_root, analysis_root, relative or "."


def git_revision(repository_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    revision = result.stdout.strip()
    if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", revision):
        return revision
    return None


def is_generated_path(relative_path: str) -> bool:
    path = Path(relative_path)
    if any(part in EXCLUDED_PATH_PARTS for part in path.parts):
        return True
    return relative_path.endswith(GENERATED_SUFFIXES)


def is_binary_file(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return True
    if b"\x00" in sample:
        return True
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def redact_secret_value(line: str) -> str:
    match = SECRET_LINE.match(line)
    if not match:
        return line
    return f"{match.group(1)}[REDACTED]"


def walk_text_files(repository_root: Path, analysis_root: Path) -> list[FileRecord]:
    records: list[FileRecord] = []
    for directory, dirnames, filenames in os.walk(analysis_root, topdown=True, followlinks=False):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not is_generated_path((Path(directory) / name).relative_to(repository_root).as_posix())
        )
        for filename in sorted(filenames):
            candidate = Path(directory) / filename
            if candidate.is_symlink() or not candidate.is_file():
                continue
            relative_path = candidate.relative_to(repository_root).as_posix()
            if is_generated_path(relative_path) or is_binary_file(candidate):
                continue
            try:
                stat = candidate.stat()
                line_count = len(read_lines(candidate))
            except OSError:
                continue
            records.append(
                FileRecord(
                    path=relative_path,
                    size_bytes=stat.st_size,
                    extension=candidate.suffix.lower(),
                    line_count=line_count,
                )
            )
    return records


def snapshot_repository(target: Path, subdirectory: str = ".") -> RepositorySnapshot:
    repository_root, analysis_root, normalized_subdirectory = resolve_roots(target, subdirectory)
    return RepositorySnapshot(
        repository_root=str(repository_root),
        analysis_root=str(analysis_root),
        subdirectory=normalized_subdirectory,
        revision=git_revision(repository_root),
        files=walk_text_files(repository_root, analysis_root),
    )


def is_manifest(path: str) -> bool:
    name = Path(path).name
    return name in MANIFEST_FILES or name.endswith(MANIFEST_SUFFIXES)


def is_config_candidate(path: str) -> bool:
    name = Path(path).name
    return name in CONFIG_FILE_NAMES or path.endswith(CONFIG_SUFFIXES)


def positive_evidence(path: str, line_number: int) -> str:
    return f"{path}:{line_number}"


def collect_universal_evidence(snapshot: RepositorySnapshot) -> list[EvidenceRecord]:
    repository_root = Path(snapshot.repository_root)
    records: list[EvidenceRecord] = []
    seen_container_definition = False

    def add(kind: str, evidence: str, data: dict[str, Any]) -> None:
        records.append(
            EvidenceRecord(
                id=f"ev-{len(records) + 1:04d}",
                kind=kind,
                status="confirmed",
                evidence=evidence,
                data=data,
            )
        )

    for file_record in snapshot.files:
        path = file_record.path
        source = repository_root / path
        name = Path(path).name
        if name in {"Dockerfile", "Containerfile"} or name.startswith(("Dockerfile.", "Containerfile.")):
            seen_container_definition = True
            add(
                "container_definition",
                positive_evidence(path, 1),
                {"path": path, "name": name},
            )
        if is_manifest(path):
            add("manifest", positive_evidence(path, 1), {"path": path, "name": name})
        try:
            lines = read_lines(source)
        except OSError:
            continue
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if is_config_candidate(path) and SECRET_LINE.match(stripped):
                add(
                    "config_key",
                    positive_evidence(path, index),
                    {"path": path, "key": stripped.split("=", 1)[0].split(":", 1)[0].strip("\"' "), "snippet": redact_secret_value(stripped)},
                )
            if RUNTIME_HINT.search(stripped):
                add(
                    "runtime_entrypoint_hint",
                    positive_evidence(path, index),
                    {"path": path, "snippet": redact_secret_value(stripped)},
                )
            if DEPENDENCY_HINT.search(stripped):
                add(
                    "dependency_hint",
                    positive_evidence(path, index),
                    {"path": path, "snippet": redact_secret_value(stripped)},
                )

    if not seen_container_definition:
        scope = snapshot.subdirectory
        add(
            "absence",
            f"검색(scope={scope}, pattern=Dockerfile|Containerfile, result=없음)",
            {"scope": scope, "pattern": "Dockerfile|Containerfile", "result": "없음"},
        )
    return records


def scan_repository(target: Path, subdirectory: str = ".") -> dict[str, Any]:
    snapshot = snapshot_repository(target, subdirectory)
    evidence = collect_universal_evidence(snapshot)
    return {
        "schema_version": 1,
        "snapshot": {
            **asdict(snapshot),
            "files": [asdict(record) for record in snapshot.files],
        },
        "evidence": [asdict(record) for record in evidence],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect deterministic repository snapshot and universal evidence as JSON."
    )
    parser.add_argument("target", type=Path, help="Local repository path to scan read-only")
    parser.add_argument("--subdirectory", default=".", help="Repository-relative analysis path")
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout")
    args = parser.parse_args(argv)

    try:
        payload = scan_repository(args.target, args.subdirectory)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
