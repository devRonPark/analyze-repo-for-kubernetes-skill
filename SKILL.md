---
name: analyze-repo-for-kubernetes
description: Use when assessing an unfamiliar application repository for Kubernetes migration, Docker Compose migration, manifest or Helm preparation, GitOps onboarding, or deployment-readiness analysis, including repositories without Dockerfiles and monorepos.
---

# Analyze Repository for Kubernetes

## Overview

Analyze a repository far enough that a separate design or generation step can begin Kubernetes work without rereading the entire codebase. Describe deployable components, build and runtime behavior, configuration, networking, storage, and component relationships with file-level evidence.

**핵심 원칙:** 근거 없는 단정보다 정확한 `미확인`이 낫다.

## User-Facing Language

The skill's users are Korean. Write all stdout messages, prompts, progress updates, errors intended for the user, and final reports in Korean. Keep technical identifiers, file paths, command names, Kubernetes terms, and required contract labels in their original form when translation would reduce precision.

## Target Resolution Gate

This gate runs **before any repository discovery tool call**. Keep these two locations separate:

- **Skill root:** the installed skill package containing `SKILL.md`, references, assets, scripts, tests, and fixtures.
- **Analysis target:** the Repository URL or Local path explicitly supplied by the user.

The skill installation directory is not the analysis target. A slash-command path, `SKILL.md` location, relative reference path, current Qwen configuration directory, or bundled `tests/fixtures` directory never identifies the repository to analyze.

When no concrete Repository URL or Local path is present:

1. Ask the Interview-First question.
2. **Stop the turn after asking.**
3. Do not call `list_directory`, `read_file`, `glob`, `grep`, shell, Git, or web tools to guess a target.

Do not inspect the skill package to discover a repository. Read a skill reference or template only after the analysis target is resolved and only to apply the workflow. The only exception is when the user explicitly asks to install, inspect, validate, or test the skill package itself.

After a target is supplied, state the resolved target in one line, verify access, and then begin repository inventory. Never silently replace a missing target with the current working directory or the skill root.

## Interview-First Intake

When the analysis target is absent, begin with [interview-first-intake.md](references/interview-first-intake.md). Ask whether the source is a **Repository URL** or **Local path**, then request only the concrete value needed to access it.

If the user already supplied the target, do not ask for it again. Private repositories must use an existing authenticated connector, CLI session, credential helper, SSH agent, or authenticated local checkout. Never request credential values in chat.

## Scope

Supported inputs include a Repository URL, local checkout, branch or commit, repository subdirectory, or pull request plus related repository context.

Do not generate Kubernetes manifests, Helm charts, Dockerfiles, or application code. Do not redesign the architecture. Record Kubernetes implications only.

## Output Modes

**Default output mode: summary.** Use [migration-summary-template.md](assets/migration-summary-template.md) unless the user explicitly requests a full, exhaustive, or detailed assessment.

Use `detailed` mode only when explicitly requested. Then use [migration-assessment-template.md](assets/migration-assessment-template.md).

두 모드 모두 근거, 중요한 미확인 사항, 방향성 있는 의존성, 실행 위치, 설정 적용 시점, 최종 판정, 구성 요소별 Kubernetes 최소 초안 값을 보존한다.

## Required Workflow

1. Complete the interview-first intake when needed, then set scope, select output mode, and inventory the repository using [workflow.md](references/workflow.md).
2. Identify independently executable components using [repository-analysis-checklist.md](references/repository-analysis-checklist.md). Separate applications, workers, jobs, static builds, and libraries.
3. Discover build and production runtime behavior. A Dockerfile is optional. Apply [language-discovery-rules.md](references/language-discovery-rules.md).
4. Extract runtime versions, commands, ports, state, and configuration names. Classify configuration timing with [configuration-timing.md](references/configuration-timing.md). Never reveal secret values.
5. Map directed component relationships with [dependency-analysis.md](references/dependency-analysis.md). Separate the logical source component from the actual execution locus.
6. Resolve evidence and readiness with [evidence-and-readiness.md](references/evidence-and-readiness.md). Preserve conflicts instead of silently choosing one source.
7. Produce the selected report as a component briefing. Include a concise component relationship view and source-backed minimum manifest inputs for every deployable component.

## 근거 계약

모든 중요한 발견 사항을 **확인됨**, **추정됨**, **미확인**, **상충됨** 중 하나로 분류한다. 가능한 경우 파일 경로와 라인을 인용한다. 패키지 선언만으로 런타임 의존성을 증명할 수 없고, 개발 명령만으로 운영 기동 명령을 증명할 수 없다.

모든 중요한 발견 사항에는 `path/to/file:line` 또는 `path/to/file:start-end` 형식의 저장소 상대 파일·라인 근거를 하나 이상 포함한다(예: `pom.xml:18-26`). `미확인`과 `상충됨`도 예외가 아니다. 확인한 파일·라인과 그것만으로 하나의 답을 확정할 수 없는 이유를 함께 쓴다. 파일명만, 디렉터리 경로만, 명령어만, Docker Compose의 호스트 포트 매핑만으로는 충분한 근거가 아니다. 관련 라인이 있는 파일이 없으면 `미확인`으로 기록하고, 공백을 보여 주는 가장 가까운 설정 또는 진입점 라인을 인용한다.

근거는 발견 사항의 `근거` 필드 또는 주장 바로 뒤에 둔다. 보고서의 근거 색인은 필수이며 각 색인 항목에 파일·라인 근거를 제공한다. 다만 이는 구성 요소와 의존성별 근거를 대체하지 않는다.

## 구성 요소별 브리핑 계약

`## 구성 요소별 배포 브리핑` 아래에서 배포 가능 구성 요소마다 `### 구성 요소: <이름>`을 사용한다. 표로 속성을 나열하지 말고, 다음 범주 아래에 한 줄씩 `키: 값 — 상태: <상태> / 근거: path/to/file:line` 형식으로 쓴다.

- 역할과 실행: 역할, 경로, 유형, 언어, 프레임워크, 런타임
- 빌드와 기동: 빌드 명령, 운영 기동 명령, 컨테이너화
- 네트워크와 상태 확인: 프로토콜, 수신 포트 또는 비수신, 상태 확인 동작
- 설정과 상태: 설정, Secret 여부, 저장소, 볼륨 또는 세션 특성
- Kubernetes 최소 초안: 확인된 값에 한해서 `workload.kind`, `metadata.name`, `image`, `command`, `args`, `containerPort`, `Service`, `Ingress`를 기록
- 최소 입력 누락: manifest 초안 또는 적용에 꼭 필요하지만 저장소에서 확인되지 않은 값과 그 이유

값이 없다고 운영 기본값을 만들지 않는다. `resources`, `securityContext`, `serviceAccount`, `NetworkPolicy`, `HPA`, `PDB` 같은 일반 운영 정책은 저장소 근거가 있을 때만 기록한다. 실제 YAML, 작업 계획, 우선순위, 담당 역할, 다음 인계는 생성하지 않는다.

`image`, 기동 명령, 포트처럼 최소 초안에 필요한 값이 미확인인 경우에는 해당 구성 요소의 `최소 입력 누락`에 같은 `키: 값 — 상태 / 근거` 형식으로 쓴다. 보고서 독자에게 저장소를 다시 읽으라고 지시하지 않는다.

## Containerization Contract

각 배포 가능 구성 요소를 `기존 컨테이너 정의 있음`, `대체 이미지 빌드 방식`, `컨테이너화 필요`, `컨테이너화 불필요`, `미확인` 중 하나로 분류한다.

A missing Dockerfile is a finding, not an analysis failure.

## 준비 상태 판정

끝에는 반드시 하나의 판정을 둔다: **준비됨**, **추가 정보 필요**, 또는 **진행 불가**.

## Completion Gate

모든 배포 가능 구성 요소에 역할, 빌드/런타임, 컨테이너화 분류, 확인 또는 미확인 네트워크 동작, 설정과 상태, 실행 위치가 있는 외부 의존성, 최소 Kubernetes 초안 또는 최소 입력 누락, 속성별 근거가 있을 때까지 끝내지 않는다. 저장소 수준 보고서는 한눈에 보기, 구성 요소별 배포 브리핑, 구성 요소 관계, 최종 준비 상태 판정을 포함해야 한다.
