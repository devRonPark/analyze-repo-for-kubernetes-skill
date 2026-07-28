# AGENTS.md

This file is the operating guide for agents working in this repository. Keep it
compact. Detailed skill behavior belongs in `SKILL.md`, `references/`, `scripts/`,
`tests/`, and `validation/`.

## Project Context

This repository is the Plugin root for the `analyze-repo-for-kubernetes`
Plugin. Its nested workflow Skill analyzes application repositories for
Kubernetes migration readiness, Docker Compose migration assessment, GitOps
onboarding, and Kubernetes design inputs.

The skill produces analysis and minimum design inputs only. Do not use this
repository to generate deployment manifests, edit Helm charts, troubleshoot live
clusters, or make application implementation changes unless a GitHub Issue for
this repository explicitly asks for that repository-maintenance work.

## Repository Map

- `.codex-plugin/plugin.json`: Plugin identity and component discovery.
- `skills/analyze-repo-for-kubernetes/SKILL.md`: Skill trigger boundary,
  high-level workflow, safety invariants, and routing instructions.
- `skills/analyze-repo-for-kubernetes/references/`: durable workflow, output,
  evidence, and contract references.
- `skills/analyze-repo-for-kubernetes/assets/`: Skill-local report templates and
  compatibility assets.
- `scripts/`: runtime-neutral deterministic helpers and validators shared by the
  Plugin.
- `contracts/`: machine-readable shared contracts when present.
- `mcp/`: thin local MCP transport adapters when present.
- `tests/`: unit and acceptance coverage for repository-analysis behavior.
- `validation/`: report and regression validation assets.
- `.github/`: GitHub issue, PR, and workflow configuration when present.

Read the relevant files before changing behavior. Do not duplicate detailed
system behavior in this file.

Resolve the Plugin root from repository-level scripts. The nested Skill root is
always `<Plugin root>/skills/analyze-repo-for-kubernetes`; Skill-local links stay
relative to that directory. Qwen compatibility updates must run
`scripts/update-qwen.sh` from the same Plugin checkout and preserve the symlink
to that nested Skill.

## Required Workflow

All substantive work follows this sequence:

1. Plan the work first.
2. Split the plan into vertical-slice GitHub Issues.
3. Register and manage those slices in this repository's GitHub Issues.
4. Implement one GitHub Issue at a time.
5. Before implementation edits, checkout a dedicated branch for that issue.
6. Commit issue work with the related GitHub Issue number included as `#<number>`.
7. Run focused validation before handoff.

Read-only investigation may happen on the shared checkout. Code, test, docs, and
workflow edits for an issue must happen on the issue branch.

## GitHub Issues and PRs

Write GitHub Issue and Pull Request titles, bodies, checklists, validation notes,
and review-request text in Korean.

Branch names may use ASCII English slugs for CLI compatibility.

Use GitHub Issues as the source of truth for planned vertical slices. If work is
too large for one reviewable issue, split it before implementation. If a follow-up
is discovered during implementation, create or propose a separate GitHub Issue
rather than expanding the current slice without agreement.

## Branch Rules

Never implement directly on `main`.

For each issue, create or checkout a dedicated branch before editing files. Prefer
an issue-linked branch when available:

```bash
gh issue develop <issue-number> --checkout --name issue/<issue-number>-<short-slug>
```

If `gh issue develop` is unavailable or blocked, use:

```bash
git switch -c issue/<issue-number>-<short-slug>
```

Do not mix unrelated issues on one branch. Do not carry unfinished work for one
issue into another issue's branch.

## Commit Rules

Every commit for issue work must include the related GitHub Issue number as
`#<issue-number>` in the subject or body.

Use a non-closing reference unless the explicit intent is to close the issue on
merge:

```text
feat: add trigger precision eval cases

refs #26
```

Only use closing keywords such as `fixes #<issue-number>` or
`closes #<issue-number>` when the PR is intended to close that issue.

Keep commits scoped to one vertical slice. If one commit needs multiple issue
numbers, re-check whether the work should be split.

## Implementation Rules

- Prefer existing repository patterns over new abstractions.
- Keep changes narrow and reviewable.
- Do not introduce unrelated refactors.
- Do not weaken analysis safety, read-only repository access, evidence
  traceability, or report validation contracts.
- Preserve deterministic behavior where tests or validators rely on normalized
  output.
- Do not commit secrets, credentials, tokens, `.env` files, generated caches, or
  local scratch artifacts.

## Validation

Run the smallest meaningful validation for the files changed. Common commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 scripts/validate_plugin_package.py .
python3 scripts/validate_regression.py .
```

If validation cannot run, report the exact command and the blocking error. Do not
claim tests passed unless they were actually run and passed.

## Documentation Rules

Update documentation when behavior, trigger boundaries, evidence contracts,
workflow steps, validation commands, or output formats change.

Keep AGENTS.md focused on how agents should work. Put detailed skill behavior in
the relevant reference file and link or route to it from SKILL.md when needed.

## Handoff Checklist

Before handing off issue work, report:

- GitHub Issue number.
- Branch name.
- Summary of changed behavior.
- Files changed.
- Validation commands run and results.
- Any blocked validation or follow-up issue needed.
