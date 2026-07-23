# Interview-First Intake

Use this intake before repository analysis when the target is not already explicit. Ask one question at a time and stop as soon as the analysis target is actionable.

## Target Resolution Gate

Run this gate before any repository discovery tool call. The skill installation directory is not the analysis target. `SKILL.md`, `references/`, `assets/`, `scripts/`, `tests/`, and `tests/fixtures` are implementation metadata.

Until one concrete Repository URL or Local path is known:

- do not call `list_directory`, `read_file`, `glob`, `grep`, shell, Git, or web tools
- do not infer the target from the current working directory
- do not inspect the skill package or fixture repositories
- ask the next intake question and stop the turn after asking

## First Question

```text
분석 대상은 어디에 있나요?
1. Repository URL
2. Local path
```

If the user already supplied a target, do not ask for the target again.

## Repository URL

Ask for the URL, then use the default branch unless a branch, tag, commit, or pull request was supplied. Public repositories continue immediately when access succeeds.

A private repository requires an existing safe access path such as a GitHub connector, authenticated `gh auth` session, Git credential helper, SSH agent, or authenticated local checkout. Do not ask the user to paste credentials, passwords, tokens, or private keys. When access fails, explain the failed access method and ask the user to authenticate safely or provide an authenticated local checkout.

## Local Path

Ask for the concrete Local path. Resolve `~`, environment variables, and relative paths. Verify that the path exists and is readable. Use the current checkout unless another revision was supplied. Never replace a missing path with a similar path or the skill root.

## Resolved Scope

Before analysis, state one line containing Source type, Repository URL or local path, Access method, resolved root, branch or commit, and analyzed subdirectory.
