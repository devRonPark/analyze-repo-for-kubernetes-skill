#!/usr/bin/env python3
"""Create a bounded model-facing digest from full deterministic evidence."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


DIGEST_SCHEMA_VERSION = "repository-evidence-digest/v1"
NOISY_KINDS = {"config_key", "python_dependency_or_lock"}
MAX_FILES = 300
MAX_RECORD_BYTES = 64_000
MAX_FOCUS_FILES = 20
FOCUS_EXCLUDED_NAMES = {
    "bun.lock",
    "bun.lockb",
    "cargo.lock",
    "composer.lock",
    "gemfile.lock",
    "go.sum",
    "package-lock.json",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    "uv.lock",
    "yarn.lock",
}
HIGH_PRIORITY_PREFIXES = (
    "compose_",
    "docker_",
    "helm_",
    "kubernetes_",
    "kustomize_",
    "runtime_",
)
HIGH_PRIORITY_KINDS = {
    "absence",
    "container_definition",
    "environment_access",
    "platform_config_hint",
    "platform_hint",
    "platform_process",
}


def compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: record[key]
        for key in ("kind", "evidence", "status", "data")
        if key in record
    }


def priority(record: dict[str, Any]) -> tuple[int, str, str]:
    kind = str(record.get("kind", ""))
    tier = 0 if kind in HIGH_PRIORITY_KINDS or kind.startswith(HIGH_PRIORITY_PREFIXES) else 1
    return tier, kind, str(record.get("evidence", ""))


def compact_file(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: record[key]
        for key in ("path", "language", "line_count")
        if key in record
    }


def evidence_path(record: dict[str, Any]) -> str | None:
    source = record.get("source")
    if isinstance(source, dict) and isinstance(source.get("path"), str):
        return source["path"]
    data = record.get("data")
    if isinstance(data, dict) and isinstance(data.get("path"), str):
        return data["path"]
    evidence = record.get("evidence")
    if not isinstance(evidence, str):
        return None
    path, separator, location = evidence.rpartition(":")
    if separator and location.replace("-", "").isdigit():
        return path
    return None


def focus_path_allowed(path: str) -> bool:
    parts = path.replace("\\", "/").lower().split("/")
    name = parts[-1]
    if name.endswith(".lock") or name in FOCUS_EXCLUDED_NAMES:
        return False
    if any(part in {".github", ".vscode", "test", "tests"} for part in parts[:-1]):
        return False
    if "playwright" in name or name in {"copier.yml", "copier.yaml"}:
        return False
    return not ("alembic" in parts and "versions" in parts)


def compact_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = payload.get("evidence")
    snapshot = payload.get("snapshot")
    if not isinstance(evidence, list) or not isinstance(snapshot, dict):
        raise ValueError("repository evidence payload에 snapshot과 evidence 배열이 필요합니다")

    by_kind = Counter(str(record.get("kind", "")) for record in evidence)
    omitted = Counter(
        str(record.get("kind", ""))
        for record in evidence
        if str(record.get("kind", "")) in NOISY_KINDS
    )
    selected: list[dict[str, Any]] = []
    focus_counts: Counter[str] = Counter()
    focus_tiers: dict[str, int] = {}
    selected_bytes = 0
    candidates = [
        record
        for record in evidence
        if isinstance(record, dict) and str(record.get("kind", "")) not in NOISY_KINDS
    ]
    for record in sorted(candidates, key=priority):
        rendered = compact_record(record)
        record_bytes = len(
            json.dumps(rendered, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        if selected_bytes + record_bytes > MAX_RECORD_BYTES:
            omitted[str(record.get("kind", ""))] += 1
            continue
        selected.append(rendered)
        selected_bytes += record_bytes
        path = evidence_path(record)
        if path and focus_path_allowed(path):
            focus_counts[path] += 1
            focus_tiers[path] = min(focus_tiers.get(path, 1), priority(record)[0])

    focus_files = sorted(
        focus_counts,
        key=lambda path: (focus_tiers[path], -focus_counts[path], path),
    )[:MAX_FOCUS_FILES]

    files = snapshot.get("files", [])
    compact_files = [
        compact_file(record)
        for record in files[:MAX_FILES]
        if isinstance(record, dict)
    ]
    digest = {
        "schema_version": DIGEST_SCHEMA_VERSION,
        "source_schema_version": payload.get("schema_version"),
        "snapshot": {
            key: snapshot.get(key)
            for key in ("repository_root", "analysis_root", "subdirectory", "revision")
        },
        "files": {
            "input": len(files),
            "selected": len(compact_files),
            "omitted": max(0, len(files) - len(compact_files)),
            "items": compact_files,
        },
        "summary": {
            "input_evidence": len(evidence),
            "selected_evidence": len(selected),
            "by_kind": dict(sorted(by_kind.items())),
            "omitted_by_kind": dict(sorted((kind, count) for kind, count in omitted.items() if count)),
        },
        "focus_files": focus_files,
        "evidence": selected,
    }
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a bounded repository evidence digest.")
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.evidence.read_text(encoding="utf-8"))
        digest = compact_evidence(payload)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"실패: {error}", file=sys.stderr)
        return 1
    rendered = json.dumps(digest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
