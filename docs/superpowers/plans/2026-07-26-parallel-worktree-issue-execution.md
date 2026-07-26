# Parallel Worktree Issue Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:using-git-worktrees before creating or entering issue worktrees. Use superpowers:test-driven-development for each feature or bugfix issue, and use superpowers:verification-before-completion before claiming an issue is complete. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the open GitHub Issues for `analyze-repo-for-kubernetes` through multiple Codex sessions with isolated worktrees, dependency gates, and predictable merge order.

**Architecture:** Split the work into an eval/report-protection lane and an evidence/graph substrate lane. Each issue branch starts from the latest `origin/main`; dependent issues wait for their predecessor to merge before implementation edits. Parallel work is allowed only across lanes or across explicitly independent eval slices.

**Tech Stack:** Git worktrees, GitHub Issues and PRs through `gh`, Python 3.11/3.12, `unittest`, existing scripts under `scripts/`, fixtures under `tests/fixtures/`, and Markdown contracts under `SKILL.md`, `references/`, and `docs/`.

## Global Constraints

- Follow `AGENTS.md`: plan first, manage vertical slices in GitHub Issues, implement one GitHub Issue at a time, use a dedicated branch, include `#<issue-number>` in every commit, and run focused validation before handoff.
- Write GitHub Issue and Pull Request titles, bodies, checklists, validation notes, and review-request text in Korean.
- Never implement directly on `main`.
- Do not mix unrelated issues on one branch.
- Preserve read-only repository analysis behavior, evidence traceability, deterministic output, secret redaction, and report validation contracts.
- Do not generate Kubernetes manifests, edit Helm charts, troubleshoot live clusters, or change application repositories from this skill repository.
- Current issue snapshot date: 2026-07-26.
- Closed issues `#21` and `#24` are merged through PR `#32`.
- Closed issues `#22` and `#23` are not planned; when open eval issues mention them, reconcile that dependency against the current report validator and the normalization/report model introduced by `#27`.

---

## Worktree Setup Protocol

Use this protocol at the start of every Codex session.

- [ ] **Step 1: Confirm repository state**

Run:

```bash
git status --short --branch
```

Run:

```bash
git fetch origin
```

Expected: local `main` may be dirty, but new issue work starts from `origin/main` in a separate worktree.

- [ ] **Step 2: Use `/tmp` for disposable worktrees**

Run:

```bash
mkdir -p /tmp/analyze-repo-for-kubernetes-skill-worktrees
```

Reason: the repository currently does not ignore a project-local `.worktrees/` directory, so `/tmp` avoids accidentally adding nested worktree files to the package.

- [ ] **Step 3: Create one worktree per issue**

Run this shape with the issue-specific branch from the task section:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-<number>-<slug> -b issue/<number>-<slug> origin/main
```

Then enter the worktree:

```bash
cd /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-<number>-<slug>
```

- [ ] **Step 4: Read local instructions**

Run:

```bash
sed -n '1,220p' AGENTS.md
```

Run:

```bash
sed -n '1,220p' SKILL.md
```

For implementation issues, read only the relevant referenced files from `references/`, `scripts/`, and `tests/` before editing.

- [ ] **Step 5: Verify clean baseline**

Run:

```bash
python3 scripts/validate_skill.py .
```

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Expected: all tests pass before issue-specific edits. If baseline fails, stop the issue session and report the exact command and output.

- [ ] **Step 6: Commit one issue at a time**

Run:

```bash
git add <changed-files>
```

Run:

```bash
git commit -m "type: concise Korean or English subject refs #<issue-number>"
```

Use a non-closing reference unless the PR is intended to close the issue on merge.

## Merge Queue Rules

- [ ] Merge `#26` before any behavior-changing `SKILL.md` refactor.
- [ ] Merge `#27` before `#33` is merged, even if `#33` is developed in parallel.
- [ ] Merge `#33` before `#34`, `#35`, `#36`, `#37`, or `#38`.
- [ ] Merge `#34` before `#35` and `#36`.
- [ ] Merge `#35` before `#36` and `#37`.
- [ ] Merge `#36` before `#37`.
- [ ] Merge `#37` before `#38`.
- [ ] Merge `#28` before `#30`.
- [ ] Merge `#31` last, after `#26`, `#27`, `#28`, and the evidence/graph pipeline contracts are stable.

## Parallel Wave Map

| Wave | Session | Issue | Branch | Worktree | Merge gate |
| --- | --- | --- | --- | --- | --- |
| 1 | Eval Foundation | `#26` | `issue/26-trigger-precision-eval` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-26-trigger-precision-eval` | none |
| 1 | Evidence Schema | `#33` | `issue/33-evidence-schema-validation` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-33-evidence-schema-validation` | merge after `#27` |
| 2 | Eval Baseline | `#27` | `issue/27-real-repository-run-eval` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-27-real-repository-run-eval` | merge after `#26` |
| 3 | Quality Eval | `#28` | `issue/28-skill-on-off-quality-eval` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-28-skill-on-off-quality-eval` | merge after `#27` |
| 3 | Inventory | `#34` | `issue/34-repository-inventory-diagnostics` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-34-repository-inventory-diagnostics` | merge after `#33` |
| 4 | Semantic Eval | `#29` | `issue/29-citation-entailment-grading` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-29-citation-entailment-grading` | merge after `#27`; prefer after `#28` |
| 4 | Efficiency Eval | `#30` | `issue/30-efficiency-intake-friction-eval` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-30-efficiency-intake-friction-eval` | merge after `#28` |
| 4 | Cache | `#35` | `issue/35-evidence-cache-reuse` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-35-evidence-cache-reuse` | merge after `#34` |
| 5 | Runtime Signals | `#36` | `issue/36-runtime-signal-extraction` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-36-runtime-signal-extraction` | merge after `#35` |
| 6 | Evidence Graph | `#37` | `issue/37-incremental-evidence-graph` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-37-incremental-evidence-graph` | merge after `#36` |
| 7 | Graph Query | `#38` | `issue/38-graph-query-packets` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-38-graph-query-packets` | merge after `#37` |
| 8 | Skill Refactor | `#31` | `issue/31-skill-reference-routing-refactor` | `/tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-31-skill-reference-routing-refactor` | merge last |

## Session A: Eval Foundation Lane

### Task 1: Issue `#26` Trigger Precision Eval

**Files:**
- Modify: `SKILL.md`
- Create: `scripts/eval_trigger_precision.py`
- Create: `tests/test_trigger_precision_eval.py`
- Create: `tests/fixtures/eval/trigger_cases.json`
- Modify if needed: `scripts/validate_skill.py`

**Interfaces:**
- Consumes: current `SKILL.md` frontmatter trigger boundary and existing target gate tests.
- Produces: executable trigger case format with `id`, `prompt`, `should_trigger`, and `rationale`; JSON/Markdown trigger precision report output.

- [ ] **Step 1: Start the worktree**

Run:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-26-trigger-precision-eval -b issue/26-trigger-precision-eval origin/main
```

- [ ] **Step 2: Read the issue and local trigger contracts**

Run:

```bash
gh issue view 26 --json number,title,body
```

Run:

```bash
sed -n '1,140p' SKILL.md
```

Run:

```bash
sed -n '1,260p' tests/test_codex_target_gate_hook.py
```

- [ ] **Step 3: Write failing tests for trigger cases**

Add tests that load `tests/fixtures/eval/trigger_cases.json`, assert at least 12 cases, assert at least 5 negative cases, and assert exact precision/recall math for deterministic fixture results.

- [ ] **Step 4: Implement the smallest deterministic evaluator**

Implement fixture loading and metric calculation without requiring live authentication. Keep live runtime execution opt-in.

- [ ] **Step 5: Update `SKILL.md` negative trigger boundary**

Add explicit non-target requests: manifest generation, Helm editing, live-cluster troubleshooting, existing-manifest-only review, and general Kubernetes explanation.

- [ ] **Step 6: Validate and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_trigger_precision_eval tests.test_package tests.test_codex_target_gate_hook -v
```

Run:

```bash
python3 scripts/validate_skill.py .
```

Run:

```bash
git add SKILL.md scripts/eval_trigger_precision.py tests/test_trigger_precision_eval.py tests/fixtures/eval/trigger_cases.json scripts/validate_skill.py
```

Run:

```bash
git commit -m "eval: add trigger precision cases refs #26"
```

### Task 2: Issue `#27` Real Repository Black-Box Regression

**Files:**
- Modify: `scripts/validate_regression.py`
- Create: `scripts/normalize_report.py`
- Create: `scripts/run_black_box_eval.py`
- Create: `tests/test_black_box_eval.py`
- Create: `tests/fixtures/black_box_repo/`
- Create: `tests/fixtures/regression/black_box_expected.json`

**Interfaces:**
- Consumes: trigger event conventions from `#26`, `scripts/validate_report.py`, and current report templates.
- Produces: opt-in black-box runner, deterministic normalizer, snapshot comparator, and metadata envelope.

- [ ] **Step 1: Wait for `#26` to merge**

Run:

```bash
git fetch origin
```

Create the branch from the updated `origin/main`:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-27-real-repository-run-eval -b issue/27-real-repository-run-eval origin/main
```

- [ ] **Step 2: Read the issue and regression checker**

Run:

```bash
gh issue view 27 --json number,title,body
```

Run:

```bash
sed -n '1,220p' scripts/validate_regression.py
```

Run:

```bash
sed -n '1,220p' scripts/validate_report.py
```

- [ ] **Step 3: Add deterministic normalizer tests**

Cover workload candidates, workload kinds, runtime dependencies, excluded candidates, launch definitions, operating-environment baseline, and design-input verdict. The test must fail when an expected component, dependency, or verdict is changed.

- [ ] **Step 4: Reframe the static checker**

Keep old fixture-schema validation only where it still has value, and make the new path compare normalized actual output against `black_box_expected.json`.

- [ ] **Step 5: Add an opt-in runner**

The runner records model/runtime identifier and skill commit SHA when available, and it does not require live execution in CI.

- [ ] **Step 6: Validate and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_black_box_eval tests.test_package -v
```

Run:

```bash
python3 scripts/validate_skill.py .
```

Run:

```bash
git add scripts/validate_regression.py scripts/normalize_report.py scripts/run_black_box_eval.py tests/test_black_box_eval.py tests/fixtures/black_box_repo tests/fixtures/regression/black_box_expected.json
```

Run:

```bash
git commit -m "eval: add real repository regression baseline refs #27"
```

## Session B: Evidence Substrate Lane

### Task 3: Issue `#33` Stable Evidence Identity And Validator

**Files:**
- Modify: `scripts/repository_evidence.py`
- Create: `scripts/evidence_contract.py`
- Create: `scripts/validate_evidence.py`
- Modify: `tests/test_repository_evidence.py`
- Create: `tests/test_evidence_contract.py`
- Create: `tests/fixtures/evidence/`

**Interfaces:**
- Consumes: current evidence records from `scripts/repository_evidence.py`.
- Produces: schema-versioned evidence records with stable IDs, source spans, extractor metadata, deterministic ordering, compatibility reading, and a standalone validator.

- [ ] **Step 1: Start the worktree**

Run:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-33-evidence-schema-validation -b issue/33-evidence-schema-validation origin/main
```

- [ ] **Step 2: Read the issue and collector tests**

Run:

```bash
gh issue view 33 --json number,title,body
```

Run:

```bash
sed -n '1,260p' scripts/repository_evidence.py
```

Run:

```bash
sed -n '1,320p' tests/test_repository_evidence.py
```

- [ ] **Step 3: Write failing validator tests**

Cover byte-stable normalized JSON, stable IDs, source spans, absence scope, duplicate ID rejection, invalid span rejection, root escape rejection, unknown kind rejection, and secret leakage rejection.

- [ ] **Step 4: Implement the contract module**

Add canonical ID generation, source reference objects, extractor metadata, ordering, duplicate handling, compatibility loading, and validation errors with machine-readable codes.

- [ ] **Step 5: Migrate the collector**

Update `repository_evidence.py` to emit the new contract while preserving the existing human-readable citation field where needed.

- [ ] **Step 6: Validate and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_evidence_contract tests.test_repository_evidence -v
```

Run:

```bash
python3 scripts/validate_evidence.py tests/fixtures/evidence/valid.json
```

Run:

```bash
git add scripts/repository_evidence.py scripts/evidence_contract.py scripts/validate_evidence.py tests/test_repository_evidence.py tests/fixtures/evidence
```

Run:

```bash
git commit -m "feat: stabilize evidence identity contract refs #33"
```

**Merge note:** `#33` may be developed in parallel with `#26` and `#27`, but merge it only after `#27` has established the report baseline.

### Task 4: Issue `#34` Repository Inventory Diagnostics

**Files:**
- Modify: `scripts/repository_evidence.py`
- Create if useful: `scripts/repository_inventory.py`
- Modify: `tests/test_repository_evidence.py`
- Create: `tests/test_repository_inventory.py`
- Create: `tests/fixtures/inventory_repo/`

**Interfaces:**
- Consumes: stable path/source identity from `#33`.
- Produces: repository inventory artifact with one disposition and one reason for every discovered path.

- [ ] **Step 1: Wait for `#33` to merge and start from `origin/main`**

Run:

```bash
git fetch origin
```

Run:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-34-repository-inventory-diagnostics -b issue/34-repository-inventory-diagnostics origin/main
```

- [ ] **Step 2: Read the issue and path-walk code**

Run:

```bash
gh issue view 34 --json number,title,body
```

Run:

```bash
sed -n '1,220p' scripts/repository_evidence.py
```

- [ ] **Step 3: Add fixture and failing tests**

The fixture includes source files, generated output, dependency caches, binary files, sensitive-looking files, symlinks, too-large files, and a read-error case when the platform permits it.

- [ ] **Step 4: Implement inventory classification**

Classify `included`, `ignored`, `generated`, `vendored`, `dependency_cache`, `binary`, `sensitive`, `symlink`, `too_large`, `unclassified`, and `read_error`. Prevent symlink traversal and root escape.

- [ ] **Step 5: Add CLI output controls**

Add options to write the inventory artifact and display compact diagnostics while keeping default read-only behavior.

- [ ] **Step 6: Validate and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_repository_inventory tests.test_repository_evidence -v
```

Run:

```bash
python3 scripts/validate_skill.py .
```

Run:

```bash
git add scripts/repository_evidence.py scripts/repository_inventory.py tests/test_repository_evidence.py tests/test_repository_inventory.py tests/fixtures/inventory_repo
```

Run:

```bash
git commit -m "feat: add repository inventory diagnostics refs #34"
```

## Session C: Quality And Efficiency Eval Lane

### Task 5: Issue `#28` Skill ON/OFF Quality Comparison

**Files:**
- Modify: `scripts/run_black_box_eval.py`
- Modify: `scripts/normalize_report.py`
- Create: `scripts/compare_skill_quality.py`
- Create: `tests/test_skill_quality_eval.py`
- Create: `tests/fixtures/quality_eval/`

**Interfaces:**
- Consumes: black-box runner and normalizer from `#27`.
- Produces: Skill ON/OFF execution mode, reviewed expected facts, per-run scores, deltas, Markdown report, and JSON report.

- [ ] **Step 1: Wait for `#27` to merge**

Run:

```bash
git fetch origin
```

Run:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-28-skill-on-off-quality-eval -b issue/28-skill-on-off-quality-eval origin/main
```

- [ ] **Step 2: Read the issue and eval runner**

Run:

```bash
gh issue view 28 --json number,title,body
```

Run:

```bash
sed -n '1,260p' scripts/run_black_box_eval.py
```

Run:

```bash
sed -n '1,260p' scripts/normalize_report.py
```

- [ ] **Step 3: Add scoring tests**

Cover deployable component precision and recall, excluded-item correctness, runtime dependency precision and recall, production startup-command correctness, unsupported-claim count, valid citation-location rate, and design-input verdict correctness.

- [ ] **Step 4: Implement ON/OFF comparison**

Ensure both runs use the same prompt, repository revision, model, runtime options, and tool permissions. Retain raw normalized outputs for diagnosis.

- [ ] **Step 5: Document stale dependency reconciliation**

In the PR body and any local eval note, state that closed issues `#22` and `#23` are reconciled through the current `#27` normalized report and `scripts/validate_report.py` contracts.

- [ ] **Step 6: Validate and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_skill_quality_eval tests.test_black_box_eval -v
```

Run:

```bash
python3 scripts/validate_skill.py .
```

Run:

```bash
git add scripts/run_black_box_eval.py scripts/normalize_report.py scripts/compare_skill_quality.py tests/test_skill_quality_eval.py tests/fixtures/quality_eval
```

Run:

```bash
git commit -m "eval: compare skill on off quality refs #28"
```

### Task 6: Issue `#29` Citation Entailment And Semantic Claim Grading

**Files:**
- Modify: `scripts/normalize_report.py`
- Create: `scripts/grade_citation_entailment.py`
- Create: `tests/test_citation_entailment.py`
- Create: `tests/fixtures/citation_entailment/`

**Interfaces:**
- Consumes: normalized report fields and citation-location validation from `#27`.
- Produces: claim-evidence pair extraction, deterministic test double grading, opt-in semantic grader hook, claim-level JSON, and Markdown summary.

- [ ] **Step 1: Start after `#27`, preferably after `#28`**

Run:

```bash
git fetch origin
```

Run:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-29-citation-entailment-grading -b issue/29-citation-entailment-grading origin/main
```

- [ ] **Step 2: Read the issue and report validator**

Run:

```bash
gh issue view 29 --json number,title,body
```

Run:

```bash
sed -n '1,260p' scripts/validate_report.py
```

Run:

```bash
sed -n '1,260p' scripts/normalize_report.py
```

- [ ] **Step 3: Add claim-evidence fixture tests**

Create at least 20 reviewed pairs across supported, unsupported, and insufficient examples. Include claims for deployable classification, production startup command, port/listener, runtime dependency, operating-environment baseline, and final design-input verdict.

- [ ] **Step 4: Implement deterministic grading path**

Return exactly `supported`, `unsupported`, or `insufficient` with a concise reason. Redact secret-like values before context construction.

- [ ] **Step 5: Add opt-in live semantic grading**

Keep live model grading disabled by default. Unit tests must not require credentials or network access.

- [ ] **Step 6: Validate and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_citation_entailment tests.test_package -v
```

Run:

```bash
python3 scripts/validate_skill.py .
```

Run:

```bash
git add scripts/normalize_report.py scripts/grade_citation_entailment.py tests/test_citation_entailment.py tests/fixtures/citation_entailment
```

Run:

```bash
git commit -m "eval: grade citation entailment refs #29"
```

### Task 7: Issue `#30` Efficiency And Intake-Friction Measurement

**Files:**
- Modify: `scripts/run_black_box_eval.py`
- Create: `scripts/measure_analysis_efficiency.py`
- Create: `tests/test_efficiency_eval.py`
- Create: `tests/fixtures/efficiency_eval/`
- Modify if needed: `references/interview-first-intake.md`

**Interfaces:**
- Consumes: black-box execution harness from `#27` and quality metrics from `#28`.
- Produces: standardized execution telemetry, current intake versus one-question prototype comparison, JSON results, Markdown comparison, and baseline budget.

- [ ] **Step 1: Wait for `#28` to merge**

Run:

```bash
git fetch origin
```

Run:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-30-efficiency-intake-friction-eval -b issue/30-efficiency-intake-friction-eval origin/main
```

- [ ] **Step 2: Read the issue and intake references**

Run:

```bash
gh issue view 30 --json number,title,body
```

Run:

```bash
sed -n '1,240p' references/interview-first-intake.md
```

Run:

```bash
sed -n '1,260p' scripts/run_black_box_eval.py
```

- [ ] **Step 3: Add telemetry fixture tests**

Cover user turns, completed tool calls, repository files read, repeated reads, elapsed runtime, token usage marked unavailable when absent, and final validation status.

- [ ] **Step 4: Implement measurement collector**

Use actual runtime events where available. Mark unavailable values explicitly instead of estimating them.

- [ ] **Step 5: Add one-question prototype harness**

Keep it isolated in eval code. Do not change production intake flow based only on lower cost.

- [ ] **Step 6: Validate and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_efficiency_eval tests.test_skill_quality_eval -v
```

Run:

```bash
python3 scripts/validate_skill.py .
```

Run:

```bash
git add scripts/run_black_box_eval.py scripts/measure_analysis_efficiency.py tests/test_efficiency_eval.py tests/fixtures/efficiency_eval references/interview-first-intake.md
```

Run:

```bash
git commit -m "eval: measure analysis efficiency refs #30"
```

## Session D: Cache Runtime Graph Lane

### Task 8: Issue `#35` Per-File Evidence Cache

**Files:**
- Modify: `scripts/repository_evidence.py`
- Create: `scripts/evidence_cache.py`
- Create: `tests/test_evidence_cache.py`
- Create: `tests/fixtures/cache_repo/`

**Interfaces:**
- Consumes: stable evidence identity from `#33` and inventory/content identity from `#34`.
- Produces: disposable per-file cache keyed by repository identity, analysis root, content hash, evidence schema version, extractor name/version, and rule fingerprint.

- [ ] **Step 1: Wait for `#34` to merge**

Run:

```bash
git fetch origin
```

Run:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-35-evidence-cache-reuse -b issue/35-evidence-cache-reuse origin/main
```

- [ ] **Step 2: Read the issue and current evidence contract**

Run:

```bash
gh issue view 35 --json number,title,body
```

Run:

```bash
sed -n '1,260p' scripts/evidence_contract.py
```

Run:

```bash
sed -n '1,260p' scripts/repository_evidence.py
```

- [ ] **Step 3: Add cache equivalence tests**

Cover unchanged second run reuse, one-file edit invalidation, delete/rename stale removal, schema/extractor/rule invalidation, corrupted entry rebuild, no-cache option, and no raw source bodies in cache storage.

- [ ] **Step 4: Implement atomic cache storage**

Use content hash as the correctness boundary and stat metadata only as a fast path.

- [ ] **Step 5: Add cache diagnostics**

Report hit, miss, invalidated, corrupted, and bypassed counts.

- [ ] **Step 6: Validate and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_evidence_cache tests.test_repository_evidence -v
```

Run:

```bash
python3 scripts/validate_skill.py .
```

Run:

```bash
git add scripts/repository_evidence.py scripts/evidence_cache.py tests/test_evidence_cache.py tests/fixtures/cache_repo
```

Run:

```bash
git commit -m "feat: add per-file evidence cache refs #35"
```

### Task 9: Issue `#36` Scoped Runtime Signal Extraction

**Files:**
- Modify: `scripts/repository_evidence.py`
- Create: `scripts/runtime_signal_extractors.py`
- Create: `tests/test_runtime_signal_extractors.py`
- Create: `tests/fixtures/runtime_signal_repo/`

**Interfaces:**
- Consumes: evidence contract from `#33`, inventory classification from `#34`, and cache invalidation from `#35`.
- Produces: pluggable extractor interface for Node.js, Python, Java, and Go runtime signals.

- [ ] **Step 1: Wait for `#35` to merge**

Run:

```bash
git fetch origin
```

Run:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-36-runtime-signal-extraction -b issue/36-runtime-signal-extraction origin/main
```

- [ ] **Step 2: Read the issue and evidence collector**

Run:

```bash
gh issue view 36 --json number,title,body
```

Run:

```bash
sed -n '1,320p' scripts/repository_evidence.py
```

- [ ] **Step 3: Add reviewed runtime fixture tests**

Cover environment/config reads, explicit listener host and port, outbound connection hints, writable paths, worker/scheduler/background registration, comment exclusion, test-only exclusion, framework default exclusion, per-file parser failure diagnostics, and disable flag behavior.

- [ ] **Step 4: Implement the extractor interface**

Key extractors by language and extractor version. Keep extraction scoped; do not build call graphs or import application code.

- [ ] **Step 5: Integrate cache invalidation**

Changing extractor version or rule fingerprint must invalidate affected cache entries while keeping clean and cached extraction equivalent.

- [ ] **Step 6: Validate and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runtime_signal_extractors tests.test_evidence_cache tests.test_repository_evidence -v
```

Run:

```bash
python3 scripts/validate_skill.py .
```

Run:

```bash
git add scripts/repository_evidence.py scripts/runtime_signal_extractors.py tests/test_runtime_signal_extractors.py tests/fixtures/runtime_signal_repo
```

Run:

```bash
git commit -m "feat: add scoped runtime signal extraction refs #36"
```

### Task 10: Issue `#37` Incremental Evidence Relationship Graph

**Files:**
- Create: `scripts/evidence_graph.py`
- Create: `scripts/validate_evidence_graph.py`
- Create: `tests/test_evidence_graph.py`
- Create: `tests/fixtures/evidence_graph/`
- Modify if needed: `scripts/repository_evidence.py`

**Interfaces:**
- Consumes: stable evidence IDs from `#33`, cache/change identity from `#35`, and runtime signals from `#36`.
- Produces: versioned graph schema, deterministic node/edge IDs, full build mode, changed-file merge mode, pruning, silent-shrink guard, and graph validator.

- [ ] **Step 1: Wait for `#36` to merge**

Run:

```bash
git fetch origin
```

Run:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-37-incremental-evidence-graph -b issue/37-incremental-evidence-graph origin/main
```

- [ ] **Step 2: Read the issue and evidence schema**

Run:

```bash
gh issue view 37 --json number,title,body
```

Run:

```bash
sed -n '1,320p' scripts/evidence_contract.py
```

- [ ] **Step 3: Add graph fixture tests**

Cover deterministic full build, incremental merge equivalence to clean rebuild, changed-file contribution replacement, deleted-file pruning, orphan removal, source evidence IDs on every relationship, no LLM judgment stored as repository fact, and silent-shrink rejection.

- [ ] **Step 4: Implement graph schema and builder**

Support the node and edge types listed in issue `#37`. Build only from validated typed evidence.

- [ ] **Step 5: Implement graph validator**

Reject dangling references, duplicate IDs, unsupported edge types, and missing source provenance.

- [ ] **Step 6: Validate and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_evidence_graph tests.test_runtime_signal_extractors -v
```

Run:

```bash
python3 scripts/validate_evidence_graph.py tests/fixtures/evidence_graph/valid_graph.json
```

Run:

```bash
git add scripts/evidence_graph.py scripts/validate_evidence_graph.py scripts/repository_evidence.py tests/test_evidence_graph.py tests/fixtures/evidence_graph
```

Run:

```bash
git commit -m "feat: build incremental evidence graph refs #37"
```

### Task 11: Issue `#38` Bounded Evidence Graph Query Packets

**Files:**
- Create: `scripts/query_evidence_graph.py`
- Modify: `scripts/evidence_graph.py`
- Create: `tests/test_evidence_graph_query.py`
- Create: `tests/fixtures/evidence_graph_queries/`

**Interfaces:**
- Consumes: graph schema and validator from `#37`.
- Produces: deterministic query intents, seed selection, bounded traversal, machine-readable subgraph output, Markdown analysis packet output, budget reporting, conflict/missing evidence surfacing, and stale schema diagnostics.

- [ ] **Step 1: Wait for `#37` to merge**

Run:

```bash
git fetch origin
```

Run:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-38-graph-query-packets -b issue/38-graph-query-packets origin/main
```

- [ ] **Step 2: Read the issue and graph builder**

Run:

```bash
gh issue view 38 --json number,title,body
```

Run:

```bash
sed -n '1,360p' scripts/evidence_graph.py
```

- [ ] **Step 3: Add query fixture tests**

Cover component overview, production launch evidence, runtime dependency, configuration key usage, endpoint and port, writable path and storage, health signal, deployment-definition comparison, and conflict inspection.

- [ ] **Step 4: Implement bounded traversal**

Support stable ID, exact name, and typed-filter seeds. Enforce depth, node, edge, and estimated-token budgets and report all budget decisions.

- [ ] **Step 5: Emit packets**

Emit both machine-readable subgraph JSON and compact Markdown packet. Mark missing, ambiguous, and conflicting evidence explicitly rather than synthesizing an answer.

- [ ] **Step 6: Validate and commit**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_evidence_graph_query tests.test_evidence_graph -v
```

Run:

```bash
python3 scripts/query_evidence_graph.py --graph tests/fixtures/evidence_graph/valid_graph.json --intent component-overview --seed api
```

Run:

```bash
git add scripts/query_evidence_graph.py scripts/evidence_graph.py tests/test_evidence_graph_query.py tests/fixtures/evidence_graph_queries
```

Run:

```bash
git commit -m "feat: query bounded evidence graph packets refs #38"
```

## Session E: Final Documentation Refactor Lane

### Task 12: Issue `#31` Eval-Protected `SKILL.md` Reference Routing Refactor

**Files:**
- Modify: `SKILL.md`
- Modify: `references/workflow.md`
- Modify: `references/evidence-and-readiness.md`
- Modify if needed: `references/interview-first-intake.md`
- Modify if needed: `assets/migration-summary-template.md`
- Modify if needed: `assets/migration-assessment-template.md`
- Modify if needed: `tests/test_package.py`
- Modify if needed: `scripts/validate_skill.py`

**Interfaces:**
- Consumes: trigger eval from `#26`, end-to-end baseline from `#27`, quality comparison from `#28`, and stable evidence/report contracts from the evidence lane.
- Produces: simplified `SKILL.md` with authoritative reference routing and reduced duplicated normative text without behavior changes.

- [ ] **Step 1: Wait for required gates**

Confirm `#26`, `#27`, `#28`, `#33`, `#34`, `#35`, `#36`, `#37`, and `#38` are merged or explicitly deferred by the maintainer.

Run:

```bash
git fetch origin
```

Run:

```bash
git worktree add /tmp/analyze-repo-for-kubernetes-skill-worktrees/issue-31-skill-reference-routing-refactor -b issue/31-skill-reference-routing-refactor origin/main
```

- [ ] **Step 2: Inventory normative duplication**

Run:

```bash
gh issue view 31 --json number,title,body
```

Run:

```bash
sed -n '1,360p' SKILL.md
```

Run:

```bash
sed -n '1,260p' references/workflow.md
```

Run:

```bash
sed -n '1,260p' references/evidence-and-readiness.md
```

- [ ] **Step 3: Measure before counts**

Run:

```bash
wc -l SKILL.md references/workflow.md references/evidence-and-readiness.md assets/migration-summary-template.md assets/migration-assessment-template.md
```

- [ ] **Step 4: Move duplicated rules to authoritative homes**

Keep `SKILL.md` focused on trigger/non-trigger boundary, safety invariants, high-level workflow, output boundary, and explicit reference routing. Keep detailed step contracts in references and templates.

- [ ] **Step 5: Replace brittle wording checks**

Where practical, replace wording-presence tests with behavioral or contract tests. Preserve package validation for required contracts that protect installability.

- [ ] **Step 6: Validate no behavior regression**

Run:

```bash
python3 scripts/validate_skill.py .
```

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Run the local deterministic eval commands added by `#26`, `#27`, and `#28` according to their help output.

- [ ] **Step 7: Measure after counts and commit**

Run:

```bash
wc -l SKILL.md references/workflow.md references/evidence-and-readiness.md assets/migration-summary-template.md assets/migration-assessment-template.md
```

Run:

```bash
git add SKILL.md references/workflow.md references/evidence-and-readiness.md references/interview-first-intake.md assets/migration-summary-template.md assets/migration-assessment-template.md tests/test_package.py scripts/validate_skill.py
```

Run:

```bash
git commit -m "refactor: simplify skill reference routing refs #31"
```

## Cross-Session Coordination

- [ ] **Step 1: Use issue comments as the coordination log**

Each session posts a Korean progress comment at start, before handoff, and when blocked. Include branch name, worktree path, files touched, validation command, and merge dependency.

- [ ] **Step 2: Avoid shared-file collision by lane**

Eval sessions should avoid editing `scripts/repository_evidence.py` unless the issue explicitly requires it. Evidence sessions should avoid editing `SKILL.md`, `scripts/validate_regression.py`, and eval harness files unless the issue explicitly requires it.

- [ ] **Step 3: Keep dependent issues unstarted until merge gates are met**

Reading and design notes may happen early, but code/test/docs edits for dependent issues start only after the dependency branch has merged to `origin/main`.

- [ ] **Step 4: Refresh each issue branch before PR**

Run:

```bash
git fetch origin
```

Run:

```bash
git merge origin/main
```

Resolve conflicts in the issue branch only. Do not modify unrelated worktrees to fix a conflict.

- [ ] **Step 5: Use the same handoff block in every final session message**

Use:

```text
GitHub Issue: #<number>
Branch: issue/<number>-<slug>
Changed behavior:
Files changed:
Validation:
Blocked validation:
Follow-up issue:
```

## Self-Review

- Spec coverage: this plan covers open issues `#26` through `#31` and `#33` through `#38`, with worktree paths, branch names, merge gates, per-session files, validation, and handoff format.
- Placeholder scan: no deferred implementation markers are used; each task has concrete files, commands, and acceptance checks.
- Type and command consistency: branch names, worktree paths, and issue numbers match the wave map and task sections.
