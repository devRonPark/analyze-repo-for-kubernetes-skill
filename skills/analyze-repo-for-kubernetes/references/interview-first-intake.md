# Interview-First Intake

Use this intake before repository analysis to resolve the analysis target. It preserves the Interview-first AskUserQuestion flow when the target is not already actionable.

## Target Resolution Gate

Run this gate before any repository discovery tool call. The skill installation directory, current directory, `SKILL.md`, `references/`, `assets/`, `scripts/`, `tests/` and fixtures are not the analysis target.

Resolve target candidates in this order:

1. A concrete Target supplied as Slash Command Input.
2. A GitHub URL or Git URL in the natural-language request.
3. An explicit “현재 저장소” or “현재 workspace,” resolved to the current repository root.

Slash Command Input wins when it and the natural-language request contain different Targets. A natural-language GitHub URL or Git URL is already a concrete target and must not be requested again.

If the user explicitly says “현재 저장소” or “현재 workspace,” resolve the current repository root. Otherwise collect the source-code delivery method and then its concrete value. For remote Git authentication and archive handling, read [remote-git-access.md](remote-git-access.md).

Record `remote_git`, `local_checkout` or `source_archive` as the source-method state; never use a translated or display label as the branch key. For local checkout resolution, read [source-intake-state.md](source-intake-state.md).

When both the delivery method and target are absent, ask exactly one AskUserQuestion using Codex `request_user_input` when available:

```text
분석 대상 애플리케이션 소스 코드 제공 방식을 알려주세요.
- 원격 Git URL
- 로컬 checkout 경로
- 소스 압축 파일
```

Stop the turn after asking. Do not ask for the concrete target value in the same turn.

On the next turn, ask exactly one follow-up AskUserQuestion according to the selected source method:

- `remote_git` / 원격 Git URL: `분석할 원격 Git URL을 알려주세요.`
- `local_checkout` / 로컬 checkout 경로: `분석할 Local path를 알려주세요.`
- `source_archive` / 소스 압축 파일: `분석할 소스 압축 파일의 Local path를 알려주세요.`

The first source-method question and second target-value question never occur in the same turn. If the user supplies a delivery method and concrete value together, skip the follow-up question. Do not use directory listing, file search, shell, Git or web tools to guess the target while either question is unresolved.

Do not use directory listing, file search, shell, Git or web tools to guess the target before a concrete URL, Local path or archive path is supplied.

## Remote Git URL

Use the default branch unless the user supplied a branch, tag, commit or pull request. Continue when read-only access succeeds.

For a private repository, use only an existing authenticated connector, CLI session, credential helper, SSH agent, demo local credential file or authenticated local checkout. Never ask for a password, token, private key or credential file content. If access fails, identify the failed access method and use the authentication decision flow in [remote-git-access.md](remote-git-access.md).

## Local Path

Resolve relative paths and verify that the path exists and is readable. Never replace a missing path with a similar path or the skill root. Do not follow a symlink outside the resolved analysis root.

## Source Archive

Accept only ZIP, tar, tar.gz or tgz source archives supplied as an attachment or a concrete local archive path. Open the archive read-only. Do not execute archive content and do not follow archive entries that resolve outside the archive extraction root. Use the extraction rules in [remote-git-access.md](remote-git-access.md). Never treat the skill package or an arbitrary archive sibling directory as the analysis target.

## Resolved Scope

Before inventory, state:

```text
분석 대상: <type> | <resolved target> | revision: <branch/commit/default> | subdirectory: <path 또는 .>
```
