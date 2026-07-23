# Repository Analysis Checklist

## Component Discovery

For each candidate, decide whether it is:

- API or web application
- static frontend build
- background worker
- scheduled task
- one-time initialization or migration job
- shared library or generated client
- development-only utility

Do not create a workload merely because a package manifest exists. Require independently executable runtime behavior. Record the reason for excluding libraries, build-only packages and development utilities.

## Required Component Fields

- component name and repository-relative path
- purpose, type and deployable status
- language, framework, runtime and version
- build command
- production startup command
- listener port or non-listener
- health behavior
- configuration names and 적용 시점
- writable or persistent paths
- inbound and outbound dependencies
- 외부 관계의 실행 위치
- containerization classification
- evidence status and `file:line` or `검색(...)` evidence

## Containerization Classification

Use exactly one:

- 기존 컨테이너 정의 있음
- 대체 이미지 빌드 방식
- 컨테이너화 필요
- 컨테이너화 불필요
- 미확인

## Completion Questions

- Are all independently executable components represented?
- Are excluded libraries and utilities explained?
- Are development commands separated from production commands?
- Are ports confirmed from source or runtime configuration?
- Are unknown and conflicting facts preserved?
- Does every important fact have valid positive or absence evidence?
