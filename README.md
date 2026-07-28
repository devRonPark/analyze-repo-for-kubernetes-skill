# analyze-repo-for-kubernetes Plugin

Qwen Code 또는 Codex가 애플리케이션 Repository를 Kubernetes 이관 관점에서 근거 기반으로 분석하도록 만드는 Codex Plugin입니다. 배포 단위는 저장소 전체이며, workflow Skill은 `skills/analyze-repo-for-kubernetes`에 있습니다.

현재 Plugin Packaging Foundation은 nested Skill 배포 경계만 제공합니다. Local MCP backend와 `.mcp.json` 등록은 후속 Tool Orchestration Slice에서 함께 추가됩니다.

분석 목적에 따라 출력 깊이를 자동으로 정합니다. 사용자가 전체 상세 보고서를 요청한 경우에만 상세 분석을 사용하고, 그 외에는 의사결정 중심의 기본 분석으로 진행합니다.

## 핵심 기능

- 원격 Git URL, local checkout 또는 source archive를 차례로 확인하는 Interview-first 흐름
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

## Qwen compatibility 설치

Qwen Code는 같은 Plugin checkout의 nested Skill을 compatibility 경로로 사용합니다. 저장소를 Plugin 소스 디렉터리에 clone합니다.

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

이 경로는 `<Plugin root>/skills/analyze-repo-for-kubernetes`를 가리키는 심볼릭 링크입니다.

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

업데이트 스크립트는 Plugin root에서 `git pull --ff-only`, Plugin 패키지 검사, 전체 테스트, Qwen compatibility 재설치를 차례로 실행합니다.

## 실행

대상 없이 호출하면 AskUserQuestion으로 애플리케이션 소스 코드 제공 방식을 먼저 묻고 해당 turn을 종료합니다. Codex에서는 `request_user_input` 도구를 사용해야 합니다. 이후 선택한 방식에 맞는 URL, Local path 또는 archive path를 다음 turn에서 요청합니다.

```text
/analyze-repo-for-kubernetes
```

정상적인 첫 응답:

```text
분석 대상 애플리케이션 소스 코드 제공 방식을 알려주세요.
- 원격 Git URL
- 로컬 checkout 경로
- 소스 압축 파일
```

`원격 Git URL`을 선택하면 `분석할 원격 Git URL을 알려주세요.`를, `로컬 checkout 경로`를 선택하면 `분석할 Local path를 알려주세요.`를, `소스 압축 파일`을 선택하면 archive path를 후속으로 질문합니다. 원격 URL에는 GitHub, GitLab 및 사내 Git server의 HTTPS 또는 SSH URL을 사용할 수 있습니다. 질문 후에는 사용자가 구체적인 대상을 입력할 때까지 파일이나 디렉터리를 탐색하지 않아야 합니다.

사용자가 source 제공 방식을 고르면 다음 turn에서 선택에 맞는 target 값만 묻습니다.

```text
분석할 원격 Git URL을 알려주세요.
```

```text
분석할 Local path를 알려주세요.
```

```text
분석할 소스 압축 파일의 Local path를 알려주세요.
```

source 제공 방식 질문과 target 값 질문은 같은 turn에 함께 묻지 않습니다. target 값이 확정될 때까지 파일이나 디렉터리를 탐색하지 않아야 합니다.

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

## Evidence cache

`scripts/repository_evidence.py`는 동일한 local checkout을 반복 분석할 때 파일별로 redacted evidence만 재사용하는 disposable local cache를 기본 사용한다. cache key는 정규화된 repository identity와 analysis root, 파일 content hash, evidence schema, language별 runtime extractor version, runtime signal 활성화 상태, rule fingerprint을 포함한다. 파일 stat은 탐색 최적화에만 쓰며 content hash가 재사용의 정확성 경계다.

cache는 분석 대상 repository 안에 쓰지 않으며 raw source body, LLM 판단, 최종 report를 저장하지 않는다. cache entry가 손상되거나 부분적으로 기록된 경우 해당 파일은 miss로 처리해 안전하게 다시 수집한다. cache를 사용하지 않아야 하는 실행에는 다음 옵션을 사용한다.

```bash
python3 scripts/repository_evidence.py /path/to/repository --no-cache --diagnostics
```

`--cache-dir <path>`로 disposable cache 위치를 지정할 수 있고, `--diagnostics`는 stderr에 `hit`, `miss`, `invalidated`, `corrupted`, `bypassed` 수를 출력한다. evidence JSON 자체에는 cache 상태를 넣지 않으므로 cached run과 clean run을 동일하게 비교할 수 있다.

## Runtime signal evidence

Scanner는 Node.js, Python, Java, Go source의 검토된 명시적 runtime construct에서만 configuration read, listener, outbound connection, writable path, background registration evidence를 수집한다. 이 결과는 `repository-evidence/v2`의 `provenance: EXTRACTED`로 기록하며, 기존 scanner/pattern evidence는 `INFERRED`로 기록한다. `status`는 source 사실의 확실성이며 provenance와 다른 메타데이터다.

주석, string literal, README, dependency declaration, test-only source, framework default는 runtime signal을 만들지 않는다. `--no-runtime-signals`를 사용하면 universal evidence를 유지한 채 이 추출기만 끈다. extractor가 한 파일에서 실패하면 scan은 계속되고, redacted diagnostic은 JSON의 `diagnostics.runtime_extraction` 및 per-file cache outcome에 보존된다.

## 패키지 검사와 테스트

```bash
python3 scripts/validate_plugin_package.py .
```

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

8개의 pinned 공개 OSS 저장소를 실제로 clone하여 repository root 전체를 정적 분석하는 통합 테스트는 네트워크를 사용하므로 기본 CI에서는 건너뜁니다. source·dependency·build는 실행하지 않으며, 필요할 때만 명시적으로 실행합니다.

```bash
RUN_OSS_REPOSITORY_E2E=1 PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_oss_repository_runs -v
```

```bash
python3 scripts/validate_regression.py tests/fixtures/regression/expected.json
```

`expected.json`는 기존 반복 출력 fixture schema를 검증합니다. 실제 repository-run 회귀 비교는 생성된 report를 먼저 검증한 뒤 normalized snapshot과 비교합니다.

```bash
python3 scripts/validate_regression.py tests/fixtures/regression/black_box_expected.json --actual-report tests/fixtures/regression/black_box_report.md --repo-root tests/fixtures/black_box_repo
```

```bash
python3 scripts/run_black_box_eval.py --repo tests/fixtures/black_box_repo --report tests/fixtures/regression/black_box_report.md --expected tests/fixtures/regression/black_box_expected.json --output black-box-result.json
```

### 전체 Plugin repository 평가

`scripts/run_repository_e2e_eval.py`는 pinned corpus manifest의 모든 저장소를 temporary directory에 checkout하고, 전체 Skill이 생성한 Markdown 보고서를 실제 checkout 기준으로 검증합니다. `--report-dir`에는 fixture ID와 같은 이름의 `<id>.md` 보고서를 두고, 선택한 `--expectations`에는 reviewed normalized expected facts를 둡니다. clone은 항상 `--allow-network`를 명시해야 합니다.

```bash
python3 scripts/run_repository_e2e_eval.py --manifest tests/fixtures/oss_runtime/manifest.json --report-dir /path/to/reports --expectations /path/to/expectations.json --allow-network --output repository-e2e-result.json
```

실제 Skill runtime을 연결할 때는 command가 Markdown report를 standard output으로 내보내야 하며, `--allow-live-runtime`도 명시해야 합니다. command는 checkout을 current working directory로 받고 `ANALYZE_REPO_FOR_KUBERNETES_TARGET`, `ANALYZE_REPO_FOR_KUBERNETES_FIXTURE_ID`, `ANALYZE_REPO_FOR_KUBERNETES_REPOSITORY_REVISION`, `ANALYZE_REPO_FOR_KUBERNETES_UPSTREAM`, `ANALYZE_REPO_FOR_KUBERNETES_REPORT_MODE`, `ANALYZE_REPO_FOR_KUBERNETES_PROMPT` 환경 변수를 받습니다. command가 checkout을 수정하거나 untracked file을 만들면 평가를 실패시킵니다.

```bash
python3 scripts/run_repository_e2e_eval.py --manifest tests/fixtures/oss_runtime/manifest.json --live-command '<Skill runtime command>' --allow-network --allow-live-runtime --output repository-e2e-result.json
```

expectations JSON은 manifest의 모든 fixture ID를 포함해야 합니다. 아래는 한 항목만 보인 축약 형식이며, 실제 file에는 나머지 fixture ID도 같은 수준으로 넣습니다.

```json
{
  "schema_version": 1,
  "comparison_fields": ["workload_candidates", "design_input_verdict"],
  "repositories": {
    "node-sql-pg": {
      "workload_candidates": [],
      "design_input_verdict": "추가 정보 필요"
    }
  }
}
```

## Codex Plugin 설치

Codex에서는 standalone Skill 복사가 아니라 Plugin을 설치합니다. 이 저장소는 개인 또는 팀 marketplace 파일을 포함하지 않으므로, 개발 중에는 Plugin root를 별도의 local marketplace에 등록한 뒤 Plugins Directory에서 설치합니다.

현재 Codex installer는 Plugin package를 검증하고 이 설치 경계를 안내할 뿐, `~/.agents/skills`, hook 또는 Codex 설정을 변경하지 않습니다.

```bash
bash scripts/install-codex.sh
```

과거 버전이 설치한 managed standalone Skill과 Target Gate hook만 migration cleanup으로 제거할 수 있습니다. 사용자 소유 cache와 다른 Skill은 제거하지 않습니다.

```bash
bash scripts/uninstall-codex.sh
```

대화형 Codex UI 검증 절차는 [codex-ui-integration.md](skills/analyze-repo-for-kubernetes/references/codex-ui-integration.md)를 따릅니다. 실제 CLI 검증은 인증된 환경에서만 opt-in으로 실행합니다.

```bash
CODEX_INTEGRATION=1 python3 scripts/validate_codex_intake.py
```

## Private Repository

인증 정보 자체를 Agent 대화에 입력하지 않습니다. 먼저 `gh auth`, Git credential helper, SSH agent 또는 인증된 local checkout으로 접근을 준비합니다. 데모에서만 [credential file example](skills/analyze-repo-for-kubernetes/assets/demo-git-credential.example.json)을 저장소 밖의 owner-only local file로 복사해 채울 수 있습니다. Agent에는 파일 경로만 제공하고, 파일 내용이나 Access Token은 제공하지 않습니다. 데모 후에는 파일을 삭제하거나 token을 폐기합니다.

## 저장소 관리 원칙

- `main`에는 테스트를 통과한 버전만 병합합니다.
- 기능 변경은 별도 branch와 Pull Request로 관리합니다.
- 버전은 `v0.1.0`, `v0.2.0` 형식의 Git tag로 관리합니다.
- GB10에는 ZIP을 반복 복사하지 않고 이 저장소를 clone한 뒤 업데이트 스크립트를 사용합니다.

## License

MIT
