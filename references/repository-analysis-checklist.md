# Repository Analysis Checklist

## Component Discovery

For each candidate directory, decide whether it is:

- API or web application
- static frontend build
- background worker
- scheduled task
- one-time initialization or migration job
- shared library or generated client
- development-only utility

Do not create a workload for a package merely because it has a manifest. Require an independently executable runtime behavior.

## Required Component Fields

- component name and path
- purpose and deployable status
- language, framework, runtime, and version
- build command
- production startup command
- listener port or no listener
- health endpoint
- configuration names and Application Phase
- writable or persistent paths
- inbound and outbound dependencies
- Execution Locus for outbound relationships
- containerization classification
- evidence status and file locations

## Containerization Classification

Use exactly one:

- Existing Container Definition
- Alternative Image Build
- Containerization Required
- Containerization Not Required
- Unknown

## Completion Questions

- Are all independently executable components represented?
- Are libraries excluded from workloads?
- Are development commands separated from production commands?
- Are ports confirmed from source or runtime configuration?
- Are missing facts marked Unknown?
