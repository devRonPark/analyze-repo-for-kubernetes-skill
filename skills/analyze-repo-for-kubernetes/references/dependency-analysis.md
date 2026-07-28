# Dependency Analysis

Represent each dependency as a directed relationship from a logical source component to a target component or external system.

## Required Relationship Fields

- source component
- target component or external system
- dependency type
- protocol or mechanism
- endpoint or configuration name when known
- 기능 실행에 필요한지
- 확인된 저장소 기동 정의에서 사용되는지
- 공급 또는 관리 경계(저장소에 배포 정의 있음, 외부 관리로 참조, 미확인)
- build-time or runtime
- 실행 위치
- evidence status and evidence

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

The logical source and execution locus can differ. A static frontend may logically depend on an API while the actual network caller is the user's browser rather than the frontend Pod.

## Dependency Types

Examples include HTTP, gRPC, SQL, message queue, cache, SMTP, object storage, filesystem, package import, generated client and build artifact.

## Evidence Rules

- Do not treat a dependency declaration alone as proof of runtime communication.
- Use `file:line` for existing relationships.
- Use `검색(scope=..., pattern=..., result=없음)` only for verified absence.
- Preserve conflicting endpoints, ports or protocols with both sources.

## Required Output by Mode

- **summary:** Produce a concise relationship card or text dependency graph.
- **detailed:** Produce both a dependency matrix and a text dependency graph. Make the two representations agree and separate build-time from runtime relationships.
