from __future__ import annotations

from copy import deepcopy


TOOL_NAMES = (
    "report_session_start",
    "report_chunk_submit",
    "report_session_sync",
    "report_session_finalize",
)


def _string(description: str, **constraints: object) -> dict[str, object]:
    return {"type": "string", "description": description, **constraints}


def _integer(description: str, **constraints: object) -> dict[str, object]:
    return {"type": "integer", "description": description, **constraints}


def _object(
    description: str,
    properties: dict[str, object],
    required: tuple[str, ...],
) -> dict[str, object]:
    return {
        "type": "object",
        "description": description,
        "additionalProperties": False,
        "properties": properties,
        "required": list(required),
    }


SUBJECT = _object(
    "보고서에서 여러 claim이 공통으로 참조할 하나의 분석 대상이다.",
    {
        "subject_id": _string(
            "세션 안에서 안정적으로 재사용할 subject 식별자다.",
            minLength=1,
            maxLength=128,
        ),
        "kind": _string(
            "subject의 분석 분류다.",
            enum=[
                "deployable",
                "repository_dependency",
                "external_dependency",
                "configuration",
                "excluded",
            ],
        ),
        "display_name": _string(
            "최종 보고서에 표시할 이름이며 Markdown 문법을 포함하지 않는다.",
            minLength=1,
            maxLength=256,
        ),
    },
    ("subject_id", "kind", "display_name"),
)

CLAIM = _object(
    "최종 Markdown의 한 필드로 컴파일할 구조화된 claim이다.",
    {
        "claim_id": _string(
            "세션 안에서 중복되지 않는 claim 식별자다.",
            minLength=1,
            maxLength=160,
        ),
        "unit_id": _string(
            "현재 lease에서 이 claim이 채우는 work-unit 식별자다.",
            minLength=1,
        ),
        "section_key": _string(
            "claim이 속하는 report contract의 논리 섹션이다.",
            enum=[
                "scope",
                "candidate_inventory",
                "component_runtime",
                "component_config_state",
                "component_k8s_input",
                "component_gap",
                "deployment_evidence",
                "configuration_detail",
                "exclusion",
                "blocker",
                "readiness",
            ],
        ),
        "subject_id": _string(
            "claim의 주체 subject 식별자다.", maxLength=128
        ),
        "field": _string(
            "lease가 요구한 정확한 contract field ID다.",
            minLength=1,
            maxLength=128,
        ),
        "value": _string(
            "확인된 값 또는 미확인 설명이며 Markdown 문법을 포함하지 않는다.",
            maxLength=2000,
        ),
        "status": _string(
            "근거 상태다.",
            enum=[
                "confirmed",
                "inferred",
                "unknown",
                "conflicted",
                "not_applicable",
            ],
        ),
        "evidence": {
            "type": "array",
            "description": "repository-relative 근거 목록이다.",
            "maxItems": 8,
            "items": _string(
                "file:line, 검색(...) 또는 claim:<id> 근거다.",
                maxLength=512,
            ),
        },
        "reason": _string(
            "inferred 또는 conflicted 상태의 판단 이유다.",
            maxLength=1000,
        ),
    },
    (
        "claim_id",
        "unit_id",
        "section_key",
        "subject_id",
        "field",
        "value",
        "status",
        "evidence",
        "reason",
    ),
)

RELATIONSHIP_ATTRIBUTE = _object(
    "dependency relationship의 key와 값이다.",
    {
        "key": _string(
            "lease가 지정한 relationship field ID다.",
            minLength=1,
            maxLength=128,
        ),
        "value": _string(
            "Markdown 문법이 없는 relationship 속성 값이다.",
            maxLength=1000,
        ),
    },
    ("key", "value"),
)

RELATIONSHIP = _object(
    "Dependency matrix와 text graph를 생성할 방향성 edge다.",
    {
        "edge_id": _string(
            "세션 안에서 중복되지 않는 edge 식별자다.",
            minLength=1,
            maxLength=160,
        ),
        "unit_id": _string(
            "현재 lease의 relationship work-unit 식별자다.",
            minLength=1,
        ),
        "source_subject_id": _string(
            "dependency를 사용하는 deployable subject ID다.",
            minLength=1,
        ),
        "target_subject_id": _string(
            "사용되는 dependency subject ID다.", minLength=1
        ),
        "attributes": {
            "type": "array",
            "description": "dependency 속성 목록이다.",
            "minItems": 1,
            "maxItems": 12,
            "items": RELATIONSHIP_ATTRIBUTE,
        },
        "status": _string(
            "relationship 전체의 근거 상태다.",
            enum=["confirmed", "inferred", "unknown", "conflicted"],
        ),
        "evidence": {
            "type": "array",
            "description": "relationship의 repository-relative 근거다.",
            "minItems": 1,
            "maxItems": 8,
            "items": _string("file:line 또는 검색(...) 근거다.", maxLength=512),
        },
        "reason": _string(
            "inferred 또는 conflicted 상태의 판단 이유다.",
            maxLength=1000,
        ),
    },
    (
        "edge_id",
        "unit_id",
        "source_subject_id",
        "target_subject_id",
        "attributes",
        "status",
        "evidence",
        "reason",
    ),
)


def _tool(
    name: str, description: str, parameters: dict[str, object]
) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "strict": True,
            "parameters": parameters,
        },
    }


TOOLS = {
    "report_session_start": _tool(
        "report_session_start",
        "완료된 target과 analysis snapshot으로 보고서 세션을 시작한다.",
        _object(
            "보고서 세션을 재현 가능하게 시작하는 opaque 식별 정보다.",
            {
                "target_ref": _string(
                    "오케스트레이터가 제공한 opaque target 식별자다.",
                    minLength=1,
                    maxLength=4096,
                ),
                "target_sha256": _string(
                    "target metadata의 SHA-256이다.",
                    pattern="^[a-f0-9]{64}$",
                ),
                "analysis_snapshot_id": _string(
                    "완료된 analysis snapshot 바이트의 SHA-256이다.",
                    pattern="^[a-f0-9]{64}$",
                ),
                "idempotency_key": _string(
                    "동일 시작 요청의 재시도 키다.",
                    minLength=8,
                    maxLength=128,
                ),
            },
            (
                "target_ref",
                "target_sha256",
                "analysis_snapshot_id",
                "idempotency_key",
            ),
        ),
    ),
    "report_chunk_submit": _tool(
        "report_chunk_submit",
        "현재 lease가 허용한 bounded semantic records만 제출한다.",
        _object(
            "하나의 동적 보고서 record chunk다.",
            {
                "session_id": _string("보고서 session ID다.", minLength=1),
                "lease_id": _string("현재 active lease ID다.", minLength=1),
                "expected_state_version": _integer(
                    "stale write를 막는 state version이다.", minimum=0
                ),
                "idempotency_key": _string(
                    "동일 chunk 재시도 키다.",
                    minLength=8,
                    maxLength=128,
                ),
                "chunk_ordinal": _integer(
                    "lease 안의 0-based chunk 순번이다.", minimum=0
                ),
                "subject_declarations": {
                    "type": "array",
                    "description": "현재 chunk가 선언하는 subject다.",
                    "maxItems": 32,
                    "items": SUBJECT,
                },
                "claims": {
                    "type": "array",
                    "description": "현재 lease가 요구한 claim이다.",
                    "maxItems": 48,
                    "items": CLAIM,
                },
                "relationships": {
                    "type": "array",
                    "description": "현재 lease가 요구한 relationship이다.",
                    "maxItems": 16,
                    "items": RELATIONSHIP,
                },
                "continuation": _string(
                    "현재 lease의 chunk 지속 여부다.",
                    enum=["more_for_same_lease", "lease_complete"],
                ),
            },
            (
                "session_id",
                "lease_id",
                "expected_state_version",
                "idempotency_key",
                "chunk_ordinal",
                "subject_declarations",
                "claims",
                "relationships",
                "continuation",
            ),
        ),
    ),
    "report_session_sync": _tool(
        "report_session_sync",
        "authoritative session 상태와 다음 행동을 다시 가져온다.",
        _object(
            "세션을 바꾸지 않는 read-only 동기화 요청이다.",
            {
                "session_id": _string("동기화할 session ID다.", minLength=1),
                "known_state_version": _integer(
                    "마지막으로 확인한 state version이다.", minimum=0
                ),
                "request_id": _string(
                    "상태를 바꾸지 않는 추적 ID다.",
                    minLength=8,
                    maxLength=128,
                ),
            },
            ("session_id", "known_state_version", "request_id"),
        ),
    ),
    "report_session_finalize": _tool(
        "report_session_finalize",
        "coverage 완료 후 결정론적 조립과 검증을 요청한다.",
        _object(
            "rendering-ready session의 최종화 요청이다.",
            {
                "session_id": _string("최종화할 session ID다.", minLength=1),
                "expected_state_version": _integer(
                    "최신 state version이다.", minimum=0
                ),
                "idempotency_key": _string(
                    "최종화 재시도 키다.",
                    minLength=8,
                    maxLength=128,
                ),
            },
            (
                "session_id",
                "expected_state_version",
                "idempotency_key",
            ),
        ),
    ),
}


def tool_names() -> tuple[str, ...]:
    return TOOL_NAMES


def schema_for(name: str) -> dict[str, object]:
    try:
        return deepcopy(TOOLS[name])
    except KeyError as error:
        raise ValueError(f"unknown tool: {name}") from error
