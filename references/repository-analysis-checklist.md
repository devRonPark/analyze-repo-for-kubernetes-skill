# Repository Analysis Checklist

## Component Discovery

For each candidate directory, decide whether it is:

- API or web application
- static frontend build
- background worker
- scheduled task
- one-time initialization or migration job
- shared library or generated client
- development-only utility

Do not create a workload for a package merely because it has a manifest. Require an independently executable runtime behavior.

## Required Component Fields

- component name and path
- purpose and deployable status
- language, framework, runtime, and version
- build command
- production startup command
- listener port or no listener
- health endpoint
- 설정 이름과 적용 시점
- writable or persistent paths
- inbound and outbound dependencies
- 외부 관계의 실행 위치
- containerization classification
- evidence status and repository-relative `file:line` locations for every field

## Containerization Classification

Use exactly one:

- 기존 컨테이너 정의 있음
- 대체 이미지 빌드 방식
- 컨테이너화 필요
- 컨테이너화 불필요
- 미확인

## Completion Questions

- Are all independently executable components represented?
- Are libraries excluded from workloads?
- Are development commands separated from production commands?
- Are ports confirmed from source or runtime configuration?
- 미확인 사실을 미확인으로 표시했는가?
- 미확인과 상충됨을 포함한 모든 중요한 발견 사항에 확인한 `file:line` 위치가 하나 이상 있는가?
