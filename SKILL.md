---
name: analyze-repo-for-kubernetes
description: Use when assessing an unfamiliar application repository for Kubernetes migration, Docker Compose migration, manifest or Helm preparation, GitOps onboarding, or deployment-readiness analysis, including repositories without Dockerfiles and monorepos.
---

# Analyze Repository for Kubernetes

## Overview

Analyze a repository far enough that a separate design or generation step can begin Kubernetes work without rereading the entire codebase. Describe deployable components, build and runtime behavior, configuration, networking, storage, and component relationships with file-level evidence.

**Core principle:** A correct `Unknown` is better than an unsupported conclusion.

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

Both modes must preserve evidence, critical unknowns, directed dependencies, execution locus, configuration application phase, and the final readiness verdict.

## Required Workflow

1. Complete the interview-first intake when needed, then set scope, select output mode, and inventory the repository using [workflow.md](references/workflow.md).
2. Identify independently executable components using [repository-analysis-checklist.md](references/repository-analysis-checklist.md). Separate applications, workers, jobs, static builds, and libraries.
3. Discover build and production runtime behavior. A Dockerfile is optional. Apply [language-discovery-rules.md](references/language-discovery-rules.md).
4. Extract runtime versions, commands, ports, state, and configuration names. Classify configuration timing with [configuration-timing.md](references/configuration-timing.md). Never reveal secret values.
5. Map directed component relationships with [dependency-analysis.md](references/dependency-analysis.md). Separate the logical source component from the actual execution locus.
6. Resolve evidence and readiness with [evidence-and-readiness.md](references/evidence-and-readiness.md). Preserve conflicts instead of silently choosing one source.
7. Produce the selected report. Include a dependency matrix and text dependency graph.

## Evidence Contract

Classify every material finding as **Confirmed**, **Inferred**, **Unknown**, or **Conflicting**. Cite file paths and line numbers when available. A package declaration alone does not prove a runtime dependency. A development command does not prove a production startup command.

## Containerization Contract

Classify each deployable component as Existing Container Definition, Alternative Image Build, Containerization Required, Containerization Not Required, or Unknown.

A missing Dockerfile is a finding, not an analysis failure.

## Readiness Verdict

End with exactly one verdict: **Ready**, **Needs Input**, or **Blocked**.

## Completion Gate

Do not finish until every deployable component has build/runtime and containerization classifications, known or unknown network behavior, configuration application phases, outbound dependencies with execution loci, and evidence. The repository-level report must contain the component inventory, dependency matrix, dependency graph, risks, required inputs, and readiness verdict.
