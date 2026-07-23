# Repository Analysis Workflow

## 1. Resolve Target

Apply the Target Resolution Gate before any repository discovery tool call. Confirm the Repository URL or Local path, access method, revision, and analyzed subdirectory.

## 2. Select Output Mode

Use summary mode by default. Use detailed mode only when explicitly requested.

## 3. Inventory High-Signal Files

Inspect directory structure, package manifests, lockfiles, build files, runtime entrypoints, Compose files, CI workflows, deployment docs, environment examples, migrations, and tests. Exclude generated output, dependency caches, vendored code, and binary assets unless directly relevant.

## 4. Identify Components

Separate independently executable applications, APIs, static frontends, workers, scheduled jobs, one-time jobs, and non-deployable libraries.

## 5. Determine Build and Runtime

For every deployable component, identify build command, production startup command, runtime and version, port or no listener, health endpoint, writable paths, and containerization status. A missing Dockerfile is a finding, not an analysis failure.

## 6. Analyze Configuration and Dependencies

Classify every major configuration by Application Phase. Build a directed dependency matrix and dependency graph. Record Execution Locus for each material relationship.

## 7. Resolve Evidence

Classify findings as Confirmed, Inferred, Unknown, or Conflicting. Preserve conflicts and cite file evidence.

## 8. Finish Through Completion Gate

Do not finish until every deployable component is classified, risks and required inputs are explicit, and the report ends with Ready, Needs Input, or Blocked.
