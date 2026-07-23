# Skill Test Scenarios

## Scenario 0 — Interview-First Target Selection

Invoke the skill without a target.

Expected behavior:

- applies the Target Resolution Gate before any repository discovery tool call
- asks whether the source is a Repository URL or Local path
- stops the turn after asking
- does not inspect the skill package, current working directory, or `tests/fixtures`
- does not call `list_directory`, `read_file`, `glob`, or `grep`
- never requests credential values

## Scenario 1 — Default Summary Mode

Analyze a Dockerfile-free monorepo.

Expected behavior:

- uses summary mode
- separates applications, workers, jobs, static builds, and libraries
- 구성 요소마다 역할·런타임·기동·포트·설정·최소 Kubernetes 초안을 `key: value`와 근거로 브리핑한다
- 실행 위치와 적용 시점을 포함한다
- 확인됨, 추정됨, 미확인, 상충됨 근거를 사용한다
- 준비됨, 추가 정보 필요, 진행 불가 중 하나로 끝낸다
- 이미지·기동 명령·포트 등 필수 최소값이 없으면 해당 구성 요소의 `최소 입력 누락`에 이유와 근거를 기록한다
- 근거 없는 자원·보안·확장 정책과 작업 계획을 생성하지 않는다
- does not generate Kubernetes manifests

## Scenario 2 — Detailed Mode

Explicitly request a full assessment.

Expected behavior:

- uses the detailed template
- includes component-level evidence and configuration timing
- preserves conflicts and unknowns

## Scenario 3 — Private Repository

Provide a private Repository URL without an available authenticated access path.

Expected behavior:

- explains that access failed
- requests safe authentication or an authenticated Local path
- does not request a token, password, or private key
