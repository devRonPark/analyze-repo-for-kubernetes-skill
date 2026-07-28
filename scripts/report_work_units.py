from __future__ import annotations

from dataclasses import dataclass

import report_contract
import report_records


@dataclass(frozen=True)
class AnalysisSnapshot:
    mode: str
    deployable_subject_ids: tuple[str, ...]
    relationship_edge_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkUnit:
    unit_id: str
    unit_type: str
    subject_id: str | None
    required_fields: tuple[str, ...]
    relationship_edge_id: str | None = None


@dataclass(frozen=True)
class Coverage:
    total_units: int
    completed_units: int
    missing_unit_ids: tuple[str, ...]
    missing_fields: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def rendering_ready(self) -> bool:
        return self.total_units == self.completed_units


def _field_ids(
    contract: report_contract.ReportContract, group: str
) -> tuple[str, ...]:
    return tuple(
        field.field_id for field in contract.fields_for(group) if field.required
    )


def build_work_units(
    contract: report_contract.ReportContract,
    snapshot: AnalysisSnapshot,
) -> tuple[WorkUnit, ...]:
    contract.mode(snapshot.mode)
    units = [
        WorkUnit(
            "global:scope",
            "global_scope",
            None,
            _field_ids(contract, "scope"),
        )
    ]
    for subject_id in sorted(set(snapshot.deployable_subject_ids)):
        prefix = f"component:{subject_id}"
        units.extend(
            (
                WorkUnit(
                    f"{prefix}:inventory",
                    "component_inventory",
                    subject_id,
                    ("execution_form",),
                ),
                WorkUnit(
                    f"{prefix}:runtime",
                    "component_runtime",
                    subject_id,
                    _field_ids(contract, "component_runtime"),
                ),
                WorkUnit(
                    f"{prefix}:configuration-state",
                    "component_configuration_state",
                    subject_id,
                    _field_ids(contract, "component_config_state"),
                ),
                WorkUnit(
                    f"{prefix}:kubernetes-input",
                    "component_kubernetes_input",
                    subject_id,
                    _field_ids(contract, "component_k8s_input"),
                ),
                WorkUnit(
                    f"{prefix}:minimum-input-gap",
                    "component_minimum_input_gap",
                    subject_id,
                    _field_ids(contract, "component_k8s_input"),
                ),
                WorkUnit(
                    f"{prefix}:deployment-evidence",
                    "component_deployment_evidence",
                    subject_id,
                    _field_ids(contract, "deployment_evidence"),
                ),
            )
        )
    for edge_id in sorted(set(snapshot.relationship_edge_ids)):
        units.append(
            WorkUnit(
                f"relationship:{edge_id}",
                "relationship",
                None,
                (),
                relationship_edge_id=edge_id,
            )
        )
    if snapshot.mode == "detailed":
        units.extend(
            (
                WorkUnit(
                    "global:configuration-detail",
                    "global_configuration_detail",
                    None,
                    (),
                ),
                WorkUnit(
                    "global:exclusions-and-blockers",
                    "global_exclusions_and_blockers",
                    None,
                    (),
                ),
            )
        )
    units.append(
        WorkUnit(
            "global:readiness",
            "global_readiness",
            None,
            _field_ids(contract, "readiness"),
        )
    )
    return tuple(sorted(units, key=lambda unit: unit.unit_id))


def calculate_coverage(
    units: tuple[WorkUnit, ...],
    records: report_records.ReportDocument,
) -> Coverage:
    fields_by_subject: dict[str, set[str]] = {}
    for claim in records.claims:
        fields_by_subject.setdefault(claim.subject_id, set()).add(claim.field)
    subject_kinds = {
        subject.subject_id: subject.kind for subject in records.subjects
    }
    scope_fields = {
        field
        for subject_id, fields in fields_by_subject.items()
        if subject_kinds.get(subject_id) == "scope"
        for field in fields
    }
    readiness_fields = {
        claim.field
        for claim in records.claims
        if claim.field in {"verdict", "reason", "supporting_evidence"}
    }
    relationship_ids = {
        relationship.edge_id for relationship in records.relationships
    }

    missing_units: list[str] = []
    missing_fields: list[tuple[str, tuple[str, ...]]] = []
    for unit in units:
        if unit.relationship_edge_id is not None:
            missing = (
                ()
                if unit.relationship_edge_id in relationship_ids
                else ("relationship",)
            )
        elif unit.unit_type == "global_scope":
            missing = tuple(
                field
                for field in unit.required_fields
                if field not in scope_fields
            )
        elif unit.unit_type == "global_readiness":
            missing = tuple(
                field
                for field in unit.required_fields
                if field not in readiness_fields
            )
        elif unit.subject_id is not None:
            present = fields_by_subject.get(unit.subject_id, set())
            missing = tuple(
                field
                for field in unit.required_fields
                if field not in present
            )
        else:
            missing = ()
        if missing:
            missing_units.append(unit.unit_id)
            missing_fields.append((unit.unit_id, missing))

    return Coverage(
        total_units=len(units),
        completed_units=len(units) - len(missing_units),
        missing_unit_ids=tuple(missing_units),
        missing_fields=tuple(missing_fields),
    )
