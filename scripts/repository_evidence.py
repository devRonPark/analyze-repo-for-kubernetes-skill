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
from typing import Any, Callable


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
DOCKER_INSTRUCTIONS = {"FROM", "COPY", "RUN", "WORKDIR", "USER", "ENV", "EXPOSE", "ENTRYPOINT", "CMD", "HEALTHCHECK"}
COMPOSE_FILE_NAMES = {"compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"}
COMPOSE_SERVICE_FIELDS = {
    "image",
    "build",
    "command",
    "entrypoint",
    "ports",
    "expose",
    "environment",
    "env_file",
    "depends_on",
    "profiles",
    "volumes",
    "networks",
}
KUBERNETES_KINDS = {
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "Job",
    "CronJob",
    "Service",
    "Ingress",
    "ConfigMap",
    "Secret",
    "PersistentVolumeClaim",
}
KUSTOMIZE_FIELDS = {"resources", "patches", "images", "configMapGenerator", "secretGenerator", "namespace", "commonLabels"}
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
PLATFORM_FILES = {
    "Procfile": "procfile",
    "fly.toml": "fly",
    "render.yaml": "render",
    "railway.toml": "railway",
    "manifest.yml": "cloud_foundry",
    "serverless.yml": "serverless",
    "nx.json": "nx",
    "turbo.json": "turbo",
    "Makefile": "make",
    "Taskfile.yml": "taskfile",
    "Taskfile.yaml": "taskfile",
}
SENSITIVE_NAME = r"(?:password|passwd|secret|token|private[_-]?key|api[_-]?key|access[_-]?key)"
INLINE_SECRET_VALUE = re.compile(rf"(?i)(\b[A-Za-z0-9_.-]*{SENSITIVE_NAME}[A-Za-z0-9_.-]*\s*[:=]\s*)([^\s,;]+)")
INLINE_SECRET_FLAG = re.compile(
    rf"(?i)(--{SENSITIVE_NAME})((?:[\"']?\s*[,=]\s*[\"']?)|(?:\s+[\"']?))([^\s,\]\"]+)"
)
URL_CREDENTIALS = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
BASIC_AUTH_CREDENTIALS = re.compile(r"(?i)((?:-u|--user)\s+)[^\s:]+:[^\s]+")
AUTHORIZATION_BEARER = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s,\]\"']+)")


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


def redact_sensitive_text(text: str) -> str:
    redacted = redact_secret_value(text)
    redacted = URL_CREDENTIALS.sub(r"\1[REDACTED]@", redacted)
    redacted = BASIC_AUTH_CREDENTIALS.sub(r"\1[REDACTED]", redacted)
    redacted = AUTHORIZATION_BEARER.sub(r"\1[REDACTED]", redacted)
    redacted = INLINE_SECRET_VALUE.sub(r"\1[REDACTED]", redacted)
    return INLINE_SECRET_FLAG.sub(r"\1\2[REDACTED]", redacted)


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


def leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def yaml_key(line: str) -> str | None:
    match = re.match(r"^\s*(?:-\s+)?([A-Za-z0-9_.-]+):", line)
    return match.group(1) if match else None


def config_key_name(line: str) -> str | None:
    match = re.match(r"^\s*[\"']?([A-Za-z0-9_.-]+)[\"']?\s*[:=]", line)
    return match.group(1) if match else None


def is_compose_file(name: str) -> bool:
    lowered = name.lower()
    return lowered in COMPOSE_FILE_NAMES or lowered.startswith(("compose.", "docker-compose."))


def collect_json_config_keys(
    path: str,
    lines: list[str],
    add: Callable[[str, str, dict[str, Any]], None],
) -> None:
    try:
        payload = json.loads("\n".join(lines))
    except json.JSONDecodeError:
        return

    def visit(value: Any, prefix: str = "") -> None:
        if not isinstance(value, dict):
            return
        for key, nested in value.items():
            if not isinstance(key, str):
                continue
            full_key = f"{prefix}.{key}" if prefix else key
            line_number = next(
                (index for index, line in enumerate(lines, start=1) if re.search(rf'\"{re.escape(key)}\"\s*:', line)),
                1,
            )
            add("config_key", positive_evidence(path, line_number), {"path": path, "key": full_key})
            visit(nested, full_key)

    visit(payload)


def collect_language_evidence(
    path: str,
    lines: list[str],
    add: Callable[[str, str, dict[str, Any]], None],
) -> None:
    name = Path(path).name
    scope = Path(path).parent.as_posix() or "."
    language = LANGUAGE_MANIFESTS.get(name)
    if language is None and name.endswith((".csproj", ".fsproj", ".vbproj")):
        language = "dotnet"
    if language:
        add("language_manifest", positive_evidence(path, 1), {"language": language, "path": path})

    lock_managers = {
        "package-lock.json": "npm",
        "npm-shrinkwrap.json": "npm",
        "pnpm-lock.yaml": "pnpm",
        "yarn.lock": "yarn",
        "bun.lockb": "bun",
    }
    if name in lock_managers:
        add("package_manager_hint", positive_evidence(path, 1), {"manager": lock_managers[name], "scope": scope, "path": path})
    if name in {"mvnw", "mvnw.cmd"}:
        add("java_wrapper", positive_evidence(path, 1), {"tool": "maven", "path": path})
    if name in {"gradlew", "gradlew.bat"}:
        add("java_wrapper", positive_evidence(path, 1), {"tool": "gradle", "path": path})

    if name == "package.json":
        try:
            package_data = json.loads("\n".join(lines))
        except json.JSONDecodeError:
            package_data = {}
        scripts = package_data.get("scripts") if isinstance(package_data, dict) else None
        if isinstance(scripts, dict):
            for script_name, command in scripts.items():
                if isinstance(script_name, str) and isinstance(command, str):
                    add(
                        "node_script",
                        positive_evidence(path, 1),
                        {"script": script_name, "scope": scope, "path": path},
                    )

    for index, line in enumerate(lines, start=1):
        if name == "package.json":
            package_manager = re.search(r'"packageManager"\s*:\s*"([A-Za-z0-9_.-]+)', line)
            if package_manager:
                add("package_manager_hint", positive_evidence(path, index), {"manager": package_manager.group(1), "scope": scope, "path": path})
            if re.search(r'"(?:workspaces|packages)"\s*:', line):
                add("node_workspace", positive_evidence(path, index), {"path": path})
            if re.search(r'"(?:scripts|start|main|bin)"\s*:', line):
                add("node_script_or_entrypoint", positive_evidence(path, index), {"path": path})
        if name == "pom.xml" and re.search(r"<(?:packaging|dependency|profile|mainClass)>", line):
            add("java_build_hint", positive_evidence(path, index), {"path": path})
        if name.startswith("requirements") or name in {"poetry.lock", "uv.lock", "Pipfile.lock"}:
            add("python_dependency_or_lock", positive_evidence(path, index), {"path": path})
        if name == "go.mod" and re.match(r"\s*(?:module|go|require|replace)\s+", line):
            add("go_module_hint", positive_evidence(path, index), {"path": path})
        if name.endswith((".csproj", ".fsproj", ".vbproj")) and re.search(r"<(?:TargetFramework|OutputType|PackageReference)", line):
            add("dotnet_project_hint", positive_evidence(path, index), {"path": path})
        if name == "Cargo.toml" and re.match(r"\s*\[(?:package|workspace|dependencies|bin)", line):
            add("rust_cargo_hint", positive_evidence(path, index), {"path": path})
        if name == "artisan":
            add("php_artisan_hint", positive_evidence(path, index), {"path": path})
        if re.search(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)", line):
            key = re.search(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)", line).group(1)
            add("environment_access", positive_evidence(path, index), {"key": key, "path": path})
        if re.search(r"(?:os\.getenv|os\.environ(?:\.get)?|ENV\[|getenv)\(", line):
            add("environment_access", positive_evidence(path, index), {"path": path})
        if re.search(r"\b(?:FastAPI\(|WSGI|ASGI|Celery|RQ\(|package main|func main\(|SpringApplication\.run|Rails\.application|artisan)\b", line):
            add("language_runtime_entrypoint_hint", positive_evidence(path, index), {"path": path})


def collect_platform_evidence(
    path: str,
    lines: list[str],
    add: Callable[[str, str, dict[str, Any]], None],
) -> None:
    name = Path(path).name
    platform = PLATFORM_FILES.get(name)
    if platform == "cloud_foundry" and not any(line.strip() == "applications:" for line in lines):
        platform = None
    if platform:
        add("platform_hint", positive_evidence(path, 1), {"platform": platform, "path": path})
        if name.endswith(".json"):
            try:
                payload = json.loads("\n".join(lines))
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                for field in payload:
                    if isinstance(field, str):
                        line_number = next(
                            (index for index, line in enumerate(lines, start=1) if re.search(rf'\"{re.escape(field)}\"\s*:', line)),
                            1,
                        )
                        add("platform_config_hint", positive_evidence(path, line_number), {"platform": platform, "field": field, "path": path})
            return
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if platform == "procfile":
                process = re.match(r"^([A-Za-z0-9_.-]+):\s*(.+)$", stripped)
                if process:
                    add(
                        "platform_process",
                        positive_evidence(path, index),
                        {"platform": platform, "process_type": process.group(1), "path": path},
                    )
                continue
            field = yaml_key(line)
            if field is None:
                assignment = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*=", line)
                field = assignment.group(1) if assignment else None
            if field:
                add("platform_config_hint", positive_evidence(path, index), {"platform": platform, "field": field, "path": path})


def collect_docker_evidence(
    path: str,
    lines: list[str],
    add: Callable[[str, str, dict[str, Any]], None],
) -> None:
    for index, line in enumerate(lines, start=1):
        match = re.match(r"^\s*([A-Za-z]+)\b", line)
        if not match:
            continue
        instruction = match.group(1).upper()
        if instruction not in DOCKER_INSTRUCTIONS:
            continue
        add("docker_instruction", positive_evidence(path, index), {"instruction": instruction, "path": path})
        if instruction == "ENV":
            instruction_value = line.strip()[len(match.group(0)):].strip()
            assignment = re.match(r"([A-Za-z_][A-Za-z0-9_]*)(?:\s*=|\s+)", instruction_value)
            if assignment:
                add("docker_env_key", positive_evidence(path, index), {"key": assignment.group(1), "path": path})


def collect_compose_evidence(
    path: str,
    lines: list[str],
    add: Callable[[str, str, dict[str, Any]], None],
) -> None:
    in_services = False
    current_service: str | None = None
    environment_indent: int | None = None
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        indent = leading_spaces(line)
        if stripped == "services:":
            in_services = True
            current_service = None
            continue
        if in_services and indent == 0 and stripped and not stripped.startswith("#"):
            in_services = False
            current_service = None
        service_match = re.match(r"^\s{2}([A-Za-z0-9_.-]+):\s*(?:#.*)?$", line)
        if in_services and service_match:
            current_service = service_match.group(1)
            environment_indent = None
            add("compose_service", positive_evidence(path, index), {"service": current_service, "path": path})
            continue
        if not current_service:
            continue
        key = yaml_key(line)
        if key in COMPOSE_SERVICE_FIELDS:
            add("compose_service_field", positive_evidence(path, index), {"service": current_service, "field": key, "path": path})
            environment_indent = indent if key == "environment" else None
            if key == "environment":
                for env_key in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*=", line):
                    add("compose_env_key", positive_evidence(path, index), {"service": current_service, "key": env_key, "path": path})
        elif environment_indent is not None and indent > environment_indent and key:
            add("compose_env_key", positive_evidence(path, index), {"service": current_service, "key": key, "path": path})
        elif environment_indent is not None and indent > environment_indent:
            list_value = re.match(r"^\s*-\s*([A-Za-z_][A-Za-z0-9_]*)=", line)
            if list_value:
                add("compose_env_key", positive_evidence(path, index), {"service": current_service, "key": list_value.group(1), "path": path})


def collect_kubernetes_evidence(
    path: str,
    lines: list[str],
    add: Callable[[str, str, dict[str, Any]], None],
) -> None:
    current_kind: str | None = None
    metadata_indent: int | None = None
    env_indent: int | None = None
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        indent = leading_spaces(line)
        kind_match = re.match(r"^\s*kind:\s*([A-Za-z]+)", line)
        if kind_match:
            possible_kind = kind_match.group(1)
            current_kind = possible_kind if possible_kind in KUBERNETES_KINDS else None
            metadata_indent = None
            env_indent = None
            if current_kind:
                add("kubernetes_resource", positive_evidence(path, index), {"resource_kind": current_kind, "path": path})
            continue
        if current_kind is None:
            continue
        if stripped == "metadata:":
            metadata_indent = indent
            continue
        key = yaml_key(line)
        if metadata_indent is not None and indent > metadata_indent and key == "name":
            value = line.split(":", 1)[1].strip()
            add("kubernetes_metadata", positive_evidence(path, index), {"resource_kind": current_kind, "field": "name", "value": value, "path": path})
            metadata_indent = None
        if key in {"image", "command", "args", "containerPort"}:
            data = {"resource_kind": current_kind, "field": key, "path": path}
            if key in {"image", "containerPort"}:
                data["value"] = line.split(":", 1)[1].strip()
            add("kubernetes_container_field", positive_evidence(path, index), data)
        if key == "env":
            env_indent = indent
        elif env_indent is not None and indent > env_indent and key == "name":
            value = line.split(":", 1)[1].strip()
            add("kubernetes_env_key", positive_evidence(path, index), {"resource_kind": current_kind, "key": value, "path": path})
        elif env_indent is not None and indent <= env_indent:
            env_indent = None
        if key and key.endswith("Probe"):
            add("kubernetes_probe", positive_evidence(path, index), {"resource_kind": current_kind, "probe": key, "path": path})
        if key in {"volumeMounts", "volumes", "persistentVolumeClaim"}:
            add("kubernetes_volume", positive_evidence(path, index), {"resource_kind": current_kind, "field": key, "path": path})
        if current_kind == "Service" and key in {"port", "targetPort", "nodePort", "type"}:
            add("kubernetes_service_exposure", positive_evidence(path, index), {"field": key, "path": path})


def collect_helm_evidence(
    path: str,
    lines: list[str],
    add: Callable[[str, str, dict[str, Any]], None],
) -> None:
    parts = Path(path).parts
    name = Path(path).name
    is_chart_file = "Chart.yaml" == name
    if is_chart_file:
        add("helm_chart", positive_evidence(path, 1), {"path": path})
    if name.startswith("values") and name.endswith((".yaml", ".yml")):
        for index, line in enumerate(lines, start=1):
            key = yaml_key(line)
            if key:
                add("helm_values_key", positive_evidence(path, index), {"key": key, "path": path})
    if "templates" in parts:
        for index, line in enumerate(lines, start=1):
            match = re.match(r"^\s*kind:\s*([A-Za-z]+)", line)
            if match:
                add("helm_template_resource", positive_evidence(path, index), {"resource_kind": match.group(1), "path": path})


def collect_kustomize_evidence(
    path: str,
    lines: list[str],
    add: Callable[[str, str, dict[str, Any]], None],
) -> None:
    if Path(path).name not in {"kustomization.yaml", "kustomization.yml", "Kustomization"}:
        return
    for index, line in enumerate(lines, start=1):
        key = yaml_key(line)
        if key in KUSTOMIZE_FIELDS:
            add("kustomize_composition", positive_evidence(path, index), {"field": key, "path": path})


def collect_package_manager_conflicts(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    by_scope: dict[str, list[EvidenceRecord]] = {}
    for record in records:
        if record.kind == "package_manager_hint":
            scope = record.data.get("scope")
            if isinstance(scope, str):
                by_scope.setdefault(scope, []).append(record)
    conflicts: list[EvidenceRecord] = []
    for scope, manager_records in sorted(by_scope.items()):
        managers = sorted({str(record.data["manager"]) for record in manager_records})
        if len(managers) < 2:
            continue
        conflicts.append(
            EvidenceRecord(
                id=f"ev-{len(records) + len(conflicts) + 1:04d}",
                kind="package_manager_conflict",
                status="confirmed",
                evidence=manager_records[0].evidence,
                data={"scope": scope, "managers": managers},
            )
        )
    return conflicts


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
        collect_language_evidence(path, lines, add)
        collect_platform_evidence(path, lines, add)
        if name in {"Dockerfile", "Containerfile"} or name.startswith(("Dockerfile.", "Containerfile.")):
            collect_docker_evidence(path, lines, add)
        if is_compose_file(name):
            collect_compose_evidence(path, lines, add)
        if name.endswith((".yaml", ".yml")):
            collect_kubernetes_evidence(path, lines, add)
            collect_helm_evidence(path, lines, add)
            collect_kustomize_evidence(path, lines, add)
        if is_config_candidate(path) and name.endswith(".json"):
            collect_json_config_keys(path, lines, add)
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if is_config_candidate(path) and not name.endswith(".json"):
                config_key = config_key_name(stripped)
                if config_key:
                    data = {"path": path, "key": config_key}
                    if SECRET_LINE.match(stripped):
                        data["snippet"] = redact_sensitive_text(stripped)
                    add("config_key", positive_evidence(path, index), data)
            if RUNTIME_HINT.search(stripped):
                add(
                    "runtime_entrypoint_hint",
                    positive_evidence(path, index),
                    {"path": path},
                )
            if DEPENDENCY_HINT.search(stripped):
                add(
                    "dependency_hint",
                    positive_evidence(path, index),
                    {"path": path},
                )

    records.extend(collect_package_manager_conflicts(records))
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
