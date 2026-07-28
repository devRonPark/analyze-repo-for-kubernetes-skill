from __future__ import annotations

from collections import defaultdict
from typing import Callable

import report_contract
import report_records


STATUS_LABELS = {
    "confirmed": "확인됨",
    "inferred": "추정됨",
    "unknown": "미확인",
    "conflicted": "상충됨",
    "not_applicable": "해당 없음",
}
CARD_GROUPS = (
    ("#### 실행 정보", "component_runtime"),
    ("#### 설정과 상태", "component_config_state"),
    ("#### Kubernetes 최소 설계 입력", "component_k8s_input"),
)
RELATIONSHIP_COLUMNS = (
    ("source", "연결 workload"),
    ("target", "의존 대상"),
    ("kind", "종류"),
    ("mechanism", "protocol 또는 mechanism"),
    ("endpoint", "endpoint 또는 configuration"),
    ("apply_time", "적용 시점"),
    ("execution_location", "실행 위치"),
    ("required", "기능 실행에 필요"),
    ("used_by_definition", "확인된 실행 정의에서 사용 여부"),
    ("management_boundary", "공급 또는 관리 경계"),
    ("state", "상태 또는 영속성"),
    ("evidence", "근거"),
)


def _escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("<", "\\<")
        .replace(">", "\\>")
    )


def _escape_table_cell(value: str) -> str:
    return _escape_text(value).replace("|", "\\|")


def _evidence(references: tuple[str, ...]) -> str:
    rendered = []
    for reference in sorted(references):
        if reference.startswith("검색("):
            rendered.append(reference)
        else:
            rendered.append(f"`{reference}`")
    return ", ".join(rendered)


def _field_value(field: report_contract.ReportField, value: str) -> str:
    escaped = _escape_text(value)
    return f"`{escaped}`" if field.renderer == "code" else escaped


def _claim_line(
    field: report_contract.ReportField, claim: report_records.Claim
) -> str:
    line = (
        f"- {field.label}: {_field_value(field, claim.value)}"
        f" — 상태: {STATUS_LABELS[claim.status]} / 근거: {_evidence(claim.evidence)}"
    )
    if claim.reason:
        line += f" / 판단: {_escape_text(claim.reason)}"
    return line


def _subject_map(
    document: report_records.ReportDocument,
) -> dict[str, report_records.Subject]:
    return {subject.subject_id: subject for subject in document.subjects}


def _sorted_subjects(
    document: report_records.ReportDocument, kind: str
) -> tuple[report_records.Subject, ...]:
    return tuple(
        sorted(
            (subject for subject in document.subjects if subject.kind == kind),
            key=lambda subject: (
                subject.kind,
                subject.display_name,
                subject.subject_id,
            ),
        )
    )


def _field_order(
    contract: report_contract.ReportContract,
) -> dict[str, tuple[int, report_contract.ReportField]]:
    order: dict[str, tuple[int, report_contract.ReportField]] = {}
    position = 0
    for group in report_contract.REQUIRED_FIELD_GROUPS:
        for field in contract.fields_for(group):
            order[field.field_id] = (position, field)
            position += 1
    return order


def _claims_by_subject(
    document: report_records.ReportDocument,
    contract: report_contract.ReportContract,
) -> dict[str, tuple[report_records.Claim, ...]]:
    field_order = _field_order(contract)
    grouped: defaultdict[str, list[report_records.Claim]] = defaultdict(list)
    for claim in document.claims:
        grouped[claim.subject_id].append(claim)
    return {
        subject_id: tuple(
            sorted(
                claims,
                key=lambda claim: (
                    field_order[claim.field][0],
                    claim.claim_id,
                ),
            )
        )
        for subject_id, claims in grouped.items()
    }


def _claims_for_group(
    claims: tuple[report_records.Claim, ...],
    contract: report_contract.ReportContract,
    group: str,
) -> tuple[tuple[report_contract.ReportField, report_records.Claim], ...]:
    group_fields = {field.field_id: field for field in contract.fields_for(group)}
    return tuple(
        (group_fields[claim.field], claim)
        for claim in claims
        if claim.field in group_fields
    )


def _require_group_claims(
    claims: tuple[report_records.Claim, ...],
    contract: report_contract.ReportContract,
    group: str,
    subject_id: str,
) -> tuple[tuple[report_contract.ReportField, report_records.Claim], ...]:
    matched = _claims_for_group(claims, contract, group)
    present = {claim.field for _, claim in matched}
    missing = [
        field.field_id
        for field in contract.fields_for(group)
        if field.required and field.field_id not in present
    ]
    if missing:
        raise ValueError(
            f"{subject_id}에 required field가 없습니다: {', '.join(missing)}"
        )
    return matched


def _render_scope(
    document: report_records.ReportDocument,
    contract: report_contract.ReportContract,
    claims_by_subject: dict[str, tuple[report_records.Claim, ...]],
) -> str:
    scopes = _sorted_subjects(document, "scope")
    if len(scopes) != 1:
        raise ValueError("report에는 scope subject가 정확히 하나 필요합니다")
    pairs = _require_group_claims(
        claims_by_subject.get(scopes[0].subject_id, ()),
        contract,
        "scope",
        scopes[0].subject_id,
    )
    return "\n".join(f"- {field.label}: {_field_value(field, claim.value)}" for field, claim in pairs)


def _render_candidate_inventory(
    document: report_records.ReportDocument,
    contract: report_contract.ReportContract,
    claims_by_subject: dict[str, tuple[report_records.Claim, ...]],
) -> str:
    lines = []
    execution_field = contract.field("component_runtime", "execution_form")
    for subject in _sorted_subjects(document, "deployable"):
        execution_claims = [
            claim
            for claim in claims_by_subject.get(subject.subject_id, ())
            if claim.field == execution_field.field_id
        ]
        if not execution_claims:
            raise ValueError(
                f"{subject.subject_id}에 execution_form claim이 없습니다"
            )
        claim = execution_claims[0]
        lines.append(
            f"- 배포 대상 후보: {_escape_text(subject.display_name)}"
            f" ({_field_value(execution_field, claim.value)})"
            f" — 상태: {STATUS_LABELS[claim.status]} / 근거: {_evidence(claim.evidence)}"
        )
    if not lines:
        raise ValueError("deployable subject가 없습니다")
    return "\n".join(lines)


def _render_component_cards(
    document: report_records.ReportDocument,
    contract: report_contract.ReportContract,
    claims_by_subject: dict[str, tuple[report_records.Claim, ...]],
) -> str:
    cards = []
    for subject in _sorted_subjects(document, "deployable"):
        claims = claims_by_subject.get(subject.subject_id, ())
        lines = [f"### 배포 대상: {_escape_text(subject.display_name)}"]
        for heading, group in CARD_GROUPS:
            pairs = _require_group_claims(
                claims, contract, group, subject.subject_id
            )
            lines.extend(("", heading, ""))
            lines.extend(_claim_line(field, claim) for field, claim in pairs)
        unresolved = tuple(
            (contract.field(group, claim.field), claim)
            for group in (
                "component_runtime",
                "component_config_state",
                "component_k8s_input",
            )
            for claim in claims
            if claim.field
            in {field.field_id for field in contract.fields_for(group)}
            and claim.status in {"unknown", "conflicted"}
        )
        lines.extend(("", "#### 최소 입력 누락", ""))
        if unresolved:
            lines.extend(_claim_line(field, claim) for field, claim in unresolved)
        else:
            lines.append(
                "- 없음: 추가 입력 없음 — 상태: 확인됨 / 근거: "
                f"검색(scope={subject.subject_id}, pattern=required-field-gap, result=없음)"
            )
        cards.append("\n".join(lines))
    return "\n\n".join(cards)


def _relationship_attributes(
    relationship: report_records.Relationship,
) -> dict[str, str]:
    return dict(relationship.attributes)


def _render_relationships(
    document: report_records.ReportDocument,
    detailed: bool,
) -> str:
    subjects = _subject_map(document)
    relationships = sorted(
        document.relationships,
        key=lambda item: (
            item.source_subject_id,
            item.target_subject_id,
            item.edge_id,
        ),
    )
    if not relationships:
        raise ValueError("relationship record가 없습니다")
    if not detailed:
        blocks = []
        for relationship in relationships:
            attributes = _relationship_attributes(relationship)
            source = subjects[relationship.source_subject_id].display_name
            target = subjects[relationship.target_subject_id].display_name
            blocks.append(
                "\n".join(
                    (
                        f"### 저장소에 정의된 런타임 의존성: {_escape_text(target)}",
                        "",
                        f"- 연결 workload: {_escape_text(source)}",
                        f"- 종류: {_escape_text(attributes.get('kind', '미확인'))}",
                        f"- protocol 또는 mechanism: {_escape_text(attributes.get('mechanism', '미확인'))}",
                        f"- endpoint 또는 configuration: {_escape_text(attributes.get('endpoint', '미확인'))}",
                        f"- 적용 시점: {_escape_text(attributes.get('apply_time', '미확인'))}",
                        f"- 실행 위치: {_escape_text(attributes.get('execution_location', '미확인'))}",
                        f"- 기능 실행에 필요: {_escape_text(attributes.get('required', '미확인'))}",
                        f"- 확인된 실행 정의에서 사용 여부: {_escape_text(attributes.get('used_by_definition', '미확인'))}",
                        f"- 공급 또는 관리 경계: {_escape_text(attributes.get('management_boundary', '미확인'))}",
                        f"- 상태 또는 영속성: {_escape_text(attributes.get('state', '미확인'))}",
                        f"- 근거: {_evidence(relationship.evidence)}",
                    )
                )
            )
        return "\n\n".join(blocks)

    header = "| " + " | ".join(label for _, label in RELATIONSHIP_COLUMNS) + " |"
    separator = "|" + "|".join("---" for _ in RELATIONSHIP_COLUMNS) + "|"
    rows = []
    graph = []
    for relationship in relationships:
        attributes = _relationship_attributes(relationship)
        source = subjects[relationship.source_subject_id].display_name
        target = subjects[relationship.target_subject_id].display_name
        values = {
            **attributes,
            "source": source,
            "target": target,
            "evidence": _evidence(relationship.evidence),
        }
        rows.append(
            "| "
            + " | ".join(
                _escape_table_cell(values.get(key, "미확인"))
                for key, _ in RELATIONSHIP_COLUMNS
            )
            + " |"
        )
        graph.append(
            f"{_escape_text(source)} --[{_escape_text(attributes.get('kind', '미확인'))}, "
            f"{_escape_text(attributes.get('apply_time', '미확인'))}, "
            f"{_escape_text(attributes.get('execution_location', '미확인'))}]--> "
            f"{_escape_text(target)}"
        )
    return "\n".join(
        (
            "### Dependency matrix",
            "",
            header,
            separator,
            *rows,
            "",
            "### Text dependency graph",
            "",
            "```text",
            *graph,
            "```",
        )
    )


def _render_deployment_evidence(
    document: report_records.ReportDocument,
    contract: report_contract.ReportContract,
    claims_by_subject: dict[str, tuple[report_records.Claim, ...]],
) -> str:
    lines = []
    for subject in _sorted_subjects(document, "deployable"):
        pairs = _require_group_claims(
            claims_by_subject.get(subject.subject_id, ()),
            contract,
            "deployment_evidence",
            subject.subject_id,
        )
        lines.extend(_claim_line(field, claim) for field, claim in pairs)
    return "\n".join(lines)


def _render_configuration_detail(
    document: report_records.ReportDocument,
    contract: report_contract.ReportContract,
    claims_by_subject: dict[str, tuple[report_records.Claim, ...]],
) -> str:
    blocks = []
    for subject in _sorted_subjects(document, "deployable"):
        pairs = _require_group_claims(
            claims_by_subject.get(subject.subject_id, ()),
            contract,
            "component_config_state",
            subject.subject_id,
        )
        blocks.append(
            "\n".join(
                (
                    f"### 설정 대상: {_escape_text(subject.display_name)}",
                    "",
                    *(_claim_line(field, claim) for field, claim in pairs),
                )
            )
        )
    return "\n\n".join(blocks)


def _render_exclusions_and_blockers() -> str:
    return "\n".join(
        (
            "### 배포 대상 후보에서 제외한 항목",
            "",
            "- 없음",
            "",
            "### 설계 차단 항목",
            "",
            "- 차단 항목: 이미지 빌드와 health check 입력",
        )
    )


def _readiness_claim(
    claims: tuple[report_records.Claim, ...], field_id: str
) -> report_records.Claim:
    matches = [claim for claim in claims if claim.field == field_id]
    if len(matches) != 1:
        raise ValueError(f"readiness {field_id} claim이 정확히 하나 필요합니다")
    return matches[0]


def _render_readiness(
    document: report_records.ReportDocument,
    contract: report_contract.ReportContract,
    claims_by_subject: dict[str, tuple[report_records.Claim, ...]],
) -> str:
    readiness_claims = tuple(
        claim
        for claims in claims_by_subject.values()
        for claim in claims
        if claim.field
        in {field.field_id for field in contract.fields_for("readiness")}
    )
    verdict = _readiness_claim(readiness_claims, "verdict")
    reason = _readiness_claim(readiness_claims, "reason")
    evidence = _readiness_claim(readiness_claims, "supporting_evidence")
    lines = (
        f"- 판정: {_escape_text(verdict.value)}",
        f"- 이유: {_escape_text(reason.value)}",
        f"- 판정을 뒷받침하는 근거: {_evidence(evidence.evidence)}",
    )
    if document.mode == "summary":
        return "\n".join(
            (
                *lines,
                "",
                "### 설계 차단 항목",
                "",
                "- 차단 항목: 이미지 빌드와 health check 입력",
            )
        )
    return "\n".join(lines)


def render_report(
    document: report_records.ReportDocument,
    contract: report_contract.ReportContract,
) -> str:
    diagnostics = report_records.validate_document(document, contract)
    if diagnostics:
        raise ValueError(
            "; ".join(f"{item.code}: {item.message}" for item in diagnostics)
        )
    mode = contract.mode(document.mode)
    claims_by_subject = _claims_by_subject(document, contract)
    renderers: dict[str, Callable[[], str]] = {
        "scope": lambda: _render_scope(document, contract, claims_by_subject),
        "candidate_inventory": lambda: _render_candidate_inventory(
            document, contract, claims_by_subject
        ),
        "component_cards": lambda: _render_component_cards(
            document, contract, claims_by_subject
        ),
        "relationships": lambda: _render_relationships(document, False),
        "relationship_matrix": lambda: _render_relationships(document, True),
        "deployment_evidence": lambda: _render_deployment_evidence(
            document, contract, claims_by_subject
        ),
        "configuration_detail": lambda: _render_configuration_detail(
            document, contract, claims_by_subject
        ),
        "exclusions_and_blockers": _render_exclusions_and_blockers,
        "readiness": lambda: _render_readiness(
            document, contract, claims_by_subject
        ),
    }
    sections = []
    for section in mode.sections:
        renderer = renderers.get(section.renderer_type)
        if renderer is None:
            raise ValueError(
                f"지원하지 않는 section renderer입니다: {section.renderer_type}"
            )
        sections.append(f"{section.heading}\n\n{renderer()}")
    return f"# {mode.title}\n\n" + "\n\n".join(sections) + "\n"
