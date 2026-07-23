# analyze-repo-for-kubernetes-skill

Qwen Code 또는 Codex가 애플리케이션 Repository를 Kubernetes 이관 관점에서 근거 기반으로 분석하도록 만드는 Agent Skill입니다.

기본 출력은 의사결정 중심의 `summary` 모드입니다. 사용자가 전체 분석을 명시한 경우에만 `detailed` 모드를 사용합니다.

## 핵심 기능

- Repository URL 또는 Local path를 먼저 확인하는 Interview-first 흐름
- 스킬 설치 경로를 분석 대상으로 오인하지 않게 하는 Target Resolution Gate
- Dockerfile 없는 Repository와 모노레포 분석
- 애플리케이션, Worker, Job, 정적 Frontend, Library 구분
- Build와 Runtime 동작, 포트, 설정, 스토리지 분석
- 관계별 실행 위치 분류
- 설정별 적용 시점 분류
- `확인됨`, `추정됨`, `미확인`, `상충됨` 근거 수준
- `준비됨`, `추가 정보 필요`, `진행 불가` 최종 판정
- 구성 요소별 역할·런타임·기동·포트·설정을 `key: value`와 파일·라인 근거로 브리핑
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

대상 없이 호출하면 구체적인 Repository URL 또는 Local path를 한 번에 요청해야 합니다.

```text
/analyze-repo-for-kubernetes
```

정상적인 첫 응답:

```text
분석할 Repository URL 또는 Local path를 알려 주세요.
```

질문 후에는 사용자가 대상을 입력할 때까지 파일이나 디렉터리를 탐색하지 않아야 합니다.

현재 Repository를 명시적으로 분석하려면 다음처럼 실행합니다.

```text
/analyze-repo-for-kubernetes
Use Local path: .
```

기본 Summary 요청:

```text
현재 Repository를 Kubernetes 이관 관점에서 summary 모드로 분석해.
결과를 kubernetes-migration-summary.md에 저장해.
Kubernetes manifest와 Dockerfile은 생성하지 마.
확인할 수 없는 정보는 미확인으로 표시해.
```

## 결과 검사

```bash
python3 scripts/validate_report.py kubernetes-migration-summary.md --mode summary
```

상세 보고서 검사:

```bash
python3 scripts/validate_report.py kubernetes-migration-assessment.md --mode detailed
```

## 패키지 검사와 테스트

```bash
python3 scripts/validate_skill.py .
```

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
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

## Private Repository

인증 정보 자체를 Agent 대화에 입력하지 않습니다. 먼저 `gh auth`, Git credential helper, SSH agent 또는 인증된 local checkout으로 접근을 준비한 후 Local path를 분석합니다.

## 저장소 관리 원칙

- `main`에는 테스트를 통과한 버전만 병합합니다.
- 기능 변경은 별도 branch와 Pull Request로 관리합니다.
- 버전은 `v0.1.0`, `v0.2.0` 형식의 Git tag로 관리합니다.
- GB10에는 ZIP을 반복 복사하지 않고 이 저장소를 clone한 뒤 업데이트 스크립트를 사용합니다.

## License

MIT
