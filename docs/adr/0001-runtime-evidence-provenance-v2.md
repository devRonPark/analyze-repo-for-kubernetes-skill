# ADR-0001: Runtime evidence provenance을 위한 v2 schema

## 상태

채택됨

## 맥락

#36은 언어별 runtime-signal extractor가 만든 evidence와 기존 universal scanner
및 pattern pack이 만든 evidence를 구분해야 한다. 기존
`repository-evidence/v1`에는 이 수집 경로를 분석 상태와 독립적으로 표현하는
필드가 없다.

수집 경로를 `status` 또는 extractor 이름만으로 추론하면, 후속 분석이 source에서
직접 추출한 사실과 pattern 기반 단서를 안정적으로 구분할 수 없다. 새 필드는
stable evidence ID와 per-file cache compatibility에도 영향을 준다.

## 결정

새 scanner output은 `repository-evidence/v2`를 사용한다. 모든 evidence record는
최상위 `provenance`를 가지며 `EXTRACTED`와 `INFERRED`를 사용한다. `status`는
분석 확실성 메타데이터로 유지하며 provenance를 대체하지 않는다.

v2 stable identity에는 provenance를 포함한다. Validator는 기존 v1 artifact를
historical identity 규칙으로 읽고 검증하는 호환 경로를 유지하지만, 새 scanner는
v1을 출력하지 않는다.

## 결과

- 후속 triage가 runtime extractor 결과와 pattern-derived evidence를 명시적으로
  구분할 수 있다.
- v1 artifact 소비자는 validator에서 계속 검증할 수 있다.
- schema, cache identity, validator, fixtures는 v2와 v1 호환 경로를 함께
  검증해야 한다.
