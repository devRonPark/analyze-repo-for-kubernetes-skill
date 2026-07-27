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
| `validate_report.py` (최초) | 실패 (`22`건) | 실패 (`21`건) |
| `validate_report.py` (계약 감지 보정 후) | 실패 (`5`건) | 미측정 |
| 템플릿 섹션명 일치 | `8/8` | `1/8` (템플릿 접근 차단됨) |
| `file:line` 인용 | `0` | `0` |

Arm A가 Arm B보다 input token을 **10.8배** 더 썼다.

## 계약 검증 결과

두 arm 모두 `validate_report.py --mode detailed`를 통과하지 못했다. 그러나 최초 실패 개수 `22`건과 `21`건은 **validator의 계약 자동 감지 결함 때문에 크게 부풀려진 수치다.** 이 절은 정정된 내용을 담는다.

### validator의 계약 자동 감지 결함

`validate_report.py`는 두 벌의 detailed 계약을 갖고 있고, 보고서 본문에 `## 3. 배포 대상별 실행 정보`라는 정확한 문자열이 있는지로 둘 중 하나를 고른다(`validate_report.py:170, 238, 261, 307`).

| 계약 | 섹션명 | 저장소 템플릿과 일치 |
| --- | --- | --- |
| `NEW_DETAILED_SECTIONS` | `## 1. 분석 범위` ~ `## 8. Kubernetes 설계 입력 상태` | 일치 |
| `DETAILED_SECTIONS` | `## 1. 평가 범위` ~ `## 7. 최종 판정` | **어떤 템플릿과도 불일치** |

구 계약의 섹션명은 `assets/migration-assessment-template.md`에도 `assets/migration-summary-template.md`에도 없다. 즉 감지에 실패하면 보고서는 저장소가 가르치지 않는 계약으로 채점되고, 근거 없는 실패가 연쇄로 발생한다.

### Arm A는 템플릿을 사실상 따랐다

Arm A가 쓴 `##` 제목은 신 계약 섹션명 8개와 **전부 일치**하며, 빠진 것은 `N. ` 번호 접두사뿐이다.

```text
## 분석 범위                    → ## 1. 분석 범위
## 배포 대상 후보                → ## 2. 배포 대상 후보
## 배포 대상별 실행 정보          → ## 3. 배포 대상별 실행 정보
## 구성과 관계                  → ## 4. 구성과 관계
## 운영 환경 배포 근거            → ## 5. 운영 환경 배포 근거
## 설정과 상태 상세              → ## 6. 설정과 상태 상세
## 제외 항목과 설계 차단 항목 상세   → ## 7. 제외 항목과 설계 차단 항목 상세
## Kubernetes 설계 입력 상태     → ## 8. Kubernetes 설계 입력 상태
```

번호 접두사만 기계적으로 부여하고 다시 검증하면 실패가 **`22`건에서 `5`건으로** 줄어든다.

```text
실패: 명시적인 최종 판정이 없습니다
실패: file:line 또는 검색(...) 근거를 찾을 수 없습니다
실패: 구성 요소별 배포 브리핑에 구성 요소 카드가 없습니다
실패: 의존성 필요 여부 필드가 없습니다: 기능 실행에 필요
실패: 의존성 필요 여부 필드가 없습니다: 공급 또는 관리 경계
```

`22`건 중 `17`건은 감지 실패에서 파생된 허위 실패였다.

### Arm B의 구조 실패는 측정 설계 결함이다

Arm B는 신 계약 섹션명을 `1/8`만 맞췄고, 프롬프트의 완료 조건에서 자체 구조를 만들었다.

그러나 이 결과는 공정한 비교가 아니다. **본 측정은 Arm B에 파일 도구 사용을 금지했으므로, Arm B는 `assets/migration-assessment-template.md`를 읽을 수 없었다.** 템플릿은 분석 대상 저장소의 내용이 아니라 skill 자산이며, 실제 운용에서 evidence 경로가 템플릿을 못 읽을 이유는 없다.

따라서 **형식 준수 능력에 대한 두 arm의 비교는 이번 측정으로 성립하지 않는다.** 재측정 시 Arm B에도 skill 자산 읽기를 허용해야 한다.

### 두 arm 모두에서 실재하는 실패

- `file:line` 인용이 `0`건이다. 두 arm 모두 파일명까지만 쓰고 line 번호를 붙이지 않았다. evidence JSON은 875건 전부 `path:line`을 갖고 있으므로, 정보가 없어서가 아니라 전사 단계에서 소실됐다.
- 명시적인 최종 판정 형식을 맞추지 못했다.

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

spec의 결정 규칙 중 **4행에 해당한다.** 다만 그 4행의 원문 표현("저사양 모델의 detailed 계약 수행 능력")은 이번 측정 결과를 정확히 서술하지 못하므로 아래와 같이 한정한다.

> 둘 다 계약 통과 실패 → 문제는 입력 방식이 아니다. 다음 과제는 출력 계약 쪽이다.

근거는 다음과 같다.

1. 두 arm 모두 `validate_report.py --mode detailed`를 통과하지 못했다.
2. 두 arm 모두 `file:line` 인용을 하나도 남기지 못했다. 입력 방식과 무관한 실패이며, evidence에 `path:line`이 이미 존재하므로 정보 부족이 아니라 전사 실패다.
3. 입력 방식을 바꿔도 계약 준수 여부는 달라지지 않았다. 따라서 이번 실패의 원인은 raw-read냐 evidence냐가 아니다.

**단, "저사양 모델이 계약을 수행할 능력이 없다"고 결론지을 근거는 이번 측정에 없다.**

- Arm A는 템플릿 섹션명 8개를 전부 맞췄고, 번호 접두사만 부여하면 실패가 `22`건에서 `5`건으로 줄었다. 모델은 템플릿을 상당 부분 따를 수 있었다.
- 남은 `5`건 중 실질적인 것은 `file:line` 인용과 구성 요소 카드 구조다.
- Arm B의 구조 실패는 템플릿 접근을 막은 측정 설계 결함에서 비롯되었으므로 모델 능력의 증거로 쓸 수 없다.

즉 이번 결과가 가리키는 것은 모델 능력의 한계가 아니라, **형식 생성과 인용 전사를 LLM에게 맡긴 구조의 취약성**과 **validator 계약 감지의 결함**이다.

동시에 **원래 가설은 기각되었다.**

> Qwen이 파일을 직접 고르면 evidence 경로보다 모델 context가 줄어든다.

Arm A는 119개 중 13개 파일만 읽고도 input token을 Arm B의 10.8배 썼다. 병목은 읽은 파일의 양이 아니라 agent step 수다. 각 step이 56개 tool 정의와 누적 대화를 다시 싣는다.

다만 이 수치는 arm당 1회 실행이고, 3항에서 확인한 요청 수 변동을 감안하면 배수의 정확한 크기는 재현 확인이 필요하다. 방향(evidence 경로가 더 적게 쓴다)은 10.8배라는 격차와 turn 수 차이(54 대 1)를 볼 때 편차로 뒤집히기 어렵다.

한편 Arm B는 토큰을 적게 쓰는 대신 **사실을 지어냈다.** 토큰 효율만으로 evidence 경로를 채택하면 정확도를 잃는다.

## 다음 단계

우선순위 순이다.

1. **`validate_report.py`의 계약 자동 감지를 고친다.** 현재는 `## 3. 배포 대상별 실행 정보` 정확 일치로 계약을 고르고, 실패하면 저장소의 어떤 템플릿과도 일치하지 않는 구 계약으로 조용히 폴백해 허위 실패를 대량 생성한다. 최소한 다음이 필요하다.
   - 번호 접두사를 무시하고 섹션명으로 매칭한다.
   - 감지된 계약을 출력에 명시한다.
   - 배포 자산에 대응하지 않는 구 계약은 제거하거나 명시적 플래그로만 선택하게 한다.

   이 결함 때문에 이번 측정의 최초 실패 개수가 4배 이상 부풀려졌다.

2. **형식 생성을 deterministic renderer로 옮긴다.** 현재 `scripts/`에는 renderer가 없고, LLM이 121줄 템플릿을 읽고 섹션·표·인용을 직접 조립한 뒤 `validate_report.py`가 사후 채점만 한다. 섹션 구조와 표는 코드가 만들고 LLM에는 판단과 사유만 남긴다. `debug-bottleneck-analysis-2026-07-24.md`의 개선 우선순위 4항과 같은 결론이며, 이번 측정은 성능이 아니라 정확도 근거를 추가한다.

3. **`file:line` 인용을 LLM이 만들지 않게 한다.** 두 arm 모두 인용에 실패했다. evidence가 이미 `path:line`을 들고 있으므로 인용은 코드가 삽입한다. 2항 renderer의 일부로 다룬다.

4. **raw-read 단독 방향은 보류한다.** 파일 선택 능력은 확인됐지만(13/119, 적절한 선택) step 수 누적 비용이 크다. 채택하려면 step 수를 줄이는 장치가 먼저 필요하다.

5. **evidence 경로에 정확도 보강이 필요하다.** Arm B의 devcontainer 오승격과 경로 날조는 evidence만으로 판단할 때 나타나는 실패다. `references/workflow.md` 7절의 구분을 evidence 자체에 typed field로 넣는 것을 검토한다.

6. **tool 정의 56개를 줄인다.** `computer_use__*` 계열을 포함한 도구가 매 요청에 실린다. 이 skill 실행에 필요한 도구만 노출하면 고정 비용이 줄어든다.

7. **재측정 시 Arm B에 skill 자산 읽기를 허용한다.** 이번 측정은 파일 도구를 전면 금지해 템플릿 접근까지 막았다. 금지 대상은 분석 대상 저장소여야 하고 skill 자산은 아니다.

## 재현 정보

spike 스크립트는 버리는 코드이므로 커밋하지 않았다. 재현에 필요한 정보는 다음과 같다.

- 계획: `docs/superpowers/plans/2026-07-27-qwen-raw-read-spike.md`
- 설계: `docs/superpowers/specs/2026-07-27-qwen-raw-read-spike-design.md`
- clone: `scripts/plain_remote_git_clone.py --url <url> --destination <dir> --revision f182358d02e4a68e52bdbabf55ca7800288511e7`
- sanitize: `scripts/repository_evidence.py`의 `resolve_roots`와 `walk_text_files`를 그대로 사용해 텍스트 파일만 복사
- evidence: `scripts/repository_evidence.py <clone> --output evidence.json`
- 실행: `qwen -p "<prompt>" -o json` 또는 프롬프트가 131,072 bytes를 넘으면 `qwen -o json < prompt.md`
- run record: `-o json` transcript의 `tool_use` 블록과 `result` 이벤트에서 추출
