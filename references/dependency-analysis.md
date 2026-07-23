# Dependency Analysis

Represent dependencies as directed relationships from a logical source component to a target.

## Required Relationship Fields

- source component
- target component or external system
- dependency type
- protocol or mechanism
- endpoint or configuration name when known
- required or optional
- build-time or runtime
- 실행 위치
- evidence status and file locations

## 실행 위치 값

Use one of:

- 브라우저
- 서버 프로세스
- worker 프로세스
- scheduled/job 프로세스
- 빌드 파이프라인
- 배포 controller
- 사람/관리자
- 외부 시스템
- 미확인

The logical source and execution locus can differ. A static frontend component may logically depend on an API, while the actual network caller is the user's browser rather than the Nginx Pod.

## Dependency Types

Examples include HTTP, gRPC, SQL, message queue, cache, SMTP, object storage, filesystem, package import, generated client, and build artifact.

## Required Output

Produce both a dependency matrix and a text dependency graph. The two representations must agree. Separate build-time relationships from runtime relationships and do not treat package declarations alone as proof of runtime communication.
