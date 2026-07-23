# Repository Analysis Workflow

## 1. Resolve Target

Apply the Target Resolution Gate before any repository discovery tool call. Confirm the Repository URL or Local path, access method, revision, and analyzed subdirectory.

## 2. Select Output Mode

Use summary mode by default. Use detailed mode only when explicitly requested.

## 3. Inventory High-Signal Files

Inspect directory structure, package manifests, lockfiles, build files, runtime entrypoints, Compose files, CI workflows, deployment docs, environment examples, migrations, and tests. Exclude generated output, dependency caches, vendored code, and binary assets unless directly relevant.

## 4. Identify Components

Separate independently executable applications, APIs, static frontends, workers, scheduled jobs, one-time jobs, and non-deployable libraries.

## 5. Determine Build and Runtime

For every deployable component, identify build command, production startup command, runtime and version, port or no listener, health endpoint, writable paths, and containerization status. A missing Dockerfile is a finding, not an analysis failure.

## 6. Analyze Configuration and Dependencies

모든 주요 설정을 적용 시점으로 분류한다. 방향성 있는 의존성 표와 의존성 흐름을 만들고, 중요한 관계마다 실행 위치를 기록한다.

## 7. Resolve Evidence

발견 사항을 확인됨, 추정됨, 미확인, 상충됨으로 분류한다. 상충 사항을 보존하고 모든 중요한 발견 사항에 `path/to/file:line` 또는 `path/to/file:start-end` 형식의 저장소 상대 파일·라인 근거를 인용한다. 미확인에는 답을 주지 못한 확인 파일을, 상충됨에는 양쪽 근거를 인용한다.

## 8. Build Component Briefings

각 배포 가능 구성 요소를 하나의 브리핑 카드로 작성한다. 역할, 런타임, 빌드, 기동, 포트, 상태 확인, 설정과 상태를 범주화하고, 각 속성을 `키: 값 — 상태 / 근거` 형식으로 기록한다.

Kubernetes 최소 초안에는 저장소로 확인한 `workload.kind`, 이름, 이미지, 기동 명령, 포트, Service, Ingress 값만 넣는다. 필요한 값이 확인되지 않으면 `최소 입력 누락`에 이유와 근거를 기록한다. 자원·보안·확장 정책 같은 일반 운영값을 임의로 추가하지 않는다.

## 9. Finish Through Completion Gate

모든 배포 가능 구성 요소가 브리핑되고, 관계와 최소 입력 누락이 명시되며, 보고서가 준비됨·추가 정보 필요·진행 불가 중 하나로 끝날 때까지 완료하지 않는다.
