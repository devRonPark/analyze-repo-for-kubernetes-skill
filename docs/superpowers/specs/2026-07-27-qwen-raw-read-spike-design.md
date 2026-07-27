# Qwen raw-read spike 설계

- 작성일: 2026-07-27
- 관련 Issue: #58
- 상태: 승인됨

## 문제

`analyze-repo-for-kubernetes` skill을 Qwen 런타임으로 확장하는 방향에서 두 가지 설계가 경쟁한다.

- **Decision Input**: deterministic scanner가 typed evidence를 만들고 모델은 그 evidence만 본다. `scripts/repository_evidence.py`(765줄)로 이미 절반 이상 구현되어 있다.
- **Raw-read**: sanitized checkout을 주고 모델이 필요한 파일을 직접 고른다.

Raw-read 방향은 검증되지 않은 가설 하나 위에 서 있다.

> Qwen이 파일을 직접 고르면 evidence 경로보다 모델 context가 줄어든다.

`validation/debug-bottleneck-analysis-2026-07-24.md`가 확인한 병목은 모델 context 증폭이다. 전체 wall time `408.93s` 중 명시 측정된 phase 합은 약 `56.7s`였고, 누적 input token은 `1,320,986`이었으며, scanner 자체는 `28ms`였다. Agent가 탐색하며 파일을 읽으면 step마다 context가 누적되므로 이 병목은 줄어들 수도 커질 수도 있다.

가설이 검증되지 않은 상태에서 sanitizer 정책, 공용 정책 모듈, read log 추출 방식을 먼저 설계하면 모든 결정이 추측 위에 얹힌다.

## 확정된 방향

Qwen 경로에 대해 다음이 합의되었다. 이 spike는 그 방향의 전제를 검증한다.

| 항목 | 결정 |
| --- | --- |
| scanner와의 관계 | Qwen 경로는 scanner를 대체한다 (raw-read only) |
| output 계약 | 기존 계약 유지. `assets/` 템플릿과 `scripts/validate_report.py`를 그대로 통과해야 한다 |
| sanitize 정책 | 타입별 분기. text config는 파일을 남기고 value만 mask하여 key 이름과 line 번호를 보존하고, binary credential은 placeholder로 대체한다 |
| 경계 강제 | sanitize가 유일한 hard boundary. hook을 걸지 않고 read log는 사후 기록으로만 쓴다 |
| gate 기록 | 실행당 JSON run record. 자동 임계값 없이 수동 판단 |

sanitize 정책과 gate 기록의 정식 구현은 이 spike의 범위가 아니다. spike 결과가 raw-read 방향을 지지할 때 본 설계에서 다룬다.

## Spike 설계

### 산출물

산출물은 코드가 아니라 숫자와 판단이다.

- 커밋 대상: `validation/qwen-raw-read-spike-2026-07-27.md` 측정 보고서
- 커밋하지 않음: spike 스크립트. scratchpad에만 두고 버린다

`validation/debug-bottleneck-analysis-2026-07-24.md`가 같은 형태의 산출물이므로 저장소 관례와 일치한다.

### 측정 arm

기존 `408.93s` baseline은 Codex 실행값이다. 여기에 Qwen raw-read를 비교하면 런타임과 방식 두 변수가 섞여 차이의 원인을 특정할 수 없다. 따라서 같은 Qwen 런타임에서 두 arm을 실행한다.

| Arm | 입력 | 역할 |
| --- | --- | --- |
| A. raw-read | 최소 sanitize된 workspace 경로만 | 가설 검증 대상 |
| B. evidence | `scripts/repository_evidence.py` JSON 출력만 | 같은 런타임 대조군 |

두 arm의 입력은 배타적이다. arm A는 evidence JSON을 받지 않고, arm B는 workspace 경로를 받지 않는다. 입력을 섞으면 대조가 성립하지 않는다.

Codex baseline은 참고치로만 기록하고 결론 근거로 쓰지 않는다.

추가 비용은 Qwen 실행 한 번이다. scanner는 이미 존재하고 `28ms`이므로 arm B의 준비 비용은 없다.

### Workspace 준비

```text
plain_remote_git_clone.py
    --url https://github.com/spring-projects/spring-petclinic
    --destination <scratch>/clone
    --revision f182358d02e4a68e52bdbabf55ca7800288511e7
  -> 최소 sanitize copy -> <scratch>/workspace + manifest.json
```

- revision은 baseline과 동일한 커밋으로 고정한다.
- clone은 기존 `scripts/plain_remote_git_clone.py`를 그대로 사용한다.
- 최소 sanitize는 `.git`, `node_modules`, build output, binary 제외까지만 한다. `scripts/repository_evidence.py`의 `EXCLUDED_PATH_PARTS`, `is_generated_path`, `is_binary_file`을 import해서 쓴다. 부수 효과로 이 함수들의 재사용 가능성이 검증되며, 이후 공용 정책 모듈 결정의 입력이 된다.
- 값 mask는 하지 않는다. 대상이 public repository이므로 이번 결론에 영향을 주지 않는다.

### 실행과 측정

두 arm 모두 동일 프롬프트를 쓰고, 분석 목적은 baseline과 같은 `전체 상세 보고서`(`full_repository_assessment` / `output_mode: detailed`)로 고정한다.

| 측정 항목 | 방법 | 미측정 시 처리 |
| --- | --- | --- |
| wall time | `date +%s%3N` marker. baseline과 동일 방식 | 해당 없음 |
| token usage | Qwen CLI가 노출하는 값 | `미측정`으로 표기 |
| 계약 통과 여부 | `python3 scripts/validate_report.py <report>` | 해당 없음. 핵심 지표 |
| 읽은 파일 목록과 개수 | Qwen session log 파싱. 실패 시 workspace atime fallback | 둘 다 실패하면 `미측정`으로 표기 |

### 결정 규칙

판정은 arm A와 arm B의 비교로 한다.

| 결과 | 결정 |
| --- | --- |
| A가 계약 통과 실패 | raw-read 방향 폐기. Decision Input 강화로 회귀 |
| A 통과하지만 B보다 token·시간 나쁨 | 가설 기각. hybrid(evidence 기본 + 선택적 read)로 전환 |
| A 통과 + B보다 뚜렷이 개선 | 본 설계 진행. sanitizer를 정식 구현 |
| 둘 다 계약 통과 실패 | 문제는 방식이 아니라 저사양 모델의 detailed 계약 수행 능력. 계약 단순화가 다음 과제 |

`뚜렷이 개선`의 자동 임계값은 의도적으로 정하지 않는다. 표본이 repository 하나이므로 임계값을 지금 정하면 근거 없는 숫자가 된다. 판정은 측정 보고서를 보고 사람이 내리고, 그 판단 근거를 보고서에 남긴다.

마지막 행이 실제로 발생할 가능성이 있다. 그 경우에도 spike는 목적을 달성한다. 잘못된 지점을 최적화하는 것을 막기 때문이다.

## 미확인 항목

구현 첫 단계에서 확인한다. 확인에 실패하면 그 사실 자체를 측정 보고서에 결과로 기록하고 진행한다.

- Qwen Code의 비대화형 실행 플래그
- Qwen이 token usage를 노출하는지
- Qwen session log에서 읽은 파일 목록을 추출할 수 있는지

## 범위 밖

이 spike는 다음을 다루지 않는다.

- 타입별 sanitizer의 정식 구현
- `scripts/source_policy.py` 같은 공용 정책 모듈 추출
- gate run record의 정식 스키마
- Codex, Claude, OpenShell 등 다른 런타임 확장

위 항목들은 모두 spike 결과에 의존하므로, 결과가 나온 뒤 별도 슬라이스로 다룬다.
