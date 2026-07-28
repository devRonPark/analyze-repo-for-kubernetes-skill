# Language Discovery Rules

Use these files as evidence even when Dockerfiles are absent.

## Node.js and TypeScript

Inspect `package.json`, workspace files, lockfiles, framework config, source entrypoints, environment access, and scripts. Distinguish development servers from production startup and static builds.

Determine the package manager for each component in this order: the component's `packageManager` field, workspace package-manager declaration, the component manifest, then lockfiles. A root declaration does not override a nested component's stronger declaration. Mixed managers must be reported per component. If equally applicable declarations conflict or only weak lockfile evidence exists, use `확인 필요` instead of naming one manager.

Record `설치 명령`, `빌드 명령`, `이미지 빌드 명령`, and `운영 기동 명령` as separate stages. A `dev` script is not production startup evidence; a Docker or other image build command is not application build evidence.

## Python

Inspect `pyproject.toml`, requirements files, lockfiles, framework entrypoints, WSGI or ASGI configuration, settings modules, migration tools, and startup scripts.

## Go

Inspect `go.mod`, `cmd/`, `main` packages, flags, environment access, embedded assets, and build workflows.

## Java and Kotlin

Inspect Maven or Gradle files, application configuration, main classes, framework profiles, ports, and executable packaging.

Evaluate Maven and Gradle separately. Use a wrapper adjacent to the component before a repository-root wrapper, then compare root and module settings. When both toolchains are present, report the scope and evidence for each rather than selecting one solely because both files exist. Keep install/dependency resolution, application build, image build, and runtime startup as distinct commands.

## .NET

Inspect solution and project files, `Program.cs`, hosting configuration, launch settings as development evidence only, and environment-specific configuration.

## Rust

Inspect `Cargo.toml`, workspace members, binaries, features, configuration loading, and server binding code.

## Evidence Rules

- A dependency declaration does not prove runtime use.
- A development script does not prove the production startup command.
- 프레임워크 기본값은 추정됨 근거가 될 수 있지만, 저장소 근거 없이 확인됨이 될 수는 없다.
- A missing Dockerfile is a finding, not an analysis failure.
