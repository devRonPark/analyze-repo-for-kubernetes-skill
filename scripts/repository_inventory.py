#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


INVENTORY_SCHEMA_VERSION = "repository-inventory/v1"
MAX_INVENTORY_FILE_BYTES = 1_048_576
IGNORED_PATH_PARTS = {".git", ".hg", ".svn", ".cache"}
DEPENDENCY_CACHE_PATH_PARTS = {
    ".gradle",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "bower_components",
    "node_modules",
    "venv",
}
VENDORED_PATH_PARTS = {"vendor"}
GENERATED_PATH_PARTS = {"build", "coverage", "dist", "out", "target"}
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
CONFIG_FILE_NAMES = {
    ".env",
    ".env.example",
    ".env.sample",
    "application.properties",
    "application.yml",
    "application.yaml",
}
CONFIG_SUFFIXES = (".properties", ".env", ".yaml", ".yml", ".toml", ".json", ".xml")
LANGUAGE_MANIFESTS = {
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "settings.gradle": "java",
    "settings.gradle.kts": "java",
    "package.json": "node",
    "pyproject.toml": "python",
    "go.mod": "go",
    "Gemfile": "ruby",
    "composer.json": "php",
    "Cargo.toml": "rust",
}
LANGUAGE_SUFFIXES = {
    ".cs": "dotnet",
    ".go": "go",
    ".java": "java",
    ".js": "node",
    ".jsx": "node",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".ts": "node",
    ".tsx": "node",
}
SCANNER_FILE_NAMES = {
    "Containerfile",
    "Dockerfile",
    "Makefile",
    "Procfile",
    "Taskfile.yaml",
    "Taskfile.yml",
    "bun.lockb",
    "fly.toml",
    "manifest.yml",
    "npm-shrinkwrap.json",
    "nx.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "railway.toml",
    "render.yaml",
    "serverless.yml",
    "turbo.json",
    "uv.lock",
    "yarn.lock",
}
SCANNER_SUFFIXES = (".csproj", ".fsproj", ".vbproj")
SENSITIVE_FILE_NAMES = {".env"}
SENSITIVE_SUFFIXES = (".key", ".pem", ".p12", ".pfx")
SENSITIVE_NAME = re.compile(r"(?i)(?:password|passwd|secret|token|private[_-]?key|api[_-]?key|access[_-]?key)")


@dataclass(frozen=True)
class InventoryRecord:
    path: str
    path_type: str
    disposition: str
    reason: str
    size_bytes: int | None = None
    mtime_ns: int | None = None
    extension: str = ""
    language: str | None = None
    is_config: bool = False
    content_sha256: str | None = None
    line_count: int | None = None
    symlink_target: str | None = None


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


def safe_relative_path(repository_root: Path, path: Path) -> str:
    resolved_parent = path.parent.resolve()
    try:
        resolved_parent.relative_to(repository_root)
    except ValueError as error:
        raise ValueError("inventory path must stay inside repository root") from error
    return path.relative_to(repository_root).as_posix()


def path_parts(relative_path: str) -> tuple[str, ...]:
    return Path(relative_path).parts


def is_config_path(relative_path: str) -> bool:
    name = Path(relative_path).name
    return name in CONFIG_FILE_NAMES or relative_path.endswith(CONFIG_SUFFIXES)


def language_for_path(relative_path: str) -> str | None:
    path = Path(relative_path)
    name = path.name
    if name in LANGUAGE_MANIFESTS:
        return LANGUAGE_MANIFESTS[name]
    if name.endswith((".csproj", ".fsproj", ".vbproj")):
        return "dotnet"
    return LANGUAGE_SUFFIXES.get(path.suffix.lower())


def is_sensitive_path(relative_path: str) -> bool:
    name = Path(relative_path).name
    lowered = name.lower()
    if lowered in SENSITIVE_FILE_NAMES:
        return True
    if lowered.endswith((".example", ".sample", ".template")):
        return False
    return lowered.endswith(SENSITIVE_SUFFIXES) or bool(SENSITIVE_NAME.search(name))


def included_scanner_input(relative_path: str) -> bool:
    path = Path(relative_path)
    name = path.name
    if name in SCANNER_FILE_NAMES or name in LANGUAGE_MANIFESTS or name.endswith(SCANNER_SUFFIXES):
        return True
    if name.startswith(("Dockerfile.", "Containerfile.")):
        return True
    if path.suffix.lower() in LANGUAGE_SUFFIXES:
        return True
    return is_config_path(relative_path)


def disposition_for_prunable_path(relative_path: str) -> tuple[str, str] | None:
    parts = set(path_parts(relative_path))
    if parts & IGNORED_PATH_PARTS:
        return "ignored", "ignored_path_part"
    if parts & DEPENDENCY_CACHE_PATH_PARTS:
        return "dependency_cache", "dependency_cache_path_part"
    if parts & VENDORED_PATH_PARTS:
        return "vendored", "vendored_path_part"
    if parts & GENERATED_PATH_PARTS:
        return "generated", "generated_path_part"
    return None


def record_from_path(
    path: Path,
    repository_root: Path,
    path_type: str,
    disposition: str,
    reason: str,
    content: bytes | None = None,
    symlink_target: str | None = None,
) -> InventoryRecord:
    relative_path = safe_relative_path(repository_root, path)
    try:
        stat = path.lstat()
        size_bytes = stat.st_size
        mtime_ns = stat.st_mtime_ns
    except OSError:
        size_bytes = None
        mtime_ns = None
    line_count: int | None = None
    content_sha256: str | None = None
    if content is not None:
        content_sha256 = hashlib.sha256(content).hexdigest()
        line_count = len(content.decode("utf-8").splitlines())
    return InventoryRecord(
        path=relative_path,
        path_type=path_type,
        disposition=disposition,
        reason=reason,
        size_bytes=size_bytes,
        mtime_ns=mtime_ns,
        extension=path.suffix.lower(),
        language=language_for_path(relative_path),
        is_config=is_config_path(relative_path),
        content_sha256=content_sha256,
        line_count=line_count,
        symlink_target=symlink_target,
    )


def classify_file(path: Path, repository_root: Path) -> InventoryRecord:
    relative_path = safe_relative_path(repository_root, path)
    pruned = disposition_for_prunable_path(relative_path)
    if pruned is not None:
        return record_from_path(path, repository_root, "file", pruned[0], pruned[1])
    if relative_path.endswith(GENERATED_SUFFIXES):
        return record_from_path(path, repository_root, "file", "generated", "generated_suffix")
    if is_sensitive_path(relative_path):
        return record_from_path(path, repository_root, "file", "sensitive", "sensitive_path")
    try:
        stat = path.stat()
    except OSError:
        return record_from_path(path, repository_root, "file", "read_error", "stat_failed")
    if stat.st_size > MAX_INVENTORY_FILE_BYTES:
        return record_from_path(path, repository_root, "file", "too_large", "too_large_file")
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return record_from_path(path, repository_root, "file", "binary", "binary_extension")
    try:
        content = path.read_bytes()
        content.decode("utf-8")
    except UnicodeDecodeError:
        return record_from_path(path, repository_root, "file", "binary", "binary_content")
    except OSError:
        return record_from_path(path, repository_root, "file", "read_error", "read_failed")
    if b"\x00" in content:
        return record_from_path(path, repository_root, "file", "binary", "binary_content")
    if included_scanner_input(relative_path):
        return record_from_path(path, repository_root, "file", "included", "scanner_input", content=content)
    return record_from_path(path, repository_root, "file", "unclassified", "unclassified_text", content=content)


def scan_directory(repository_root: Path, directory: Path) -> list[InventoryRecord]:
    records: list[InventoryRecord] = []
    try:
        entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
    except OSError:
        return [record_from_path(directory, repository_root, "directory", "read_error", "scandir_failed")]

    for entry in entries:
        path = Path(entry.path)
        relative_path = safe_relative_path(repository_root, path)
        try:
            if entry.is_symlink():
                records.append(
                    record_from_path(
                        path,
                        repository_root,
                        "symlink",
                        "symlink",
                        "symlink_not_followed",
                        symlink_target=os.readlink(path),
                    )
                )
                continue
            if entry.is_dir(follow_symlinks=False):
                pruned = disposition_for_prunable_path(relative_path)
                if pruned is not None:
                    records.append(record_from_path(path, repository_root, "directory", pruned[0], pruned[1]))
                else:
                    records.extend(scan_directory(repository_root, path))
                continue
            if entry.is_file(follow_symlinks=False):
                records.append(classify_file(path, repository_root))
                continue
        except OSError:
            records.append(record_from_path(path, repository_root, "unknown", "read_error", "metadata_failed"))
            continue
        records.append(record_from_path(path, repository_root, "unknown", "unclassified", "unsupported_file_type"))
    return records


def inventory_record_to_dict(record: InventoryRecord) -> dict[str, Any]:
    rendered = asdict(record)
    return {key: value for key, value in rendered.items() if value is not None}


def inventory_summary(records: list[InventoryRecord]) -> dict[str, Any]:
    by_disposition: dict[str, int] = {}
    for record in records:
        by_disposition[record.disposition] = by_disposition.get(record.disposition, 0) + 1
    total_paths = len(records)
    included = by_disposition.get("included", 0)
    return {
        "by_disposition": dict(sorted(by_disposition.items())),
        "excluded_paths": total_paths - included,
        "included_paths": included,
        "reconciled": sum(by_disposition.values()) == total_paths,
        "total_paths": total_paths,
    }


def build_inventory(
    repository_root: Path,
    analysis_root: Path,
    subdirectory: str,
    revision: str | None = None,
) -> dict[str, Any]:
    records = sorted(scan_directory(repository_root, analysis_root), key=lambda record: record.path)
    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "repository_root": str(repository_root),
        "analysis_root": str(analysis_root),
        "subdirectory": subdirectory,
        "revision": revision,
        "summary": inventory_summary(records),
        "paths": [inventory_record_to_dict(record) for record in records],
    }


def inventory_repository(target: Path, subdirectory: str = ".") -> dict[str, Any]:
    repository_root, analysis_root, normalized_subdirectory = resolve_roots(target, subdirectory)
    return build_inventory(
        repository_root,
        analysis_root,
        normalized_subdirectory,
        revision=git_revision(repository_root),
    )


def included_file_records(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        record
        for record in inventory.get("paths", [])
        if record.get("path_type") == "file" and record.get("disposition") == "included"
    ]


def format_diagnostics(summary: dict[str, Any]) -> str:
    counts = " ".join(f"{key}={value}" for key, value in sorted(summary.get("by_disposition", {}).items()))
    return (
        f"inventory: total={summary.get('total_paths', 0)} "
        f"included={summary.get('included_paths', 0)} "
        f"excluded={summary.get('excluded_paths', 0)} {counts}"
    ).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect repository inventory diagnostics as JSON.")
    parser.add_argument("target", type=Path, help="Local repository path to scan read-only")
    parser.add_argument("--subdirectory", default=".", help="Repository-relative analysis path")
    parser.add_argument("--output", type=Path, help="Write inventory JSON to this path instead of stdout")
    parser.add_argument("--diagnostics", action="store_true", help="Print compact inventory diagnostics to stderr")
    args = parser.parse_args(argv)

    try:
        payload = inventory_repository(args.target, args.subdirectory)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    if args.diagnostics:
        print(format_diagnostics(payload["summary"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
