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

Put every discovery in exactly one fact-based outcome: `배포 대상 후보`, `저장소에 정의된 런타임 의존성`, `외부 런타임 의존성`, or `배포 대상 후보에서 제외한 항목`. Do not use a forced role label.

Do not create a workload merely because a package manifest exists. Require independently executable runtime behavior. Record the reason for excluding libraries, build-only packages and development utilities.

## Required Component Fields

- deployment-candidate name, execution form and repository-relative path
- reason it is a candidate or is excluded
- language, framework, runtime and version
- build command
- production startup command
- listener port or non-listener
- health behavior
- configuration names and 적용 시점
- writable or persistent paths
- inbound and outbound dependencies
- dependency execution location and supply or management boundary
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

- Are all independently executable deployment candidates represented?
- Are repository-defined runtime dependencies, external runtime dependencies and excluded items separated?
- Are development commands separated from production commands?
- Does the report separate repository launch definitions from operating-environment deployment evidence?
- Are ports confirmed from source or runtime configuration?
- Are unknown and conflicting facts preserved?
- Does every important fact have valid positive or absence evidence?
