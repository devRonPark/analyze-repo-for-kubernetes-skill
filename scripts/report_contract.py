from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT_PATH = ROOT / "contracts" / "report-contract-v1.json"
SCHEMA_VERSION = "report-contract/v1"
REQUIRED_MODES = ("summary", "detailed")


@dataclass(frozen=True)
class ReportSection:
    key: str
    heading: str
    renderer_type: str


@dataclass(frozen=True)
class ReportMode:
    name: str
    title: str
    sections: tuple[ReportSection, ...]

    def section(self, key: str) -> ReportSection:
        for section in self.sections:
            if section.key == key:
                return section
        raise ValueError(f"{self.name} mode에서 지원하지 않는 section입니다: {key}")


@dataclass(frozen=True)
class ReportContract:
    schema_version: str
    modes: Mapping[str, ReportMode]

    def mode(self, name: str) -> ReportMode:
        try:
            return self.modes[name]
        except KeyError as error:
            raise ValueError(f"지원하지 않는 report mode입니다: {name}") from error


def _non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}은 비어 있지 않은 string이어야 합니다")
    return value


def load_report_contract(path: Path = DEFAULT_CONTRACT_PATH) -> ReportContract:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("report contract root는 object여야 합니다")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"report contract schema_version은 {SCHEMA_VERSION}이어야 합니다")
    raw_modes = payload.get("modes")
    if not isinstance(raw_modes, dict):
        raise ValueError("report contract modes는 object여야 합니다")

    modes: dict[str, ReportMode] = {}
    for name in REQUIRED_MODES:
        raw_mode = raw_modes.get(name)
        if not isinstance(raw_mode, dict):
            raise ValueError(f"report contract에 {name} mode가 없습니다")
        title = _non_empty_string(raw_mode.get("title"), f"{name}.title")
        raw_sections = raw_mode.get("sections")
        if not isinstance(raw_sections, list) or not raw_sections:
            raise ValueError(f"{name}.sections는 비어 있지 않은 array여야 합니다")
        sections: list[ReportSection] = []
        keys: set[str] = set()
        headings: set[str] = set()
        for index, raw_section in enumerate(raw_sections):
            if not isinstance(raw_section, dict):
                raise ValueError(f"{name}.sections[{index}]는 object여야 합니다")
            key = _non_empty_string(raw_section.get("key"), f"{name}.sections[{index}].key")
            heading = _non_empty_string(raw_section.get("heading"), f"{name}.sections[{index}].heading")
            renderer_type = _non_empty_string(
                raw_section.get("renderer_type"),
                f"{name}.sections[{index}].renderer_type",
            )
            if not heading.startswith("## "):
                raise ValueError(f"{name}.sections[{index}].heading은 '## '로 시작해야 합니다")
            if key in keys or heading in headings:
                raise ValueError(f"{name} mode에 중복 section key 또는 heading이 있습니다")
            keys.add(key)
            headings.add(heading)
            sections.append(ReportSection(key, heading, renderer_type))
        modes[name] = ReportMode(name, title, tuple(sections))

    return ReportContract(SCHEMA_VERSION, MappingProxyType(modes))


def headings_for(mode: str) -> tuple[str, ...]:
    return tuple(section.heading for section in load_report_contract().mode(mode).sections)


def title_for(mode: str) -> str:
    return load_report_contract().mode(mode).title
