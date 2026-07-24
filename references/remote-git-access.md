# Remote Git and Demo Credential File Access

Use this reference when the analysis source is not already a readable local checkout.

## AskUserQuestion Flow

First ask exactly:

```text
분석 대상 애플리케이션 소스 코드 제공 방식을 알려주세요.
- 원격 Git URL
- 로컬 checkout 경로
- 소스 압축 파일
```

Ask one value question only after the user selects a method:

| Method | Question |
| --- | --- |
| 원격 Git URL | `분석할 원격 Git URL을 알려주세요.` |
| 로컬 checkout 경로 | `분석할 애플리케이션 소스의 Local path를 알려주세요.` |
| 소스 압축 파일 | `분석할 소스 압축 파일의 Local path를 알려주세요. 지원 형식: .zip, .tar.gz, .tgz` |

Do not ask for provider, revision, subdirectory or authentication before the concrete source is supplied. Detect the provider from the URL host, resolve the default branch, and identify a repository root automatically. Ask for revision or subdirectory only when automatic resolution has multiple valid candidates.

## Remote Git URL

Accept HTTPS or SSH URLs for GitHub, GitLab, GitHub Enterprise, GitLab Self-Managed and other internal Git servers. Reject URLs that contain a username, password or token. First attempt read-only access through an existing credential helper, authenticated CLI session or SSH agent.

If anonymous and existing authenticated access both fail, ask exactly:

```text
원격 Git 저장소에 인증이 필요합니다. 인증값을 대화에 입력하지 말고 접근 방식을 선택해 주세요.
- 현재 환경에 구성된 Git 인증 사용
- 데모용 local credential file 경로 제공
- local checkout 또는 source archive로 제공
```

The first choice means the user configures their credential helper, CLI session or SSH agent outside the conversation and then requests a retry. The third choice returns to the source-code delivery method question.

## Demo Local Credential File

Use this temporary option only for a demo when a secure credential store is unavailable. Ask exactly:

```text
데모용 Git 인증 파일의 Local path를 알려주세요. 파일 내용이나 Access Token은 대화에 입력하지 마세요.
```

The user creates one file from [demo-git-credential.example.json](../assets/demo-git-credential.example.json), outside the repository being analyzed and outside the skill package. It must represent exactly one HTTPS repository, have no symlink, and be readable only by the account that runs Git. The agent passes its path only to a Git credential helper; it never opens, searches, quotes or reports the file content.

Use [demo_git_readonly_clone.py](../scripts/demo_git_readonly_clone.py) for this file. The script verifies that `repository_url` exactly matches the requested URL, passes `username` and `access_token` only to Git's credential protocol for this read-only Git request, avoids putting either value in a command line or remote URL, and redacts authentication errors. Invoke only its `clone` subcommand; never invoke its `get` subcommand directly because Git calls it internally.

```text
python3 scripts/demo_git_readonly_clone.py clone --url <HTTPS Git URL> --credential-file <credential file path> --destination <new disposable directory>
```

Delete the file immediately after the demo or revoke the token.

Do not use this file for SSH URLs, multiple repositories, write operations, or production automation. For GitHub, use a repository-limited read-only token; for GitLab, use a project or group token with `read_repository` only.

## Source Archive

Accept only `.zip`, `.tar.gz` and `.tgz` files. Extract them into a disposable analysis directory, reject path traversal and symlinks outside that directory, and never execute archive contents. Detect a single repository root automatically; ask for an archive subdirectory only when multiple roots are plausible.
