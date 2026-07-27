# Repository Navigation Corpus Design

## Goal

Build an evidence-backed navigation policy for Node.js, Java, Python, and Go repositories so the Kubernetes analysis skill can identify which files to inspect, why to inspect them, when to expand to related files, and when to stop without loading an entire repository into the LLM context.

## Scope

- Analyze 40 public OSS repositories: 10 per language.
- Preserve repository diversity across API servers, workers, schedulers, CLI tools, monorepos, controllers/operators, and large platforms.
- Record human-reviewed navigation traces and the minimum source set needed to establish workload, runtime, build, entrypoint, configuration, ports, storage, dependencies, and deployment evidence.
- Derive universal, language, framework, and repository-shape rules.
- Do not modify the production scanner until corpus-derived rules meet benchmark thresholds.

## Architecture

The research branch contains four independent layers:

1. **Corpus manifest** — pinned repository identity, revision, language, category, and analysis scope.
2. **Observation records** — reviewed navigation traces, selected and rejected files, evidence links, misses, and stop decisions.
3. **Rule corpus** — declarative priority, follow-edge, exclusion, fallback, and stop rules.
4. **Benchmark** — compares candidate navigation output against reviewed golden files using recall, precision, files read, and estimated token cost.

The scanner remains a candidate generator. It must not turn detected patterns directly into Kubernetes conclusions. The LLM receives ranked candidates and relationship edges, verifies hypotheses against minimal source ranges, and records confirmed, inferred, unknown, or conflicting findings.

## Research Questions

1. Which seed files reveal repository shape and workload roots fastest?
2. Which references reliably lead from build or deployment definitions to production entrypoints?
3. Which path and filename exclusions reduce noise without losing required evidence?
4. Which rules are universal, language-specific, framework-specific, or repository-specific?
5. What evidence is sufficient to stop reading more files for each Kubernetes design field?

## Observation Unit

Each repository observation records:

- repository identity and pinned revision
- repository shape and workload candidates
- seed files and their selection reasons
- ordered navigation actions
- relationship edges followed
- files and line ranges read
- files rejected and rejection reasons
- confirmed design inputs
- unresolved and conflicting inputs
- scanner false positives and false negatives
- generalized rule candidates
- reviewer notes

## Navigation Model

Navigation uses five rule types:

1. **Seed rules**: choose initial manifests, build, container, orchestration, and workspace files.
2. **Priority rules**: score candidates using file role, path role, runtime signals, and workload locality.
3. **Follow rules**: expand explicit references such as Docker `CMD`, package scripts, Maven modules, Python console scripts, and Go `cmd/*` packages.
4. **Fallback rules**: broaden search when required design fields remain unknown.
5. **Stop rules**: stop when the required fields have sufficient independent evidence or when the exploration budget is exhausted.

## Benchmark Metrics

- Required-file recall: golden required files selected by policy.
- Selection precision: selected files that are golden required or supporting files.
- Critical-field coverage: workload, runtime, build, entrypoint, configuration, port, storage, internal dependency, external dependency.
- Files read and source lines read.
- Estimated input tokens.
- Unsupported-assumption count.
- Contradiction detection rate.

Initial promotion thresholds:

- required-file recall >= 0.90 per language
- critical-field coverage >= 0.90 per language
- no regression in unsupported-assumption count
- median reviewed source files <= 20 per workload

## Repository Selection Principles

Each language set must cover at least:

- two HTTP/API-oriented repositories
- one background worker or queue
- one scheduler or workflow system
- one CLI-oriented repository
- one monorepo or multi-module repository
- one operator/controller or infrastructure-oriented repository where common
- one large platform repository

Framework repositories may be included only when they contain runnable examples or production processes useful for navigation research. Pure libraries are not sufficient unless they expose a distinct CLI, server, worker, or controller runtime.

## Safety and Reproducibility

- Pin every repository to an exact commit SHA before observation.
- Clone and inspect read-only; do not execute repository code or dependencies.
- Redact secrets and ignore actual `.env`, key, certificate, and credential files.
- Treat README and documentation as supporting evidence, not authoritative runtime truth.
- Preserve exact source paths and line ranges for every golden decision.

## Deliverables

- `research/navigation-corpus/manifest.json`
- `research/navigation-corpus/schema/observation.schema.json`
- `research/navigation-corpus/observations/<language>/<id>.json`
- `research/navigation-corpus/rules/universal.yaml`
- `research/navigation-corpus/rules/<language>.yaml`
- `research/navigation-corpus/benchmarks/`
- corpus methodology and per-language findings reports

## Non-goals

- Inferring production topology from popularity or framework defaults.
- Generating Kubernetes manifests directly from scanner matches.
- Supporting every language in the first corpus.
- Treating all source files of a matching extension as equally important.
