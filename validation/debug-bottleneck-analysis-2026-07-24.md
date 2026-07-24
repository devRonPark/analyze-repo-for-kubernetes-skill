# analyze-repo-for-kubernetes Debug 병목 분석 보고서

## 분석 목적

저사양 모델에서 `$analyze-repo-for-kubernetes` skill을 실행할 때 안정적인 처리 시간을 보장하기 위해, `debug mode` 성격의 black-box 실행으로 가장 오래 걸리는 병목 지점을 확인했다.

## 실행 조건

- 실행 일자: 2026-07-24
- Source method: GitHub
- Target repository: `https://github.com/spring-projects/spring-petclinic`
- Target revision: `main @ f182358d02e4a68e52bdbabf55ca7800288511e7`
- 분석 목적: `전체 상세 보고서`
- 내부 해석: `full_repository_assessment` / `output_mode: detailed`
- 실행 제약: 대상 repository의 `script`, `build`, `test`, `server`, `container` 명령은 실행하지 않고 정적 파일 탐색만 수행
- 측정 방식: `codex exec --json` 이벤트와 단계별 `date +%s%3N` marker 기반 측정

## 전체 실행 결과

- 전체 wall time: `408.93s`
- Codex usage:
  - `input_tokens=1,320,986`
  - `cached_input_tokens=1,228,544`
  - `output_tokens=17,589`
  - `reasoning_output_tokens=10,623`
- 명시적으로 timestamp를 찍은 phase 합계: 약 `56.7s`
- 결론: deterministic scanner 자체보다 모델 호출 간 누적 context 처리, LLM triage, detailed 출력 조립이 주요 병목이다.

## 단계별 측정값

| 단계 | 시간 | 비고 |
|---|---:|---|
| Universal Scanner | `28ms` | `rg --files`, `rg -n`; 총 114개 파일에서 manifest/config/entrypoint 후보 수집 |
| Evidence Pattern Packs | `54ms` | Docker/Compose/Kubernetes/Java/config/platform hint 정적 조회 |
| 보조 evidence read | `10ms` | key file line count와 selected evidence hit count 확인 |
| Deterministic Verifier | `168ms` | citation check, absence check, secret-name-only check, worktree clean check |
| LLM triage/reasoning | `29.393s` | evidence 기반 deployable/runtime dependency/excluded 항목 의미 분리 |
| Report assembly | `12.712s` | debug timing report 조립. Kubernetes detailed 본문은 출력하지 않음 |
| GitHub access | 약 `7s` marker 기준 | 실제 `git ls-remote` process wall은 약 `370ms`; Codex tool dispatch 포함 |
| Clone/fetch | 약 `7s` marker 기준 | 실제 shallow clone process wall은 약 `598ms`; Codex tool dispatch 포함 |

## 병목 Top 3

### 1. 모델 context 증폭

가장 큰 구조적 병목은 전체 wall time과 phase 합계 사이의 차이다.

- 전체 wall time은 `408.93s`
- timestamp로 직접 측정한 주요 phase 합계는 약 `56.7s`
- 누적 input token은 `1,320,986`

`SKILL.md`, 여러 reference 문서, raw command output, `pom.xml` 전체 구간, Kubernetes manifest, DB seed/schema grep 결과가 반복적으로 모델 context에 들어가면서 저사양 모델에서 처리 시간이 크게 증가한다.

### 2. LLM triage/reasoning

명시 측정 phase 중 가장 오래 걸린 구간은 `LLM triage/reasoning`이다.

- 측정값: `29.393s`
- 주요 작업:
  - Spring Boot Java 앱을 배포 대상 후보로 분리
  - Maven/Gradle 공존을 build/runtime 판단에서 보존
  - Compose DB와 Kubernetes DB manifest를 운영 baseline으로 혼동하지 않도록 분리
  - profile별 H2/MySQL/PostgreSQL 설정을 runtime dependency 판단과 구분

이 구간은 semantic judgment가 필요한 영역이지만, raw evidence가 과도하면 저사양 모델에서 안정 시간이 깨진다.

### 3. Detailed report assembly

상세 보고서 모드의 출력 계약을 맞추는 report assembly도 큰 비용이다.

- 측정값: `12.712s`
- 원인:
  - detailed schema가 섹션, 표, dependency matrix, text graph, 최소 설계 입력, 차단 항목을 모두 요구함
  - LLM이 형식과 판단을 동시에 수행함
  - 출력량이 커질수록 verifier 이전의 초안 생성 비용이 증가함

## deterministic 단계 평가

정적 scanner와 verifier는 병목이 아니었다.

- Universal Scanner: `28ms`
- Evidence Pattern Packs: `54ms`
- 보조 evidence read: `10ms`
- Deterministic Verifier: `168ms`

따라서 우선 최적화 대상은 `rg`/파일 탐색 속도가 아니라, scanner output을 모델에 전달하는 방식과 LLM이 담당하는 작업 범위다.

## 부수 발견

debug 실행 중 secret 관련 line evidence가 raw output에 포함될 수 있음을 확인했다.

- 예: `k8s/db.yml`의 `stringData`, `password` key line
- 문제: verifier 이후 redaction만으로는 늦다.
- 개선 방향: scanner 출력 단계에서 secret value를 즉시 redaction하고, LLM context에는 secret key name과 사용 위치만 전달해야 한다.

## 개선 우선순위

1. Raw file snippet 대신 compact typed facts를 모델에 전달한다.
   - 예: `component_candidate`, `config_key`, `dependency_edge`, `manifest_resource`, `absence_evidence`

2. 파일 read에 hard cap을 둔다.
   - `pom.xml` 전체 440줄 같은 입력을 피하고 필요한 line window만 읽는다.
   - DB seed/data SQL, static asset, test source는 기본 scan에서 제외한다.

3. tool call 수를 줄인다.
   - 현재 debug 실행은 다수의 `sed`, `rg`, `nl`, `awk`, `date` 호출을 만들었다.
   - `scanner -> verifier -> renderer` 정도의 deterministic command 3-5개로 줄이는 것이 좋다.

4. detailed report assembly를 deterministic renderer로 옮긴다.
   - LLM은 `판단 사유`, `추정됨`, `미확인`, `상충됨` 설명만 채운다.
   - Markdown section, table, citation format은 코드가 생성한다.

5. GitHub 접근을 cache한다.
   - cache key: `(repository URL, commit, subdirectory, scanner version)`
   - 재실행 시 clone/fetch를 생략한다.
   - 새 분석에서는 `git ls-remote`와 `clone`을 분리하지 말고 shallow clone 후 `rev-parse HEAD`로 revision을 확정한다.

6. 스킬 reference bootstrap을 줄인다.
   - 매 실행마다 전체 reference를 모델에 넣지 않는다.
   - target language와 발견된 artifact에 맞는 reference만 lazy-load한다.
   - detailed mode에서도 unused language pack은 읽지 않는다.

## 최종 판단

저사양 모델에서 안정적인 처리 시간을 보장하려면 scanner 성능보다 다음 두 가지가 우선이다.

- LLM context에 들어가는 raw evidence 양을 강하게 제한한다.
- detailed report 형식 생성과 검증을 deterministic code로 이동한다.

현재 구조에서는 작은 repository인 `spring-petclinic`에서도 전체 wall time이 `408.93s`까지 증가했다. 이는 repository 크기보다 agent step 수와 누적 context 크기가 처리 시간을 지배한다는 신호다.
