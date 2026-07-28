#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PLUGIN_NAME = "analyze-repo-for-kubernetes"
MANIFEST_REL = Path(".codex-plugin/plugin.json")
SKILL_REL = Path("skills") / PLUGIN_NAME
SKILL_PATH = SKILL_REL / "SKILL.md"
STRICT_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
FRONTMATTER = re.compile(
    r"^---\nname: ([a-z0-9-]+)\ndescription: (.+)\n---\n"
)
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")

REQUIRED_PLUGIN_FILES = (
    Path("ADR.md"),
    Path("README.md"),
    Path(".mcp.json"),
    Path("hooks.json"),
    Path("contracts/report-contract-v1.json"),
    Path("scripts/bounded_subprocess.py"),
    Path("scripts/report_diagnostics.py"),
    Path("scripts/report_records.py"),
    Path("scripts/report_renderer.py"),
    Path("scripts/render_report.py"),
    Path("scripts/report_session_models.py"),
    Path("scripts/report_session_store.py"),
    Path("scripts/report_work_units.py"),
    Path("scripts/report_lease_planner.py"),
    Path("scripts/report_session_service.py"),
    Path("scripts/report_lifecycle.py"),
    Path("scripts/report_tool_schemas.py"),
    Path("scripts/report_tool_commands.py"),
    Path("scripts/report_tool_handler.py"),
    Path("scripts/report_model_protocol.py"),
    Path("scripts/report_orchestrator.py"),
    Path("mcp/report_tool_server.py"),
    Path("scripts/validate_report.py"),
    Path("scripts/validate_target_report.py"),
    Path("scripts/normalize_report.py"),
    Path("scripts/run_black_box_eval.py"),
    Path("scripts/run_repository_e2e_eval.py"),
    Path("scripts/codex_target_gate_hook.py"),
    Path("scripts/validate_codex_intake.py"),
    Path("scripts/uninstall-codex.sh"),
    Path("scripts/demo_git_readonly_clone.py"),
    Path("scripts/source_intake.py"),
    Path("scripts/plain_remote_git_clone.py"),
    Path("scripts/compact_repository_evidence.py"),
    Path("scripts/prepare_analysis_target.py"),
    Path("scripts/run_codex_benchmark.py"),
    Path("scripts/remote_git_auth.py"),
    Path("scripts/source_archive.py"),
    Path("tests/scenarios.md"),
)
REQUIRED_SKILL_FILES = (
    Path("SKILL.md"),
    Path("agents/openai.yaml"),
    Path("references/workflow.md"),
    Path("references/evidence-pattern-packs.md"),
    Path("references/codex-ui-integration.md"),
    Path("references/interview-first-intake.md"),
    Path("references/remote-git-access.md"),
    Path("references/source-intake-state.md"),
    Path("references/repository-analysis-checklist.md"),
    Path("references/language-discovery-rules.md"),
    Path("references/dependency-analysis.md"),
    Path("references/evidence-and-readiness.md"),
    Path("references/configuration-timing.md"),
    Path("assets/migration-assessment-template.md"),
    Path("assets/migration-summary-template.md"),
    Path("assets/demo-git-credential.example.json"),
)
REQUIRED_MANIFEST_FIELDS = (
    "name",
    "version",
    "description",
    "author.name",
    "author.url",
    "homepage",
    "repository",
    "license",
    "keywords",
    "skills",
    "interface.displayName",
    "interface.shortDescription",
    "interface.longDescription",
    "interface.developerName",
    "interface.category",
    "interface.capabilities",
    "interface.websiteURL",
    "interface.defaultPrompt",
)
REQUIRED_TERMS = (
    "확인됨",
    "추정됨",
    "미확인",
    "상충됨",
    "설계 입력 충분",
    "추가 정보 필요",
    "분석 불가",
    "Dependency matrix",
    "Text dependency graph",
    "A missing Dockerfile is a finding, not an analysis failure",
    "Kubernetes manifest",
    "read-only repository analyst",
    "Repository 콘텐츠",
    "검색(scope=",
    "실행 위치",
    "적용 시점",
    "배포 대상별 실행 정보",
    "Kubernetes 최소 설계 입력",
    "최소 입력 누락",
    "키: 값",
    "Default output mode: summary",
    "Target Resolution Gate",
    "Repository URL",
    "Local path",
    "Source archive",
    "원격 Git URL",
    "소스 압축 파일",
    "remote_git",
    "local_checkout",
    "source_archive",
    "local credential file",
    "Slash Command Input",
    "ResolvedAnalysisRequest",
    "analysis_ready",
    "빠른 구조 파악",
    "전체 상세 보고서",
    "source_method_required",
    "target_value_required",
    "PreToolUse",
    "best-effort",
    "Target Gate",
    "Universal Scanner -> Evidence Pattern Packs -> LLM Triage/Reasoning -> Deterministic Verifier -> Report",
    "deterministic collection",
    "candidate evidence",
    "citation validity",
)


def _nested_value(value: object, dotted_key: str) -> object | None:
    current = value
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _is_non_empty(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return value is not None


def _load_manifest(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"Plugin manifest is missing: {MANIFEST_REL}")
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"Plugin manifest is not valid UTF-8 JSON: {exc}")
        return None
    if not isinstance(manifest, dict):
        errors.append("Plugin manifest root must be a JSON object")
        return None
    return manifest


def _validate_manifest(manifest: dict[str, Any], errors: list[str]) -> None:
    for field in REQUIRED_MANIFEST_FIELDS:
        if not _is_non_empty(_nested_value(manifest, field)):
            errors.append(f"Plugin manifest requires non-empty {field}")

    version = manifest.get("version")
    if not isinstance(version, str) or STRICT_SEMVER.fullmatch(version) is None:
        errors.append("Plugin manifest version must use strict semver")
    if manifest.get("skills") != "./skills/":
        errors.append('Plugin manifest skills must be exactly "./skills/"')
    if manifest.get("mcpServers") != "./.mcp.json":
        errors.append(
            'Plugin manifest mcpServers must be exactly "./.mcp.json"'
        )
    if manifest.get("name") != PLUGIN_NAME:
        errors.append(f"Plugin manifest name must be {PLUGIN_NAME}")


def _validate_skill(
    root: Path,
    manifest: dict[str, Any] | None,
    errors: list[str],
) -> None:
    skill_root = root / SKILL_REL
    skill_path = skill_root / "SKILL.md"

    if (root / "SKILL.md").exists():
        errors.append("root SKILL.md is not allowed in the Plugin package")

    skill_files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name.lower() == "skill.md"
    )
    if skill_files != [skill_path]:
        relative = ", ".join(
            str(path.relative_to(root)) for path in skill_files
        ) or "none"
        errors.append(
            "Plugin must contain exactly one canonical nested SKILL.md at "
            f"{SKILL_PATH}; found: {relative}"
        )

    for relative in REQUIRED_SKILL_FILES:
        if not (skill_root / relative).is_file():
            errors.append(f"required nested Skill file is missing: {relative}")

    if not skill_path.is_file():
        return

    text = skill_path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    if match is None:
        errors.append(
            "nested SKILL.md frontmatter requires name and one-line description"
        )
    else:
        skill_name, description = match.groups()
        plugin_name = manifest.get("name") if manifest is not None else None
        if skill_name != plugin_name:
            errors.append(
                f"nested Skill name {skill_name!r} must match Plugin name {plugin_name!r}"
            )
        if not description.startswith("Use when "):
            errors.append("nested Skill description must start with 'Use when '")
        if len(description) > 500:
            errors.append("nested Skill description must not exceed 500 characters")

    resolved_skill_root = skill_root.resolve()
    for raw_link in MARKDOWN_LINK.findall(text):
        if raw_link.startswith(("#", "http://", "https://", "mailto:")):
            continue
        link = raw_link.split("#", 1)[0]
        if not link:
            continue
        candidate = (skill_root / link).resolve()
        if not candidate.is_relative_to(resolved_skill_root):
            errors.append(
                f"Skill resource link escapes nested Skill root: {raw_link}"
            )
        elif not candidate.is_file():
            errors.append(f"broken nested Skill resource link: {raw_link}")


def _validate_required_content(root: Path, errors: list[str]) -> None:
    for relative in REQUIRED_PLUGIN_FILES:
        if not (root / relative).is_file():
            errors.append(f"required Plugin file is missing: {relative}")

    markdown = sorted(root.rglob("*.md"))
    all_text = "\n".join(
        path.read_text(encoding="utf-8") for path in markdown
    )
    for term in REQUIRED_TERMS:
        if term not in all_text:
            errors.append(f"required package contract term is missing: {term}")

    placeholder = re.compile(r"\b(?:TBD|TODO|FIXME)\b")
    for path in markdown:
        if placeholder.search(path.read_text(encoding="utf-8")):
            errors.append(
                "package Markdown contains a placeholder marker: "
                f"{path.relative_to(root)}"
            )


def _validate_mcp_config(root: Path, errors: list[str]) -> None:
    path = root / ".mcp.json"
    if not path.is_file():
        return
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"MCP config is not valid UTF-8 JSON: {exc}")
        return
    expected = {
        "type": "stdio",
        "command": "python3",
        "args": ["${PLUGIN_ROOT}/mcp/report_tool_server.py"],
    }
    servers = config.get("mcpServers") if isinstance(config, dict) else None
    server = servers.get("report-tools") if isinstance(servers, dict) else None
    if server != expected:
        errors.append(
            "MCP config must register only the local foreground report-tools "
            "stdio server"
        )


def validate_plugin_package(root: Path) -> tuple[str, ...]:
    package_root = Path(root).resolve()
    errors: list[str] = []
    manifest = _load_manifest(package_root / MANIFEST_REL, errors)
    if manifest is not None:
        _validate_manifest(manifest, errors)
    _validate_skill(package_root, manifest, errors)
    _validate_required_content(package_root, errors)
    _validate_mcp_config(package_root, errors)
    return tuple(errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Codex Plugin package를 검증합니다.")
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Plugin root directory",
    )
    args = parser.parse_args(argv)

    errors = validate_plugin_package(Path(args.root))
    if errors:
        for error in errors:
            print(f"실패: {error}")
        return 1

    print("성공: analyze-repo-for-kubernetes Plugin package가 유효합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
