# Repository Navigation Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Track every step with checkboxes.

**Goal:** Build and benchmark a reviewed 40-repository navigation corpus for Node.js, Java, Python, and Go.

**Architecture:** A pinned manifest drives read-only inventory collection. Reviewed observations record navigation traces and golden files. Declarative navigation rules are synthesized from repeated patterns and evaluated before any production scanner change.

**Tech Stack:** Python 3 standard library, JSON, unittest, git.

## Global Constraints

- Exactly 10 repositories per language.
- Pin each repository to an exact commit before observation.
- Do not run repository applications, builds, or dependencies.
- Scanner output remains navigation candidates, not final Kubernetes conclusions.
- Do not modify production scanner rules until benchmark thresholds pass.

## File Structure

- `research/navigation-corpus/manifest.json`: 40-repository corpus definition.
- `research/navigation-corpus/schema/`: manifest and observation contracts.
- `research/navigation-corpus/observations/<language>/`: reviewed golden records.
- `research/navigation-corpus/rules/`: universal and language-specific rules.
- `research/navigation-corpus/benchmarks/`: benchmark outputs.
- `scripts/validate_navigation_corpus.py`: corpus validation.
- `scripts/collect_navigation_inventory.py`: read-only inventory collection.
- `scripts/navigation_candidates.py`: candidate ranking.
- `scripts/navigation_edges.py`: explicit relationship extraction.
- `scripts/run_navigation_benchmark.py`: metrics and threshold checks.

## Tasks

### Task 1: Manifest and schema

- [ ] Add the 40-repository manifest.
- [ ] Add validation requiring unique IDs, 10 repositories per language, repository URL, category, analysis scope, and revision state.
- [ ] Add observation schema for navigation steps, file decisions, relationship edges, findings, misses, and rule candidates.
- [ ] Add focused validator tests.

### Task 2: Inventory and candidate ranking

- [ ] Wrap the existing repository inventory in a corpus runner.
- [ ] Add transparent file-role and path-role scores.
- [ ] Penalize test, example, generated, cache, and vendored paths without hiding them from diagnostics.
- [ ] Record every score contribution and selection reason.
- [ ] Add deterministic-order tests.

### Task 3: Relationship navigation

- [ ] Extract explicit edges from container commands, package scripts, workspace declarations, Maven modules, Gradle includes, Python console scripts, and Go command packages.
- [ ] Preserve unresolved references.
- [ ] Add fixtures and focused tests for each language.

### Task 4: Reviewed corpus observations

- [ ] Pin all repositories to exact revisions.
- [ ] Produce inventory and candidate output for every repository.
- [ ] Review navigation from initial seed through stop decision.
- [ ] Record selected, supporting, rejected, and missed files with exact evidence.
- [ ] Complete Node.js, Java, Python, and Go in separate reviewable batches.

### Task 5: Rule synthesis

- [ ] Derive universal, language, framework, and repository-shape rules.
- [ ] Attach support repositories and counterexamples to every proposed rule.
- [ ] Prevent single-repository patterns from becoming universal rules.
- [ ] Require manual approval status for benchmark use.

### Task 6: Benchmark

- [ ] Compute required-file recall, selection precision, critical-field coverage, files read, lines read, and estimated tokens.
- [ ] Aggregate by language and repository shape.
- [ ] Fail benchmark execution when promotion thresholds are missed.
- [ ] Save baseline and corpus-derived comparison reports.

### Task 7: Production promotion report

- [ ] Identify rules that satisfy benchmark thresholds.
- [ ] Document rejected and overfit rules.
- [ ] Propose a minimal production patch separately.
- [ ] Run the existing test suite, corpus validation, and benchmark before integration.

## Verification Commands

```bash
python3 scripts/validate_navigation_corpus.py research/navigation-corpus
python3 -m unittest tests.test_navigation_corpus_manifest -v
python3 -m unittest tests.test_navigation_candidates -v
python3 -m unittest tests.test_navigation_edges -v
python3 -m unittest tests.test_navigation_benchmark -v
python3 -m unittest discover -s tests -p 'test_*.py' -v
```
