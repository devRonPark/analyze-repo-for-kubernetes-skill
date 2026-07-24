# Interview-First Intake

Use this intake before repository analysis when the target is not already actionable.

## Target Resolution Gate

Run this gate before any repository discovery tool call. The skill installation directory, current directory, `SKILL.md`, `references/`, `assets/`, `scripts/`, `tests/` and fixtures are not the analysis target.

If the user explicitly says “현재 저장소” or “현재 workspace,” resolve the current repository root. Otherwise collect the source-code delivery method and then its concrete value. For remote Git authentication and archive handling, read [remote-git-access.md](remote-git-access.md).

When both the delivery method and target are absent, ask exactly:

```text
분석 대상 애플리케이션 소스 코드 제공 방식을 알려주세요.
- 원격 Git URL
- 로컬 checkout 경로
- 소스 압축 파일
```

Stop the turn after asking. When the user selects only `원격 Git URL`, ask exactly `분석할 원격 Git URL을 알려주세요.` in the next turn and stop. When the user selects only `로컬 checkout 경로`, ask exactly `분석할 Local path를 알려주세요.` in the next turn and stop. When the user selects only `소스 압축 파일`, ask exactly `분석할 소스 압축 파일의 Local path를 알려주세요.` in the next turn and stop. If the user supplies a delivery method and concrete value together, skip the follow-up question.

Do not use directory listing, file search, shell, Git or web tools to guess the target before a concrete URL, Local path or archive path is supplied.

## Remote Git URL

Use the default branch unless the user supplied a branch, tag, commit or pull request. Continue when read-only access succeeds.

For a private repository, use only an existing authenticated connector, CLI session, credential helper, SSH agent, demo local credential file or authenticated local checkout. Never ask for a password, token, private key or credential file content. If access fails, identify the failed access method and use the authentication decision flow in [remote-git-access.md](remote-git-access.md).

## Local Path

Resolve relative paths and verify that the path exists and is readable. Never replace a missing path with a similar path or the skill root. Do not follow a symlink outside the resolved analysis root.

## Source Archive

Use only the archive formats and extraction rules in [remote-git-access.md](remote-git-access.md). Never treat the skill package or an arbitrary archive sibling directory as the analysis target.

## Resolved Scope

Before inventory, state:

```text
분석 대상: <type> | <resolved target> | revision: <branch/commit/default> | subdirectory: <path 또는 .>
```
