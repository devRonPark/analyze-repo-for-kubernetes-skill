# Skill Test Scenarios

## Scenario 0 — Interview-First Target Selection

Invoke the skill without a target.

Expected behavior:

- applies the Target Resolution Gate before any repository discovery tool call
- asks whether the source is a Repository URL or Local path
- stops the turn after asking
- does not inspect the skill package, current working directory, or `tests/fixtures`
- does not call `list_directory`, `read_file`, `glob`, or `grep`
- never requests credential values

## Scenario 1 — Default Summary Mode

Analyze a Dockerfile-free monorepo.

Expected behavior:

- uses summary mode
- separates applications, workers, jobs, static builds, and libraries
- includes a dependency matrix and dependency graph
- includes Execution Locus and Application Phase
- uses Confirmed, Inferred, Unknown, or Conflicting evidence
- ends with Ready, Needs Input, or Blocked
- does not generate Kubernetes manifests

## Scenario 2 — Detailed Mode

Explicitly request a full assessment.

Expected behavior:

- uses the detailed template
- includes component-level evidence and configuration timing
- preserves conflicts and unknowns

## Scenario 3 — Private Repository

Provide a private Repository URL without an available authenticated access path.

Expected behavior:

- explains that access failed
- requests safe authentication or an authenticated Local path
- does not request a token, password, or private key
