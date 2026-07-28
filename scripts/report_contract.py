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
REQUIRED_FIELD_GROUPS = (
    "scope",
    "component_runtime",
    "component_config_state",
    "component_k8s_input",
    "deployment_evidence",
    "readiness",
)
FIELD_RENDERERS = frozenset(("text", "code", "evidence", "verdict"))


@dataclass(frozen=True)
class ReportField:
    field_id: str
    label: str
    required: bool
    repeatable: bool
    renderer: str


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
    field_groups: Mapping[str, tuple[ReportField, ...]]

    def mode(self, name: str) -> ReportMode:
        try:
            return self.modes[name]
        except KeyError as error:
            raise ValueError(f"지원하지 않는 report mode입니다: {name}") from error

    def fields_for(self, group: str) -> tuple[ReportField, ...]:
        try:
            return self.field_groups[group]
        except KeyError as error:
            raise ValueError(f"지원하지 않는 field group입니다: {group}") from error

    def field(self, group: str, field_id: str) -> ReportField:
        for field in self.fields_for(group):
            if field.field_id == field_id:
                return field
        raise ValueError(f"{group} group에서 지원하지 않는 field입니다: {field_id}")


def _non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}은 비어 있지 않은 string이어야 합니다")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label}은 boolean이어야 합니다")
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

    raw_field_groups = payload.get("field_groups")
    if not isinstance(raw_field_groups, dict):
        raise ValueError("report contract field_groups는 object여야 합니다")
    field_groups: dict[str, tuple[ReportField, ...]] = {}
    for group in REQUIRED_FIELD_GROUPS:
        raw_fields = raw_field_groups.get(group)
        if not isinstance(raw_fields, list) or not raw_fields:
            raise ValueError(f"report contract에 {group} field group이 없습니다")
        fields: list[ReportField] = []
        field_ids: set[str] = set()
        for index, raw_field in enumerate(raw_fields):
            if not isinstance(raw_field, dict):
                raise ValueError(f"{group}[{index}] field는 object여야 합니다")
            field_id = _non_empty_string(
                raw_field.get("field_id"), f"{group}[{index}].field_id"
            )
            label = _non_empty_string(raw_field.get("label"), f"{group}[{index}].label")
            required = _boolean(
                raw_field.get("required"), f"{group}[{index}].required"
            )
            repeatable = _boolean(
                raw_field.get("repeatable"), f"{group}[{index}].repeatable"
            )
            renderer = _non_empty_string(
                raw_field.get("renderer"), f"{group}[{index}].renderer"
            )
            if renderer not in FIELD_RENDERERS:
                raise ValueError(
                    f"{group}[{index}].renderer가 지원되지 않습니다: {renderer}"
                )
            if field_id in field_ids:
                raise ValueError(f"{group} group에 중복 field ID가 있습니다: {field_id}")
            field_ids.add(field_id)
            fields.append(
                ReportField(field_id, label, required, repeatable, renderer)
            )
        field_groups[group] = tuple(fields)

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

    return ReportContract(
        SCHEMA_VERSION,
        MappingProxyType(modes),
        MappingProxyType(field_groups),
    )


def headings_for(mode: str) -> tuple[str, ...]:
    return tuple(section.heading for section in load_report_contract().mode(mode).sections)


def title_for(mode: str) -> str:
    return load_report_contract().mode(mode).title
