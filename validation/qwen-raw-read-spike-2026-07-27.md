# Qwen raw-read vs evidence 경로 측정 보고서

## 분석 목적

`docs/superpowers/specs/2026-07-27-qwen-raw-read-spike-design.md`가 검증하려 한 가설은 다음과 같다.

> Qwen이 파일을 직접 고르면 evidence 경로보다 모델 context가 줄어든다.

이 가설이 참이면 sanitized checkout raw-read 방향으로 진행하고, 거짓이면 Decision Input 쪽을 강화한다.

## 실행 조건

- 실행 일자: 2026-07-27
- 대상 repository: `https://github.com/spring-projects/spring-petclinic`
- 대상 revision: `main @ f182358d02e4a68e52bdbabf55ca7800288511e7` (기존 baseline과 동일 커밋)
- 분석 목적: `전체 상세 보고서` (`full_repository_assessment` / `output_mode: detailed`)
- Runtime: Qwen Code `0.21.0`
- Model: `Qwen3-Coder-30B-A3B-Instruct` (sglang, `max_model_len=131072`)
- Endpoint: `http://172.16.4.249:30000/v1`
- 실행 제약: 대상 repository의 script, build, test, migration, server, container 명령은 실행하지 않고 정적 파일 탐색만 수행

두 arm의 입력은 배타적으로 유지했다.

| Arm | 입력 | cwd |
| --- | --- | --- |
| A. raw-read | 최소 sanitize된 workspace 경로만 | workspace |
| B. evidence | `scripts/repository_evidence.py` JSON만 | 빈 디렉터리 |

프롬프트의 나머지 부분은 두 arm이 글자 단위로 동일한 preamble을 공유한다. 차이는 입력 방식 문장뿐이다.

## Workspace 준비

| 항목 | 값 |
| --- | --- |
| clone 전체 파일 | 158 |
| sanitize 후 workspace 파일 | 119 |
| workspace 총 줄 수 | 27,399 |
| workspace 총 바이트 | 1,057,962 |
| scanner wall time | `195ms` |
| 수집된 evidence | 875건 |
| evidence JSON 크기 | 253,620 bytes |
| evidence JSON 정확한 token 수 | 72,004 |

`.git`, `node_modules`, `target`, `build`, `dist`, binary는 제외했다. 값 mask는 하지 않았다. 대상이 public repository이므로 결론에 영향이 없다.

evidence 875건 중 702건(80%)이 `config_key`였다.

## 측정 결과

| 항목 | Arm A (raw-read) | Arm B (evidence) |
| --- | ---: | ---: |
| wall time | `352,056ms` | `278,792ms` |
| `duration_ms` | `350,763` | `277,512` |
| `num_turns` | `54` | `1` |
| API requests | `55` | `2` |
| tool calls | `53` | `0` |
| `read_file` | `13` | `0` |
| `list_directory` | `11` | `0` |
| **input tokens** | **`1,822,966`** | **`169,057`** |
| output tokens | `5,517` | `1,288` |
| total tokens | `1,828,483` | `170,345` |
| 보고서 크기 | `5,200` bytes | `2,493` bytes |
| `validate_report.py` | 실패 (`22`건) | 실패 (`21`건) |
| `file:line` 인용 | `0` | `0` |

Arm A가 Arm B보다 input token을 **10.8배** 더 썼다.

## 계약 검증 결과

두 arm 모두 `validate_report.py --mode detailed`를 통과하지 못했다. 실패 항목은 거의 동일하다.

공통 실패:

- 필수 섹션 7개(`## 1. 평가 범위` ~ `## 7. 최종 판정`)가 모두 없음
- `file:line` 또는 `검색(...)` 근거를 찾을 수 없음
- 명시적인 최종 판정이 없음
- `한눈에 보기` 필수 키 6개 없음
- 의존성 필요 여부 필드 2개 없음
- 최종 판정 필수 구분 2개 없음

두 arm 모두 자기 나름의 섹션 구조를 만들었고, skill이 지정한 detailed template의 섹션명을 따르지 않았다. 인용은 파일명까지만 쓰고 line 번호를 붙이지 않았다.

## Arm A가 읽은 파일

119개 중 13개(11%)를 읽었다.

```text
README.md
pom.xml
build.gradle
docker-compose.yml
src/main/java/org/springframework/samples/petclinic/PetClinicApplication.java
src/main/resources/application.properties
src/main/resources/application-mysql.properties
src/main/resources/application-postgres.properties
.gitpod.yml
.devcontainer/Dockerfile
.devcontainer/devcontainer.json
k8s/petclinic.yml
k8s/db.yml
```

디렉터리는 11개를 탐색했다.

파일 선택 자체는 적절했다. Maven과 Gradle 공존, profile별 DB 설정, Compose 정의, Kubernetes manifest를 모두 포함했다. **raw-read 방식의 파일 선택 능력은 이번 실패의 원인이 아니다.**

## 보고서 내용 정확도

토큰을 적게 쓴 Arm B가 사실 관계에서 더 나빴다.

| 주장 | 저장소 실제 | 판정 |
| --- | --- | --- |
| Arm A: `Dockerfile 없음. Spring Boot build plugin을 사용한 이미지 빌드 가능`, `컨테이너화 필요` | 앱 Dockerfile 없음. `.devcontainer/Dockerfile`만 존재 | 정확 |
| Arm B: `컨테이너화되어 있으며, Dockerfile 및 devcontainer 구성이 존재 (k8s/petclinic.yml)` | 앱 Dockerfile 없음. 인용한 `k8s/petclinic.yml`은 Dockerfile 근거가 아님 | 오류 |
| Arm B: `CI/CD 시스템: GitHub Actions (k8s/workflows)` | `k8s/`에는 `db.yml`, `petclinic.yml`뿐. 실제 경로는 `.github/workflows` | 경로 날조 |

Arm B의 오류는 `references/workflow.md` 7절이 명시적으로 경고하는 실수다. development 도구인 devcontainer를 운영 환경 컨테이너화 근거로 승격했다.

Arm A는 같은 항목을 `Dockerfile 없음`과 `컨테이너화 필요`로 올바르게 분리했다.

## 부수 발견

### 1. 저사양 모델이 headless에서 purpose gate를 통과하지 못한다

첫 arm A 실행은 27.2초 만에 분석 없이 종료했다. skill을 로드한 직후 분석 목적을 되묻고 턴을 끝냈다.

```text
TOOL   skill {"skill": "analyze-repo-for-kubernetes"}
출력   이 분석 결과를 어디에 활용하시나요?
       - 빠른 구조 파악  - Kubernetes 설계 준비  ...
```

프롬프트에는 `목적: 전체 상세 보고서`가 명시되어 있었다. `references/source-intake-state.md`는 `전체 상세 보고서`를 explicit purpose로 규정하고 질문 없이 `analysis_ready`로 전이하라고 요구한다. 모델이 이 계약을 지키지 못했다.

측정값: wall `27,174ms`, turns `2`, tool calls `1`, `read_file` `0`, input tokens `42,662`, 보고서 `310 bytes`.

비대화형 실행에는 질문에 답할 주체가 없으므로 이 상태는 곧 실행 종료를 뜻한다. 본 측정은 "질문하지 말고 바로 분석하라"를 명시한 preamble을 두 arm에 동일하게 적용해 다시 실행했다.

### 2. tool 정의가 만드는 고정 비용

2줄짜리 YAML 하나를 읽는 최소 실행에서도 input token이 `30,268`개 들었다. `system/init` 이벤트의 `tools` 배열에 56개 도구가 등록되어 있다. 저장소 내용과 무관한 고정 비용이며, 매 API request마다 다시 실린다.

Arm A는 55 requests를 만들었으므로 이 고정 비용이 55번 누적됐다. 이것이 `1,822,966`의 주된 구성 요소다.

### 3. `input_tokens`는 요청 누적합이다

동일한 1턴 프롬프트를 6회 실행해 확인했다.

| API requests | input_tokens |
| ---: | ---: |
| 2 | 23,985 |
| 2 | 23,985 |
| 3 | 33,160 |
| 4 | 42,473 |
| 4 | 42,475 |
| 10 | 57,926 |

요청 수가 같으면 값도 정확히 같다. 값이 흔들리는 원인은 계측 오류가 아니라, 같은 프롬프트에도 모델이 만드는 요청 수가 2~10회로 달라지기 때문이다. `Reply with exactly the word OK` 프롬프트에 도구를 8번 호출한 실행도 있었다.

따라서 `input_tokens`는 총 context 소비량의 유효한 지표지만, **단일 실행 비교의 신뢰 구간은 좁지 않다.**

### 4. 셸 인자 길이 한계

Arm B 프롬프트는 255,799 bytes로 Linux `MAX_ARG_STRLEN`(131,072 bytes)을 초과해 `-p`로 전달할 수 없었다. `Argument list too long`으로 즉시 실패했다.

Arm B는 stdin으로 전달했다. Arm A는 `-p`를 썼다. 전달 채널이 token 수에 영향을 주는지 6회 probe로 확인했고, 차이는 채널이 아니라 요청 수에서 나온다는 것을 위 3항에서 확인했다.

## 참고치

기존 `validation/debug-bottleneck-analysis-2026-07-24.md`의 Codex 실행값이다.

| 항목 | 값 |
| --- | ---: |
| wall time | `408.93s` |
| input tokens | `1,320,986` |
| cached input tokens | `1,228,544` |

같은 저장소, 같은 커밋, 같은 목적이지만 **런타임이 다르므로 결론 근거로 쓰지 않는다.** 참고로만 기록한다. Arm A의 `1,822,966`은 이 값을 38% 상회한다.

## 판정

spec의 결정 규칙 중 **4행에 해당한다.**

> 둘 다 계약 통과 실패 → 문제는 방식이 아니라 저사양 모델의 detailed 계약 수행 능력. 계약 단순화가 다음 과제.

근거는 다음과 같다.

1. 두 arm 모두 `validate_report.py --mode detailed`를 통과하지 못했다. 실패 개수는 22건과 21건으로 사실상 동일하고, 실패 항목도 거의 겹친다.
2. 두 arm 모두 `file:line` 인용을 하나도 남기지 못했다. 입력 방식과 무관한 실패다.
3. 입력 방식을 바꿔도 계약 준수 여부는 달라지지 않았다. 따라서 이번 실패의 원인은 raw-read냐 evidence냐가 아니다.

동시에 **원래 가설은 기각되었다.**

> Qwen이 파일을 직접 고르면 evidence 경로보다 모델 context가 줄어든다.

Arm A는 119개 중 13개 파일만 읽고도 input token을 Arm B의 10.8배 썼다. 병목은 읽은 파일의 양이 아니라 agent step 수다. 각 step이 56개 tool 정의와 누적 대화를 다시 싣는다.

다만 이 수치는 arm당 1회 실행이고, 3항에서 확인한 요청 수 변동을 감안하면 배수의 정확한 크기는 재현 확인이 필요하다. 방향(evidence 경로가 더 적게 쓴다)은 10.8배라는 격차와 turn 수 차이(54 대 1)를 볼 때 편차로 뒤집히기 어렵다.

한편 Arm B는 토큰을 적게 쓰는 대신 **사실을 지어냈다.** 토큰 효율만으로 evidence 경로를 채택하면 정확도를 잃는다.

## 다음 단계

우선순위 순이다.

1. **detailed 출력 계약을 저사양 모델이 수행 가능한 수준으로 단순화한다.** 현재 계약은 섹션 7개, 표, dependency matrix, 최소 설계 입력, 필수 키 다수를 LLM이 동시에 만들도록 요구한다. 두 arm 모두 여기서 실패했다. `debug-bottleneck-analysis-2026-07-24.md`의 개선 우선순위 4항(detailed report assembly를 deterministic renderer로 이전)과 같은 결론이다.

2. **`file:line` 인용을 LLM이 만들지 않게 한다.** 두 arm 모두 인용에 실패했다. evidence가 이미 `path:line`을 들고 있으므로, 인용은 코드가 삽입하고 LLM은 판단 사유만 쓰게 한다.

3. **raw-read 단독 방향은 보류한다.** 파일 선택 능력은 확인됐지만(13/119, 적절한 선택) step 수 누적 비용이 크다. 채택하려면 step 수를 줄이는 장치가 먼저 필요하다.

4. **evidence 경로에 정확도 보강이 필요하다.** Arm B의 devcontainer 오승격과 경로 날조는 evidence만으로 판단할 때 나타나는 실패다. `references/workflow.md` 7절의 구분을 evidence 자체에 typed field로 넣는 것을 검토한다.

5. **tool 정의 56개를 줄인다.** `computer_use__*` 계열을 포함한 도구가 매 요청에 실린다. 이 skill 실행에 필요한 도구만 노출하면 고정 비용이 줄어든다.

## 재현 정보

spike 스크립트는 버리는 코드이므로 커밋하지 않았다. 재현에 필요한 정보는 다음과 같다.

- 계획: `docs/superpowers/plans/2026-07-27-qwen-raw-read-spike.md`
- 설계: `docs/superpowers/specs/2026-07-27-qwen-raw-read-spike-design.md`
- clone: `scripts/plain_remote_git_clone.py --url <url> --destination <dir> --revision f182358d02e4a68e52bdbabf55ca7800288511e7`
- sanitize: `scripts/repository_evidence.py`의 `resolve_roots`와 `walk_text_files`를 그대로 사용해 텍스트 파일만 복사
- evidence: `scripts/repository_evidence.py <clone> --output evidence.json`
- 실행: `qwen -p "<prompt>" -o json` 또는 프롬프트가 131,072 bytes를 넘으면 `qwen -o json < prompt.md`
- run record: `-o json` transcript의 `tool_use` 블록과 `result` 이벤트에서 추출
