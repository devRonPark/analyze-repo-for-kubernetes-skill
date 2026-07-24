# Interview-First Intake

Use this intake before repository analysis to resolve the analysis target. It preserves the Interview-first AskUserQuestion flow when the target is not already actionable.

## Target Resolution Gate

Run this gate before any repository discovery tool call. The skill installation directory, current directory, `SKILL.md`, `references/`, `assets/`, `scripts/`, `tests/` and fixtures are not the analysis target.

Resolve target candidates in this order:

1. A concrete Target supplied as Slash Command Input.
2. A GitHub URL or Git URL in the natural-language request.
3. An explicit “현재 저장소” or “현재 workspace,” resolved to the current repository root.

Slash Command Input wins when it and the natural-language request contain different Targets. A natural-language GitHub URL or Git URL is already a concrete target and must not be requested again.

When the target is absent, ask exactly one AskUserQuestion using Codex `request_user_input` when available:

```text
소스를 어떻게 제공하시겠어요?
- Repository URL
- Local directory path
- Source archive
```

Stop the turn after asking. Do not ask for the concrete target value in the same turn.

On the next turn, ask exactly one follow-up AskUserQuestion according to the selected source method:

- Repository URL: `분석할 GitHub 또는 Git repository URL을 입력해 주세요.`
- Local directory path: `분석할 local directory path를 입력해 주세요.`
- Source archive: `분석할 ZIP, tar, tar.gz 또는 tgz archive path를 입력해 주세요.`

The first source-method question and second target-value question never occur in the same turn. Do not use directory listing, file search, shell, Git or web tools to guess the target while either question is unresolved.

## Repository URL

Use the default branch unless the user supplied a branch, tag, commit or pull request. Continue when read-only access succeeds.

For a private repository, use only an existing authenticated connector, CLI session, credential helper, SSH agent or authenticated local checkout. Never ask for a password, token, private key or other credential value. If access fails, identify the failed access method and request safe authentication or an authenticated local checkout.

## Local Path

Resolve relative paths and verify that the path exists and is readable. Never replace a missing path with a similar path or the skill root. Do not follow a symlink outside the resolved analysis root.

## Source Archive

Accept only ZIP, tar, tar.gz or tgz source archives supplied as an attachment or a concrete local archive path. Open the archive read-only. Do not execute archive content and do not follow archive entries that resolve outside the archive extraction root.

## Resolved Scope

Before inventory, state:

```text
분석 대상: <type> | <resolved target> | revision: <branch/commit/default> | subdirectory: <path 또는 .>
```
