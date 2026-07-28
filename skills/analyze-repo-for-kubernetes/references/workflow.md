# Repository Analysis Workflow

## 1. 분석 요청 확정과 정규화

Repository discovery 전에 Target Resolution Gate를 적용한다. 원격 Git URL, local checkout 또는 source archive, read-only 접근 방식, revision, 분석 subdirectory를 확정한다. Remote Git authentication 또는 source archive에는 [remote-git-access.md](remote-git-access.md)를 적용한다. Target이 실행 가능한 상태가 된 뒤에만 사용자 목적을 해석하고 `intent`, `scope`, `focus`, `output_mode`, `provider`, `phase`를 가진 `ResolvedAnalysisRequest`를 만든다.

Target이 없으면 source method를 먼저 묻고, 다음 turn에서 그 method에 맞는 target value만 묻는다. 목적이 모호하면 target이 확정된 뒤 context question을 한 번만 묻는다. source-method, target-value and purpose questions never occur in the same turn. Never ask the user to select `summary`, `detailed`, `provider` or `phase`.

## 2. 분석 준비 상태 확인

`ResolvedAnalysisRequest.phase`가 `analysis_ready`일 때만 repository discovery를 시작한다. 기본 출력은 summary이며, 사용자의 목적이 `전체 상세 보고서`로 정규화된 경우에만 detailed를 사용한다.

## 3. Evidence Collection 시작

분석 흐름은 `Universal Scanner -> Evidence Pattern Packs -> LLM Triage/Reasoning -> Deterministic Verifier -> Report`이다.

Universal Scanner의 1차 inventory는 manifest/lockfile, 배포 매니페스트, container 정의, 환경 설정, runtime entrypoint, DB 또는 broker configuration으로 제한한다. CI workflow, log configuration, README, deployment document, migration, test는 1차 finding을 보완할 때만 2차로 읽는다.

generated output, dependency cache, vendored code, binary asset는 직접 관련이 없으면 제외한다. analysis root 밖 symlink를 따르지 않는다.

## 4. Evidence Pattern Packs 적용

Evidence Pattern Packs는 Docker, Compose, Kubernetes, Helm, Kustomize, GitHub Actions, language/framework, platform hint에서 line-addressable typed evidence를 수집한다.

deterministic collection은 evidence만 만들고 component decision은 만들지 않는다. package manifest, dependency, script, Docker/Compose, CI job은 candidate evidence일 뿐이며, deployable ownership, production readiness, default deployment path, requiredness로 직접 변환하지 않는다.

각 pattern은 존재하는 fact를 `path/to/file:line` 또는 `path/to/file:start-end`로 남기고, 확인한 부재를 `검색(scope=..., pattern=..., result=없음)`으로 남긴다. Secret 값은 기록하지 않는다.

## 5. LLM triage와 분석 결과 분리

LLM triage는 수집된 evidence를 인용해 semantic interpretation을 수행한다. 판단이 확정되지 않으면 `추정됨`, `미확인`, `상충됨`을 보존한다.

발견 항목은 네 결과 중 하나로 분리한다.

- `배포 대상 후보`
- `저장소에 정의된 런타임 의존성`
- `외부 런타임 의존성`
- `배포 대상 후보에서 제외한 항목`

migration은 one-time job 후보로 먼저 평가한다. library, generated client, build-only package, development utility는 제외 이유와 근거를 기록한다. package manifest만으로 배포 대상 후보를 만들지 않는다.

## 6. 저장소 기동 정의 확인

Compose, script, entrypoint, Procfile, platform command처럼 저장소에서 확인한 기동 정의를 기록한다. 이 근거는 executable behavior를 보여줄 수 있지만 운영 환경 배포 기준 구성은 아니다.

local Compose나 runtime source만으로 운영 환경의 기준 구성을 단정하지 않는다. Compose service가 DB, cache, broker를 띄우더라도 Kubernetes에 직접 배포해야 한다는 뜻이 아니다.

## 7. 운영 환경 배포 근거 확인

Helm, Kustomize, plain manifest, GitOps configuration, release CI처럼 operating-environment deployment declaration을 저장소 기동 정의와 분리해 기록한다.

운영 환경 배포 근거가 없으면 `미확인`과 absence search를 기록한다. 운영 환경 배포 기준 구성은 이 근거가 있을 때만 후보로 다룬다. README 예시, development Compose, framework default를 운영 baseline으로 승격하지 않는다.

## 8. Build와 runtime 분석

각 배포 대상 후보마다 build command, production startup command, runtime/version, port 또는 non-listener, health behavior, configuration 적용 시점, writable state, containerization status를 분석한다.

Dockerfile 누락은 분석 실패가 아니라 finding이다. language-specific dependency declaration은 runtime use를 확인하지 않는다. development command와 production startup command를 분리한다.

## 9. Configuration과 dependency 분석

주요 configuration을 `빌드 시점`, `배포 시점`, `프로세스 시작 시점`, `실행 중`, `관리 시점`, `미확인` 중 하나로 분류한다.

모든 dependency를 logical source workload에서 target 방향으로 기록한다. dependency type, protocol 또는 mechanism, endpoint 또는 configuration name, 시점, 실행 위치, 기능 실행에 필요 여부, 확인된 실행 정의에서 사용 여부, 공급 또는 관리 경계, 상태와 근거를 포함한다.

logical source와 실제 network caller를 구분한다. package declaration만으로 runtime communication을 `확인됨`으로 판단하지 않는다.

## 10. Evidence 상태 확정

finding은 `확인됨`, `추정됨`, `미확인`, `상충됨` 중 하나로 분류한다. conflict와 unknown은 Kubernetes 설계에 편한 값으로 임의 해결하지 않는다.

`추정됨`에는 판단 이유를 쓰고, `미확인`에는 확인한 파일 또는 검색 범위와 부족한 정보를 쓴다. `상충됨`에는 양쪽 근거를 모두 기록한다.

## 11. 배포 대상 후보 briefing 작성

배포 대상 후보마다 하나의 briefing card를 만든다. source-backed 값과 inferred Kubernetes candidate를 분리한다.

각 component에 `workload.kind`, `metadata.name`, `image`, `command`, `args`, `containerPort`, `Service`, `Ingress`의 후보값 또는 최소 입력 누락을 기록한다. unresolved required value는 `최소 입력 누락`에 key, 이유, 근거 또는 검색 범위, 후속 설계 차단 여부와 함께 둔다.

termination/recovery, observable signal, state/persistence는 repository evidence가 있을 때만 확인됨으로 기록한다.

## 12. Deterministic Verifier와 Completion Gate

Deterministic Verifier는 schema, citation validity, unsupported claim, secret leakage의 최종 방어선이다. verifier가 invalid citation, schema drift, unsupported deployable/readiness conclusion, Secret 값 노출을 발견하면 보고서를 완료하지 않는다.

Completion Gate에서 다음을 확인한다.

- target과 revision이 명시되어 있다.
- 모든 독립 실행 component가 포함되어 있다.
- 배포 대상 후보, 런타임 의존성, 외부 의존성과 제외 항목의 경계가 근거와 함께 기록되어 있다.
- 저장소에서 확인한 기동 정의와 운영 환경 배포 근거를 혼동하지 않았다.
- 운영 환경 배포 기준 구성을 근거 없이 만들지 않았다.
- 각 배포 대상 후보에 build, runtime, containerization, network, configuration, state 분석이 있다.
- 중요한 dependency에 방향, 시점, 실행 위치, 기능 실행에 필요 여부, 공급 또는 관리 경계가 있다.
- 중요한 repository fact에 evidence status와 유효한 근거가 있다.
- conflict와 unknown을 임의로 해소하지 않았다.
- 각 component에 Kubernetes 최소 설계 입력 또는 최소 입력 누락이 있다.
- Secret 값이 노출되지 않았다.
- Kubernetes manifest, Dockerfile, Helm chart 또는 application code를 생성하지 않았다.
- 보고서가 `설계 입력 충분`, `추가 정보 필요`, `분석 불가` 중 하나의 Kubernetes 설계 입력 상태로 끝난다.

`추가 정보 필요` 판정은 검증된 설계 차단 항목의 범주와 영향 범위를 포함해야 한다.

## 13. Structured report mode routing

Structured report mode는 evidence triage가 완료되고 immutable analysis snapshot이 생성된 뒤에만 시작한다. analysis completion handoff에는 `target_ref`, `target_sha256`, `analysis_snapshot_id`, `idempotency_key`가 반드시 포함되어야 한다.

Analysis mode에서 deployable subject ID와 relationship edge ID를 확정한 뒤 다음 helper를 한 번 실행한다. 이 helper는 `target.json`의 mode를 사용해 bounded snapshot을 `.report-session/snapshots/<analysis_snapshot_id>.json`에 content-addressed bytes로 생성하고 stdout에는 네 handoff field만 반환한다.

```text
python3 <plugin-root>/scripts/report_start_handoff.py --target-ref <workspace>/target.json --deployable-subject-id <subject-id> --relationship-edge-id <edge-id>
```

필요한 각 subject와 edge에 해당 option을 반복한다. 동일 target과 ID 집합의 재실행은 동일 snapshot과 `idempotency_key`를 반환한다. `target_sha256`은 target bytes에, `analysis_snapshot_id`는 snapshot bytes에 결합되므로 handoff가 생성된 뒤 두 파일을 수정하지 않는다. 네 값을 수정하거나 path를 해석하지 말고 그대로 `report_session_start`에 전달한다.

보고서 단계는 분석 대화와 분리된 compact report sub-session으로 실행한다. 이 모드에서는 [qwen-structured-report-mode.md](qwen-structured-report-mode.md)를 최상위 지시문으로 적용하고, report lifecycle server가 제공하는 only four lifecycle tools만 사용한다: `report_session_start`, `report_chunk_submit`, `report_session_sync`, `report_session_finalize`.

모델은 backend가 제공한 `next_action`에 대응하는 도구 하나만 호출한다. lease, state version, required field, continuation, retry와 repair는 해당 지시문에 따른다. 모델은 report 파일, template 또는 Markdown 본문을 직접 읽거나 수정하거나 생성하지 않으며, lifecycle backend가 canonical artifact 생성과 validation을 소유한다.

`<thought>` stop sequence는 사용하지 않는다. stream 종료와 단일 lifecycle Tool Call의 완전성을 확인한 뒤에만 backend로 전달한다.

backend가 `COMPLETE`를 반환하면 최종 응답은 artifact path, SHA-256, byte size, validation status만 포함한다. Markdown 보고서 본문은 모델 응답으로 반환하지 않는다.

Outside structured report mode, 기존 template 선택, staged `report.md` 검증, 전체 보고서 반환 규칙을 유지한다.
