#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


COMPARISON_FIELDS = [
    "workload_candidates",
    "workload_kinds",
    "repository_defined_runtime_dependencies",
    "external_runtime_dependencies",
    "excluded_candidates",
    "repository_launch_definitions",
    "target_environment_baseline",
    "design_input_verdict",
]


def normalize_markdown(text: str) -> dict[str, Any]:
    candidates, candidate_kinds = _workload_candidates(text)
    workload_kinds = dict(candidate_kinds)
    workload_kinds.update(_component_workload_kinds(text))
    return {
        "workload_candidates": candidates,
        "workload_kinds": {name: workload_kinds[name] for name in candidates if name in workload_kinds},
        "repository_defined_runtime_dependencies": _named_heading_values(
            text,
            "저장소에 정의된 런타임 의존성",
        ),
        "external_runtime_dependencies": _named_heading_values(text, "외부 런타임 의존성"),
        "excluded_candidates": _excluded_candidates(text),
        "repository_launch_definitions": _comma_values(_line_value(text, "저장소에서 확인한 기동 정의")),
        "production_startup_commands": _component_line_values(text, "운영 기동 명령"),
        "listener_ports": _component_comma_values(text, "수신 포트"),
        "target_environment_baseline": _line_value(text, "운영 환경 배포 기준 구성") or "미확인",
        "design_input_verdict": _line_value(text, "판정"),
    }


def _workload_candidates(text: str) -> tuple[list[str], dict[str, str]]:
    candidates: list[str] = []
    kinds: dict[str, str] = {}
    for raw_value in _bullet_values(text, "배포 대상 후보"):
        name, kind = _name_and_parenthetical_kind(raw_value)
        if name and name not in candidates:
            candidates.append(name)
        if name and kind:
            kinds[name] = kind
    return candidates, kinds


def _component_workload_kinds(text: str) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for name, card in _component_sections(text):
        kind = _line_value(card, "실행 형태")
        if kind:
            kinds[name] = kind
    return kinds


def _component_line_values(text: str, key: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for name, card in _component_sections(text):
        value = _line_value(card, key)
        if value and value not in {"미확인", "해당 없음", "없음"}:
            values[name] = value
    return values


def _component_comma_values(text: str, key: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for name, card in _component_sections(text):
        parts = [
            value
            for value in _comma_values(_line_value(card, key))
            if value not in {"미확인", "해당 없음", "없음"}
        ]
        if parts:
            values[name] = parts
    return values


def _component_sections(text: str) -> list[tuple[str, str]]:
    headings = list(re.finditer(r"(?m)^### 배포 대상:\s*(\S+)", text))
    sections: list[tuple[str, str]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        next_section = text.find("\n## ", heading.end())
        if next_section != -1 and next_section < end:
            end = next_section
        sections.append((heading.group(1), text[heading.end():end]))
    return sections


def _named_heading_values(text: str, label: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(rf"(?m)^### {re.escape(label)}:\s*(.+)$", text):
        raw_value = _clean_value(match.group(1))
        if not raw_value or raw_value == "없음":
            continue
        for value in _comma_values(raw_value):
            if value not in values:
                values.append(value)
    return values


def _excluded_candidates(text: str) -> list[str]:
    values: list[str] = []
    section = _section_after_heading(text, "### 배포 대상 후보에서 제외한 항목")
    for raw_value in _bullet_values(section, "제외 항목"):
        for value in _comma_values(raw_value):
            if value != "없음" and value not in values:
                values.append(value)
    for raw_value in _bullet_values(section, "없음"):
        if raw_value and raw_value != "제외 항목 없음":
            values.append(raw_value)
    return values


def _bullet_values(text: str, key: str) -> list[str]:
    values: list[str] = []
    prefix = f"- {key}:"
    for line in text.splitlines():
        if line.startswith(prefix):
            values.append(_clean_value(line[len(prefix):].strip()))
    return values


def _line_value(text: str, key: str) -> str:
    values = _bullet_values(text, key)
    return values[-1] if values else ""


def _clean_value(value: str) -> str:
    value = value.split(" — 상태:", 1)[0].strip()
    value = value.split(" / 근거:", 1)[0].strip()
    return value


def _comma_values(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _name_and_parenthetical_kind(value: str) -> tuple[str, str]:
    match = re.match(r"(?P<name>\S+)(?:\s*\((?P<kind>[^)]+)\))?", value)
    if not match:
        return "", ""
    return match.group("name"), match.group("kind") or ""


def _section_after_heading(text: str, heading: str) -> str:
    start = text.find(heading)
    if start == -1:
        return ""
    end = text.find("\n### ", start + len(heading))
    next_top = text.find("\n## ", start + len(heading))
    candidates = [position for position in [end, next_top] if position != -1]
    return text[start:min(candidates) if candidates else len(text)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize a generated Kubernetes design-input report.")
    parser.add_argument("report", type=Path, help="Markdown report path")
    parser.add_argument("--output", type=Path, help="Write normalized JSON to this path")
    args = parser.parse_args()

    normalized = normalize_markdown(args.report.read_text(encoding="utf-8"))
    output = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
