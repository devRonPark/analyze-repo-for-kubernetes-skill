# analyze-repo-for-kubernetes-skill

Qwen Code 또는 Codex가 애플리케이션 Repository를 Kubernetes 이관 관점에서 근거 기반으로 분석하도록 만드는 Agent Skill입니다.

분석 목적에 따라 출력 깊이를 자동으로 정합니다. 사용자가 전체 상세 보고서를 요청한 경우에만 상세 분석을 사용하고, 그 외에는 의사결정 중심의 기본 분석으로 진행합니다.

## 핵심 기능

- Git URL, Local path 또는 Source archive를 먼저 확인하는 Interview-first 흐름
- 스킬 설치 경로를 분석 대상으로 오인하지 않게 하는 Target Resolution Gate
- Dockerfile 없는 Repository와 모노레포 분석
- 배포 대상 후보, 저장소에 정의된 런타임 의존성, 외부 런타임 의존성, 제외 항목 구분
- Build와 Runtime 동작, 포트, 설정, 스토리지 분석
- 관계별 실행 위치 분류
- 설정별 적용 시점 분류
- `확인됨`, `추정됨`, `미확인`, `상충됨` 근거 수준
- `설계 입력 충분`, `추가 정보 필요`, `분석 불가` Kubernetes 설계 입력 상태
- 배포 대상별 실행 정보·런타임·기동·포트·설정을 `key: value`와 파일·라인 근거로 브리핑
- 저장소에서 확인한 기동 정의와 운영 환경 배포 근거를 분리
- 확인된 저장소 값과 명시적으로 추정한 Kubernetes 최소 설계 입력
- 파일 부재를 관련 없는 라인 대신 `검색(scope=..., pattern=..., result=없음)`으로 기록
- Repository prompt injection 방어와 read-only 기본 동작
- 분석 결과 정적 검사기

## Qwen Code 설치

저장소를 스킬 소스 디렉터리에 clone합니다.

```bash
git clone https://github.com/devRonPark/analyze-repo-for-kubernetes-skill.git ~/skills-src/analyze-repo-for-kubernetes-skill
```

```bash
cd ~/skills-src/analyze-repo-for-kubernetes-skill
```

패키지 검사와 심볼릭 링크 설치를 실행합니다.

```bash
bash scripts/install-qwen.sh
```

기본 설치 위치:

```text
~/.qwen/skills/analyze-repo-for-kubernetes
```

Qwen Code를 새로 시작한 뒤 스킬을 확인합니다.

```bash
qwen
```

```text
/skills
```

목록에 `analyze-repo-for-kubernetes`가 보여야 합니다.

## 업데이트

로컬 변경 사항이 없는 상태에서 실행합니다.

```bash
cd ~/skills-src/analyze-repo-for-kubernetes-skill
```

```bash
bash scripts/update-qwen.sh
```

업데이트 스크립트는 `git pull --ff-only`, 패키지 검사, 전체 테스트, Qwen Code 재설치를 차례로 실행합니다.

## 실행

대상 없이 호출하면 AskUserQuestion으로 구체적인 Git URL, Local path 또는 Source archive를 한 번만 요청하고 해당 turn을 종료합니다.

```text
/analyze-repo-for-kubernetes
```

정상적인 첫 응답:

```text
분석할 Git URL, Local path 또는 Source archive를 알려 주세요.
```

질문 후에는 사용자가 대상을 입력할 때까지 파일이나 디렉터리를 탐색하지 않아야 합니다.

GitHub URL이 포함된 자연어 요청은 URL을 다시 묻지 않고 바로 Target으로 사용합니다.

```text
https://github.com/example/payments-service 를 Kubernetes 설계 준비에 활용할 수 있게 분석해.
```

Slash Command Input으로 Target을 제공할 수도 있습니다. Input Target은 자연어에 다른 Target이 함께 있어도 우선합니다.

```text
/analyze-repo-for-kubernetes https://github.com/example/payments-service.git
```

```text
/analyze-repo-for-kubernetes /workspace/payments-service
```

```text
/analyze-repo-for-kubernetes /downloads/payments-service.tar.gz
```

Source archive는 ZIP, tar, tar.gz, tgz를 지원하며 read-only로 분석합니다. 현재 Repository를 명시적으로 분석하려면 Slash Command Input에 `.`을 제공합니다.

```text
/analyze-repo-for-kubernetes .
```

Target은 있지만 활용 목적이 모호하면 다음 한 번의 질문으로 맥락을 수집합니다.

```text
이 분석 결과를 어디에 활용하시나요?
- 빠른 구조 파악
- Kubernetes 설계 준비
- 이관 문제점 점검
- 전체 상세 보고서
- 기본 분석으로 진행
```

Kubernetes 설계 준비, 이관 문제점 점검 또는 전체 상세 보고서처럼 목적이 요청에 명확하면 이 질문 없이 분석을 시작합니다. 사용자는 출력 형식이나 내부 provider·phase를 선택할 필요가 없습니다.

## 결과 검사

```bash
python3 scripts/validate_report.py kubernetes-migration-summary.md --mode summary --repo-root /path/to/analyzed-repository
```

상세 보고서 검사:

```bash
python3 scripts/validate_report.py kubernetes-migration-assessment.md --mode detailed --repo-root /path/to/analyzed-repository
```

## 패키지 검사와 테스트

```bash
python3 scripts/validate_skill.py .
```

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

```bash
python3 scripts/validate_regression.py tests/fixtures/regression/expected.json
```

## Codex 설치

macOS, Linux, WSL 또는 Git Bash:

```bash
bash scripts/install-codex.sh
```

기본 설치 위치:

```text
~/.agents/skills/analyze-repo-for-kubernetes
```

Codex CLI의 stable hooks 기능이 있으면 설치 스크립트는 `~/.codex/config.toml`에 이 skill만을 위한 `UserPromptSubmit` + `PreToolUse` Target Gate를 등록합니다. 등록 후 설정 검증이 실패하면 기존 설정을 복구하고 설치를 실패로 처리합니다. Codex가 처음 등록한 user hook은 `/hooks`에서 검토·신뢰해야 실행됩니다. 신뢰된 hook은 Target 미확정 상태의 로컬 repository 탐색을 차단하며, 없는 환경에서는 스킬 지시만 적용됩니다. Codex hosted web 도구는 현재 `PreToolUse` 대상이 아니므로 web 탐색 금지는 스킬 지시로 유지됩니다.

WSL에서 Codex가 Windows profile을 Codex home으로 사용하면 설치 스크립트는 기존 `USERPROFILE/.codex`를 자동 선택한다. 필요한 경우 `CODEX_CONFIG_DIR`로 hook을 등록할 Codex home을 명시할 수 있다.

테스트 등으로 hook 등록을 명시적으로 건너뛰려면 다음처럼 실행합니다.

```bash
CODEX_SKIP_HOOK=1 bash scripts/install-codex.sh
```

제거 시에는 이 skill이 관리한 hook과 intake cache만 제거합니다.

```bash
bash scripts/uninstall-codex.sh
```

대화형 Codex UI 검증 절차는 [codex-ui-integration.md](references/codex-ui-integration.md)를 따릅니다. 실제 CLI 검증은 인증된 환경에서만 opt-in으로 실행합니다.

```bash
CODEX_INTEGRATION=1 python3 scripts/validate_codex_intake.py
```

## Private Repository

인증 정보 자체를 Agent 대화에 입력하지 않습니다. 먼저 `gh auth`, Git credential helper, SSH agent 또는 인증된 local checkout으로 접근을 준비한 후 Local path를 분석합니다.

## 저장소 관리 원칙

- `main`에는 테스트를 통과한 버전만 병합합니다.
- 기능 변경은 별도 branch와 Pull Request로 관리합니다.
- 버전은 `v0.1.0`, `v0.2.0` 형식의 Git tag로 관리합니다.
- GB10에는 ZIP을 반복 복사하지 않고 이 저장소를 clone한 뒤 업데이트 스크립트를 사용합니다.

## License

MIT
