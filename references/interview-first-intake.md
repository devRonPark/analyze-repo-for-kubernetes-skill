# Interview-First Intake

Use this intake before repository analysis to resolve the analysis target. It preserves the Interview-first AskUserQuestion flow when the target is not already actionable.

## Target Resolution Gate

Run this gate before any repository discovery tool call. The skill installation directory, current directory, `SKILL.md`, `references/`, `assets/`, `scripts/`, `tests/` and fixtures are not the analysis target.

Resolve target candidates in this order:

1. A concrete Target supplied as Slash Command Input.
2. A GitHub URL or Git URL in the natural-language request.
3. An explicit “현재 저장소” or “현재 workspace,” resolved to the current repository root.

Slash Command Input wins when it and the natural-language request contain different Targets. A natural-language GitHub URL or Git URL is already a concrete target and must not be requested again.

When the target is absent, ask exactly one AskUserQuestion:

```text
분석할 Git URL, Local path 또는 Source archive를 알려 주세요.
```

Stop the turn after asking. Do not use directory listing, file search, shell, Git or web tools to guess the target.

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
