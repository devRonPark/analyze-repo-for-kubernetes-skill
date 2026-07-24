# Repository Analysis Workflow

## 1. Resolve Target

Apply the Target Resolution Gate before repository discovery. Confirm the remote Git URL, local checkout or source archive, read-only access method, revision and analyzed subdirectory. For remote Git authentication or source archives, read [remote-git-access.md](remote-git-access.md).

## 2. Select Output Mode

Use summary by default. Use detailed only when the user explicitly requests a full, exhaustive or detailed assessment.

## 3. Inventory High-Signal Files

First inspect only manifests and lockfiles, deployment manifests, container definitions, environment configuration, runtime entrypoints, and DB or broker configuration. Use CI workflows, logs, README, deployment documentation, migrations and tests only as a second-pass supplement when a first-pass finding needs clarification.

Exclude generated output, dependency caches, vendored code and binary assets unless directly relevant. Do not follow symlinks outside the analysis root.

## 4. Identify Analysis Outcomes

Separate findings into four outcomes: `배포 대상 후보`, `저장소에 정의된 런타임 의존성`, `외부 런타임 의존성`, and `배포 대상 후보에서 제외한 항목`. A migration is first evaluated as a one-time job candidate; libraries, generated clients and development-only utilities are excluded with a reason.

## 5. Confirm Repository Launch Definitions

Record confirmed Compose services, scripts, entrypoints and their included processes as repository launch definitions. They prove executable behavior only; they do not establish an operating-environment deployment baseline. Do not infer that a package is a deployment target merely from its manifest.

## 6. Confirm Operating-Environment Deployment Evidence

Separate confirmed operating-environment deployment declarations (Helm, Kustomize, manifests, GitOps or release CI) from repository launch definitions. If the repository has no such declaration, record `미확인` with an absence search; never turn a local Compose or README example into an operating-environment baseline.

## 7. Determine Build and Runtime

For every deployable component, identify build command, production startup command, runtime and version, port or non-listener, health behavior, writable paths and containerization status.

A missing Dockerfile is a finding, not an analysis failure.

## 8. Analyze Configuration and Dependencies

Classify major configuration by 적용 시점. Map directed dependencies and record dependency type, timing, 실행 위치, `기능 실행에 필요`, `확인된 실행 정의에서 사용 여부`, and `공급 또는 관리 경계`. Keep source runtime behavior separate from operating-environment deployment evidence.

## 9. Resolve Evidence

Classify findings as 확인됨, 추정됨, 미확인 or 상충됨. Use repository-relative `file:line` evidence for existing facts and `검색(scope=..., pattern=..., result=없음)` for verified absence. Preserve conflicts and never invent a line citation.

## 10. Build Deployment-Candidate Briefings

Create one briefing card per deployment candidate. Separate source-backed values from inferred Kubernetes candidates. Put unresolved required values in 최소 입력 누락. Include termination/recovery, observable signals and state/persistence only when the repository provides evidence.

## 11. Finish Through Completion Gate

Confirm scope, candidate and dependency boundaries, evidence, operating-environment deployment evidence, missing inputs, secret redaction and exactly one design-input verdict before completing the report. Every `추가 정보 필요` verdict must identify a verified blocker category and impact scope.
