# Interview-First Intake

Use this intake before repository analysis when the target is not already actionable.

## Target Resolution Gate

Run this gate before any repository discovery tool call. The skill installation directory, current directory, `SKILL.md`, `references/`, `assets/`, `scripts/`, `tests/` and fixtures are not the analysis target.

If the user explicitly says “현재 저장소” or “현재 workspace,” resolve the current repository root. Otherwise require one concrete Repository URL or Local path.

When the target is absent, ask exactly:

```text
분석할 Repository URL 또는 Local path를 알려 주세요.
```

Stop the turn after asking. Do not use directory listing, file search, shell, Git or web tools to guess the target.

## Repository URL

Use the default branch unless the user supplied a branch, tag, commit or pull request. Continue when read-only access succeeds.

For a private repository, use only an existing authenticated connector, CLI session, credential helper, SSH agent or authenticated local checkout. Never ask for a password, token, private key or other credential value. If access fails, identify the failed access method and request safe authentication or an authenticated local checkout.

## Local Path

Resolve relative paths and verify that the path exists and is readable. Never replace a missing path with a similar path or the skill root. Do not follow a symlink outside the resolved analysis root.

## Resolved Scope

Before inventory, state:

```text
분석 대상: <type> | <resolved target> | revision: <branch/commit/default> | subdirectory: <path 또는 .>
```
