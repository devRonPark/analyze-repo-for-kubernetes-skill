# Language Discovery Rules

Use these files as evidence even when Dockerfiles are absent.

## Node.js and TypeScript

Inspect `package.json`, workspace files, lockfiles, framework config, source entrypoints, environment access, and scripts. Distinguish development servers from production startup and static builds.

## Python

Inspect `pyproject.toml`, requirements files, lockfiles, framework entrypoints, WSGI or ASGI configuration, settings modules, migration tools, and startup scripts.

## Go

Inspect `go.mod`, `cmd/`, `main` packages, flags, environment access, embedded assets, and build workflows.

## Java and Kotlin

Inspect Maven or Gradle files, application configuration, main classes, framework profiles, ports, and executable packaging.

## .NET

Inspect solution and project files, `Program.cs`, hosting configuration, launch settings as development evidence only, and environment-specific configuration.

## Rust

Inspect `Cargo.toml`, workspace members, binaries, features, configuration loading, and server binding code.

## Evidence Rules

- A dependency declaration does not prove runtime use.
- A development script does not prove the production startup command.
- 프레임워크 기본값은 추정됨 근거가 될 수 있지만, 저장소 근거 없이 확인됨이 될 수는 없다.
- A missing Dockerfile is a finding, not an analysis failure.
