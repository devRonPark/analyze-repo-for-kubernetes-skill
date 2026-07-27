#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


LANGUAGES = {"node", "java", "python", "go"}
DECISIONS = {"required", "supporting", "rejected", "missed", "unresolved"}
STATUSES = {"confirmed", "inferred", "unknown", "conflicting"}
REVIEW_STATUSES = {"draft", "reviewed", "approved"}
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_PATTERN = re.compile(r"^[^/]+/[^/]+$")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"missing file: {path}") from None
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON: {path}: {error}") from error


def validate_source(source: object, context: str) -> list[str]:
    if not isinstance(source, dict):
        return [f"{context}: source must be an object"]
    errors: list[str] = []
    path = source.get("path")
    start = source.get("line_start")
    end = source.get("line_end")
    if not isinstance(path, str) or not path:
        errors.append(f"{context}: source.path must be a non-empty string")
    if not isinstance(start, int) or start < 1:
        errors.append(f"{context}: source.line_start must be >= 1")
    if not isinstance(end, int) or end < 1:
        errors.append(f"{context}: source.line_end must be >= 1")
    if isinstance(start, int) and isinstance(end, int) and end < start:
        errors.append(f"{context}: source.line_end must be >= line_start")
    revision = source.get("revision")
    if revision is not None and (not isinstance(revision, str) or not SHA_PATTERN.fullmatch(revision)):
        errors.append(f"{context}: source.revision must be a 40-character lowercase SHA")
    return errors


def validate_observation(payload: object, expected: dict[str, object] | None = None) -> list[str]:
    if not isinstance(payload, dict):
        return ["observation must be an object"]
    errors: list[str] = []
    required = {
        "schema_version",
        "corpus_id",
        "repository",
        "revision",
        "language",
        "repository_shape",
        "workload_candidates",
        "navigation_steps",
        "file_decisions",
        "relationship_edges",
        "design_findings",
        "scanner_misses",
        "rule_candidates",
        "stop_decision",
        "review",
    }
    missing = sorted(required - set(payload))
    if missing:
        errors.append(f"missing observation fields: {', '.join(missing)}")
        return errors
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    repository = payload.get("repository")
    if not isinstance(repository, str) or not REPOSITORY_PATTERN.fullmatch(repository):
        errors.append("repository must use owner/name format")
    revision = payload.get("revision")
    if not isinstance(revision, str) or not SHA_PATTERN.fullmatch(revision):
        errors.append("revision must be a 40-character lowercase SHA")
    language = payload.get("language")
    if language not in LANGUAGES:
        errors.append(f"language must be one of {sorted(LANGUAGES)}")
    if expected:
        for key in ("id", "repository", "language", "revision"):
            observation_key = "corpus_id" if key == "id" else key
            if expected.get(key) != payload.get(observation_key):
                errors.append(f"manifest {key} does not match observation {observation_key}")
    steps = payload.get("navigation_steps")
    if not isinstance(steps, list) or not steps:
        errors.append("navigation_steps must be a non-empty array")
    else:
        orders = [step.get("order") for step in steps if isinstance(step, dict)]
        if orders != list(range(1, len(steps) + 1)):
            errors.append("navigation_steps order must be contiguous and start at 1")
    file_decisions = payload.get("file_decisions")
    if not isinstance(file_decisions, list) or not file_decisions:
        errors.append("file_decisions must be a non-empty array")
    else:
        seen_paths: set[str] = set()
        for index, decision in enumerate(file_decisions):
            context = f"file_decisions[{index}]"
            if not isinstance(decision, dict):
                errors.append(f"{context} must be an object")
                continue
            path = decision.get("path")
            if not isinstance(path, str) or not path:
                errors.append(f"{context}.path must be a non-empty string")
            elif path in seen_paths:
                errors.append(f"duplicate file decision path: {path}")
            else:
                seen_paths.add(path)
            if decision.get("decision") not in DECISIONS:
                errors.append(f"{context}.decision is invalid")
    for collection_name in ("workload_candidates", "design_findings"):
        collection = payload.get(collection_name)
        if not isinstance(collection, list):
            errors.append(f"{collection_name} must be an array")
            continue
        for index, item in enumerate(collection):
            if not isinstance(item, dict):
                errors.append(f"{collection_name}[{index}] must be an object")
                continue
            if item.get("status") not in STATUSES:
                errors.append(f"{collection_name}[{index}].status is invalid")
            evidence = item.get("evidence")
            if not isinstance(evidence, list):
                errors.append(f"{collection_name}[{index}].evidence must be an array")
            else:
                for source_index, source in enumerate(evidence):
                    errors.extend(validate_source(source, f"{collection_name}[{index}].evidence[{source_index}]"))
    relationships = payload.get("relationship_edges")
    if not isinstance(relationships, list):
        errors.append("relationship_edges must be an array")
    else:
        for index, edge in enumerate(relationships):
            if isinstance(edge, dict):
                errors.extend(validate_source(edge.get("source"), f"relationship_edges[{index}].source"))
            else:
                errors.append(f"relationship_edges[{index}] must be an object")
    stop = payload.get("stop_decision")
    if not isinstance(stop, dict) or not isinstance(stop.get("stopped"), bool):
        errors.append("stop_decision.stopped must be boolean")
    review = payload.get("review")
    if not isinstance(review, dict) or review.get("status") not in REVIEW_STATUSES:
        errors.append("review.status is invalid")
    return errors


def validate_corpus(root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = root / "manifest.json"
    try:
        manifest = load_json(manifest_path)
    except ValueError as error:
        return [str(error)]
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "selection_policy", "repositories"}:
        return ["manifest must contain schema_version, selection_policy and repositories"]
    if manifest.get("schema_version") != 1:
        errors.append("manifest schema_version must be 1")
    repositories = manifest.get("repositories")
    if not isinstance(repositories, list):
        return errors + ["manifest repositories must be an array"]
    if len(repositories) != 40:
        errors.append(f"manifest must contain 40 repositories, found {len(repositories)}")
    languages = Counter(item.get("language") for item in repositories if isinstance(item, dict))
    expected_counts = Counter({language: 10 for language in LANGUAGES})
    if languages != expected_counts:
        errors.append(f"manifest language distribution must be {dict(expected_counts)}, found {dict(languages)}")
    ids: set[str] = set()
    repos: set[str] = set()
    for index, item in enumerate(repositories):
        context = f"repositories[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{context} must be an object")
            continue
        corpus_id = item.get("id")
        repository = item.get("repository")
        if not isinstance(corpus_id, str) or not corpus_id:
            errors.append(f"{context}.id must be a non-empty string")
        elif corpus_id in ids:
            errors.append(f"duplicate corpus id: {corpus_id}")
        else:
            ids.add(corpus_id)
        if not isinstance(repository, str) or not REPOSITORY_PATTERN.fullmatch(repository):
            errors.append(f"{context}.repository must use owner/name format")
        elif repository in repos:
            errors.append(f"duplicate repository: {repository}")
        else:
            repos.add(repository)
        if item.get("language") not in LANGUAGES:
            errors.append(f"{context}.language is invalid")
        status = item.get("revision_status")
        if status not in {"unpinned", "pinned"}:
            errors.append(f"{context}.revision_status must be pinned or unpinned")
        if status == "pinned":
            revision = item.get("revision")
            observation_path = item.get("observation")
            if not isinstance(revision, str) or not SHA_PATTERN.fullmatch(revision):
                errors.append(f"{context}.revision must be a 40-character lowercase SHA")
            if not isinstance(observation_path, str) or not observation_path:
                errors.append(f"{context}.observation is required when pinned")
                continue
            observation_file = root.parents[1] / observation_path
            try:
                observation = load_json(observation_file)
            except ValueError as error:
                errors.append(str(error))
                continue
            errors.extend(f"{corpus_id}: {error}" for error in validate_observation(observation, item))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the repository navigation research corpus.")
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "research" / "navigation-corpus",
    )
    args = parser.parse_args(argv)
    errors = validate_corpus(args.root.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("repository navigation corpus is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
