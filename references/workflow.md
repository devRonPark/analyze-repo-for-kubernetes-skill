# Repository Analysis Workflow

## 1. Resolve Target

Apply the Target Resolution Gate before repository discovery. Confirm the Repository URL or Local path, read-only access method, revision and analyzed subdirectory.

## 2. Select Output Mode

Use summary by default. Use detailed only when the user explicitly requests a full, exhaustive or detailed assessment.

## 3. Inventory High-Signal Files

Inspect directory structure, package manifests, lockfiles, build files, runtime entrypoints, Compose files, CI workflows, deployment documentation, environment examples, migrations and tests.

Exclude generated output, dependency caches, vendored code and binary assets unless directly relevant. Do not follow symlinks outside the analysis root.

## 4. Identify Components

Separate independently executable applications, APIs, static frontends, workers, scheduled jobs and one-time jobs from libraries, generated clients and development-only utilities. Record why a non-deployable candidate was excluded.

## 5. Determine Build and Runtime

For every deployable component, identify build command, production startup command, runtime and version, port or non-listener, health behavior, writable paths and containerization status.

A missing Dockerfile is a finding, not an analysis failure.

## 6. Analyze Configuration and Dependencies

Classify major configuration by 적용 시점. Map directed dependencies and record dependency type, timing, required status and 실제 실행 위치.

## 7. Resolve Evidence

Classify findings as 확인됨, 추정됨, 미확인 or 상충됨. Use repository-relative `file:line` evidence for existing facts and `검색(scope=..., pattern=..., result=없음)` for verified absence. Preserve conflicts and never invent a line citation.

## 8. Build Component Briefings

Create one briefing card per deployable component. Separate source-backed values from inferred Kubernetes candidates. Put unresolved required values in 최소 입력 누락.

## 9. Finish Through Completion Gate

Confirm scope, component coverage, evidence, dependencies, missing inputs, secret redaction and exactly one readiness verdict before completing the report.
