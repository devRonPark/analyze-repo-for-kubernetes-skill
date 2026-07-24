# Skill 커버리지 검증 및 개선 계획

검증일: 2026-07-23  
대상 Skill: `analyze-repo-for-kubernetes`  
검증 방식: 공개 레포지토리의 특정 commit을 local checkout으로 고정한 뒤, 동일 모델·동일 prompt·동일 read-only 조건에서 각 레포지토리를 2회씩 독립 분석

## 검증 조건

- 실행 모델: `gpt-5.6-terra`
- 출력 모드: `summary`
- 분석 방식: 정적 분석만 허용
- 금지 사항: build, test, server, container, repository script 실행 및 대상 레포지토리 파일 변경
- 반복 횟수: 레포지토리당 2회, 총 16회
- 기준 prompt:

```text
Use the analyze-repo-for-kubernetes skill at <skill-path>/SKILL.md.
현재 저장소를 Kubernetes 이관 관점에서 summary 모드로 분석해.
저장소는 읽기 전용으로 정적 분석하고, 빌드·테스트·서버·컨테이너·저장소 스크립트를 실행하지 마.
분석 결과는 응답에만 작성하고 파일을 수정하거나 생성하지 마.
확인할 수 없는 내용은 미확인으로 분리하고 모든 주요 판단에 repository-relative file:line 근거를 제시해.
```

- ground truth 작성 방식: manifest, lockfile, build file, production deployment file, runtime entrypoint를 수동 교차 확인
- 출력 계약 검사: 각 결과를 `python3 scripts/validate_report.py <report> --mode summary`로 검사
- 패키지 기준선: `scripts/validate_skill.py` 통과, unit test 17개 통과
- 실제 생성 보고서 검사 결과: 16개 중 0개 통과

# 1. 검증 대상

| Repository / commit | Programming Language | Build / dependency tool | Repository Structure | 선정 이유 |
|---|---|---|---|---|
| [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic) `f182358d` | Java 17, Spring Boot | Maven + Gradle | Single Repository / Backend | 동일 애플리케이션에 두 Java build 경로가 공존하고 DB profile 및 Kubernetes 예제가 있음 |
| [astral-sh/uv-fastapi-example](https://github.com/astral-sh/uv-fastapi-example) `a1e31314` | Python 3.12+, FastAPI | uv | Single Repository / Backend | 작은 uv 기반 애플리케이션으로 manifest 우선 탐색의 기준 사례 |
| [anomaly/lab-python-server](https://github.com/anomaly/lab-python-server) `d08f2cab` | Python 3.10+, FastAPI, TaskIQ | Poetry | Single Repository / Backend, multi-process | 하나의 Python package에서 API와 worker가 분리되고 dev/prod Compose가 다름 |
| [sahat/hackathon-starter](https://github.com/sahat/hackathon-starter) `b1ac2bbd` | Node.js, Express, Pug | npm | Single Repository / Backend/server-rendered web | 단일 Node 프로세스가 다수의 외부 API와 MongoDB를 사용하는 사례 |
| [antfu-collective/vitesse](https://github.com/antfu-collective/vitesse) `8a01bc92` | TypeScript, Vue, Vite SSG | pnpm | Single Repository / Frontend Only | `pnpm-workspace.yaml`은 있지만 `packages: []`인 정적 frontend 사례 |
| [alan2207/bulletproof-react](https://github.com/alan2207/bulletproof-react) `9506629e` | TypeScript, React, Next.js, Vite | yarn | Mono-Repository / 다중 frontend 애플리케이션 | formal workspace 설정 없이 세 개의 독립 앱과 test-only mock server가 공존 |
| [oldboyxx/jira_clone](https://github.com/oldboyxx/jira_clone) `26a9e77b` | TypeScript/Node.js API, React client | npm 중심, client에 yarn lock 공존 | Mono-Repository / Frontend + Backend | root orchestration과 `api`, `client`의 독립 production command 및 PostgreSQL 의존성이 있음 |
| [GoogleCloudPlatform/microservices-demo](https://github.com/GoogleCloudPlatform/microservices-demo) `9a4616e7` | Java, Python, Node.js, Go, C#, C++ | Gradle, pip, npm, Go, .NET, CMake | MSA Repository | 12개 repo-owned service, Redis, optional overlay, Kustomize가 있는 다언어 MSA |

이 매트릭스는 Java, Python, Node.js와 Maven, Gradle, uv, Poetry, pip, npm, yarn, pnpm을 모두 포함한다. 구조 범위는 frontend-only single, backend single, multi-process single, frontend+backend mono-repo, multi-app mono-repo, MSA를 포함한다.

# 2. 레포지토리별 검증 결과

## 2.1 spring-projects/spring-petclinic

### 식별 결과

- Java 17 / Spring Boot 4.1 애플리케이션 1개와 예제 PostgreSQL 배포를 찾았다.
- Maven과 Gradle을 모두 실제 build 경로로 식별했다.
- 두 실행 모두 애플리케이션과 `demo-db`를 배포 구성 요소로 보고했다.
- 두 실행 모두 최종 판정은 `추가 정보 필요`였다.

### 분석에 사용한 핵심 파일

| 파일 | 선택 이유 |
|---|---|
| `pom.xml:5-19` | Spring Boot, Java version, Maven artifact 식별 |
| `build.gradle:1-20` | Gradle plugin과 Java toolchain 식별 |
| `.github/workflows/maven-build.yml:20-29` | 실제 Maven CI command 확인 |
| `.github/workflows/gradle-build.yml:20-31` | 실제 Gradle CI command 확인 |
| `src/main/java/org/springframework/samples/petclinic/PetClinicApplication.java:28-34` | 독립 실행 main class 확인 |
| `src/main/resources/application.properties:1-21` | 기본 H2 profile과 actuator 설정 확인 |
| `src/main/resources/application-postgres.properties:3-5` | 외부 PostgreSQL 설정 확인 |
| `k8s/petclinic.yml:15-64`, `k8s/db.yml:28-73` | 기존 workload, port, image, DB 배포 확인 |

### 정확하게 판단한 항목

- Java/Spring Boot, Java 17, Maven과 Gradle의 동시 지원
- 단일 Spring Boot main application
- H2 기본값과 MySQL/PostgreSQL 선택 profile
- CI에 근거한 `./mvnw -B verify`, `./gradlew build`
- local run command를 production command로 단정하지 않은 불확실성 처리
- Kubernetes manifest의 application image와 DB persistence/Secret 누락

### 누락하거나 잘못 판단한 항목

- `Single Repository / Backend`를 명시적으로 분류하지 않았다.
- `demo-db`를 application component와 같은 수준의 배포 브리핑으로 처리해 repo-owned application과 third-party infrastructure의 경계가 흐려졌다.
- executable JAR가 만들어지는 Spring Boot project임에도 production startup 후보를 `추정됨`으로 제시하지 않고 전부 `미확인`으로 남겼다.
- 두 결과 모두 component key를 합치거나 누락해 report validator를 통과하지 못했다.

### 불필요하게 분석한 파일

- 2차 결과는 `src/test/java/.../PetClinicIntegrationTests.java`를 runtime 제외 근거로 사용했다. `pom.xml`과 `build.gradle`의 test scope만으로 같은 판단이 가능했고 line 없는 파일 경로까지 출력해 validation error를 추가했다.

### 수동 확인이 필요했던 항목

- Maven과 Gradle 중 운영 표준 build 경로
- H2, MySQL, PostgreSQL 중 실제 운영 DB
- `dsyer/petclinic` image와 현재 source revision의 provenance
- Kubernetes 내 DB 운영 여부와 관리형 DB 사용 여부

### 평가

| 평가 항목 | 판정 | 근거 |
|---|---|---|
| 언어 식별 | 통과 | 두 실행 모두 Java 17 / Spring Boot 식별 |
| 빌드 도구 식별 | 통과 | `pom.xml`, `build.gradle`, CI command를 함께 사용 |
| 구조 분류 | 실패 | Single/Mono/MSA 명시 없음 |
| 서비스 탐색 | 부분 통과 | app과 DB를 찾았으나 application과 infrastructure 역할 구분이 불명확 |
| 핵심 파일 선택 | 통과 | build, main, application config, deployment file을 근거로 사용 |
| 명령어 추론 | 부분 통과 | build command는 정확, production startup 후보는 제시하지 않음 |
| 외부 의존성 | 통과 | H2 기본 및 MySQL/PostgreSQL 선택 관계 식별 |
| 불확실성 관리 | 통과 | image provenance, startup, persistence를 미확인으로 보존 |
| 결과 일관성 | 통과 | component, build path, DB, 최종 판정이 두 실행에서 동일 |

최종 판정: **부분 통과**

## 2.2 astral-sh/uv-fastapi-example

### 식별 결과

- Python 3.12+, FastAPI, uv를 정확히 식별했다.
- FastAPI API 1개만 deployable component로 식별했다.
- 두 실행 모두 `uv sync --locked --no-cache`와 `/app/.venv/bin/fastapi run app/main.py --port 80`을 제시했다.
- 두 실행 모두 최종 판정은 `추가 정보 필요`였다.

### 분석에 사용한 핵심 파일

| 파일 | 선택 이유 |
|---|---|
| `pyproject.toml:1-9` | project, Python version, direct dependency 확인 |
| `uv.lock:1-2`, `uv.lock:83-103` | uv lock과 resolved FastAPI version 확인 |
| `Dockerfile:1-14` | dependency install, production startup, port 확인 |
| `app/main.py:7-22` | ASGI application과 route 확인 |
| `app/dependencies.py:6-13` | 전역 인증 dependency와 probe 제약 확인 |

### 정확하게 판단한 항목

- uv 기반 Python application과 FastAPI framework
- router module을 별도 workload로 오인하지 않고 API 1개로 통합
- Docker build와 production startup command
- port 80과 전용 health endpoint 부재
- 외부 DB, cache, broker가 확인되지 않는다는 판단
- hard-coded 인증값을 그대로 노출하지 않고 `[REDACTED]` 처리

### 누락하거나 잘못 판단한 항목

- `Single Repository / Backend`를 명시적으로 분류하지 않았다.
- generic resource/security policy 부재를 모두 설계 차단 입력으로 확장했다.
- 같은 사실을 1차에서는 `언어/프레임워크/런타임`, 2차에서는 `언어·런타임`으로 결합해 exact output key가 흔들렸다.

### 불필요하게 분석한 파일

- 실행 trace에서 generic Python `.gitignore` 전체와 `uv.lock`의 다수 transitive package record를 읽었다. 이 사례의 핵심 결과는 `pyproject.toml`, `Dockerfile`, `app/main.py`, `app/dependencies.py`만으로 결정 가능했다.

### 수동 확인이 필요했던 항목

- 운영 image registry/tag
- 인증 없는 probe endpoint 필요 여부
- 외부 공개 여부

### 평가

| 평가 항목 | 판정 | 근거 |
|---|---|---|
| 언어 식별 | 통과 | Python 3.12+와 FastAPI 정확 |
| 빌드 도구 식별 | 통과 | `pyproject.toml`, `uv.lock`, Dockerfile의 uv command |
| 구조 분류 | 실패 | Single/Mono/MSA 명시 없음 |
| 서비스 탐색 | 통과 | API 1개, router 제외 정확 |
| 핵심 파일 선택 | 통과 | 네 개의 high-signal 파일로 주요 판단 뒷받침 |
| 명령어 추론 | 통과 | build와 production startup 모두 직접 근거 |
| 외부 의존성 | 통과 | runtime outbound dependency 부재를 검색 근거로 분리 |
| 불확실성 관리 | 통과 | probe, image, exposure를 미확인 처리 |
| 결과 일관성 | 통과 | component, command, port, dependency, verdict 동일 |

최종 판정: **부분 통과**

## 2.3 anomaly/lab-python-server

### 식별 결과

- Python/FastAPI API와 TaskIQ worker 두 개의 application process를 식별했다.
- Poetry project와 production Docker/Compose/Helm 구성을 찾았다.
- 2차 결과는 dev-only `scheduler` 후보와 PostgreSQL, Redis, RabbitMQ, MinIO를 별도 분류했다.
- 두 실행 모두 최종 판정은 `추가 정보 필요`였다.

### 분석에 사용한 핵심 파일

| 파일 | 선택 이유 |
|---|---|
| `src/pyproject.toml:1-60` | Poetry, Python, FastAPI, TaskIQ, external client 식별 |
| `Dockerfile.prod:27-74` | production dependency/image build 단계 확인 |
| `docker-compose.prod.yml:101-150` | API/worker production command와 상충하는 worker build 설정 확인 |
| `docker-compose.yml:72-179` | dev-only API, worker, scheduler, MinIO job 구분 |
| `src/labs/api.py:57-95` | FastAPI application과 health route 확인 |
| `src/labs/broker.py:29-59` | TaskIQ broker/result backend/scheduler object 확인 |
| `src/labs/settings/*.py` | DB, Redis, AMQP, S3, SMTP, SMS, JWT 설정과 Secret 분류 |

### 정확하게 판단한 항목

- API와 worker를 독립 runtime으로 식별
- Poetry/FastAPI/TaskIQ와 Python version
- API production command와 worker command
- PostgreSQL, Redis, RabbitMQ, S3/MinIO, SMTP/SMS external dependency
- dev Compose와 production Compose의 차이
- `scheduler`가 dev Compose에는 있지만 production definition이 없다는 점을 2차 실행에서 보존

### 누락하거나 잘못 판단한 항목

- `Single Repository / Backend multi-process`를 명시적으로 분류하지 않았다.
- 1차 결과는 Dockerfile 내부 단계를 “build command 확인됨”으로 보았고, 2차 결과는 공식 build command를 `미확인`으로 보았다.
- worker는 production Compose 안에서 `Dockerfile`과 `.env.development`를 참조한다. 이 conflict를 2차만 `상충됨`으로 기록했다.
- 1차 결과는 dev-only scheduler 후보를 별도로 설명하지 않았다.
- 1차 결과에는 실제 파일 길이를 넘는 line citation이 최소 9개 있었다. 예를 들어 70줄인 `src/labs/db.py`를 `src/labs/db.py:922-939`로, 48줄인 `src/labs/routers/ext/__init__.py`를 `:155-163`으로 인용했다.

### 불필요하게 분석한 파일

- 외부 의존성이 다수라 settings 파일 탐색은 필요했다. 다만 동일 설정을 API와 worker 카드에서 반복 인용해 출력 길이가 늘었고, 공통 설정 표 하나로 충분했다.

### 수동 확인이 필요했던 항목

- worker production image가 `Dockerfile`인지 `Dockerfile.prod`인지
- production worker가 `.env.development`를 참조하는 것이 의도인지
- scheduler의 실제 production 운영 필요 여부
- Redis와 RabbitMQ 중 TaskIQ broker/result backend의 운영 조합

### 평가

| 평가 항목 | 판정 | 근거 |
|---|---|---|
| 언어 식별 | 통과 | Python/FastAPI/TaskIQ 정확 |
| 빌드 도구 식별 | 통과 | Poetry와 production image build file 확인 |
| 구조 분류 | 실패 | Single/Mono/MSA 명시 없음 |
| 서비스 탐색 | 통과 | API/worker 식별, scheduler는 production 근거 부족으로 분리 |
| 핵심 파일 선택 | 부분 통과 | 파일 종류는 적절했지만 1차 결과의 line citation 다수가 실제 범위를 벗어남 |
| 명령어 추론 | 부분 통과 | startup은 정확, build status와 worker image 판단이 반복 실행에서 다름 |
| 외부 의존성 | 통과 | DB, cache, broker, object storage, comms 모두 식별 |
| 불확실성 관리 | 통과 | prod/dev conflict와 scheduler를 상충/미확인으로 보존 |
| 결과 일관성 | 부분 통과 | component identity는 같지만 build command status와 conflict 탐지가 다름 |

최종 판정: **부분 통과**

## 2.4 sahat/hackathon-starter

### 식별 결과

- Node.js/Express/Pug 단일 web application을 식별했다.
- `npm run scss`와 `npm start`를 정확히 제시했다.
- MongoDB를 필수 DB 및 session store로 찾고 다수의 선택 외부 API를 분리했다.
- 두 실행 모두 최종 판정은 `추가 정보 필요`였다.

### 분석에 사용한 핵심 파일

| 파일 | 선택 이유 |
|---|---|
| `package.json:14-29`, `package.json:122-124` | npm scripts와 Node version 확인 |
| `package-lock.json` | npm dependency resolution 근거 |
| `app.js:110-151`, `app.js:443-463` | Express, MongoDB, session, port, listener 확인 |
| `.env.example:9-102` | DB, Secret, provider 환경변수 목록 확인 |
| `models/User.js:5-78` | MongoDB persistent state 확인 |
| `controllers/ai.js`, `controllers/ai-agent.js` | AI provider 및 Mongo-backed checkpoint/cache 확인 |

### 정확하게 판단한 항목

- 단일 Node/Express web runtime
- SCSS build와 `node app.js` production startup
- MongoDB required dependency와 Mongo session store
- `PORT`/host, file write 후보, health endpoint 부재
- OAuth, SMTP, AI, payment 등 기능별 선택 dependency
- devDependency와 별도 worker가 아닌 startup cleanup function을 workload에서 제외

### 누락하거나 잘못 판단한 항목

- `Single Repository / Backend`를 명시적으로 분류하지 않았다.
- npm command는 정확했지만 “package manager: npm”을 `package-lock.json` 근거와 함께 별도 필드로 출력하지 않았다.
- resource/security policy를 모두 blocker로 나열해 application 분석과 운영 정책의 경계가 흐려졌다.

### 불필요하게 분석한 파일

- provider별 controller 구현을 깊게 열어 다수 API를 개별 관계로 확장했다. workload 및 required dependency 결정에는 `.env.example`, route registration, Mongo/session code가 우선이며 provider별 구현은 선택 기능의 required 여부가 불명확할 때만 추가로 읽으면 충분하다.

### 수동 확인이 필요했던 항목

- 운영에서 활성화할 OAuth/AI/payment provider
- upload/RAG 임시 파일의 보존 정책
- public `BASE_URL`과 TLS 종료 위치

### 평가

| 평가 항목 | 판정 | 근거 |
|---|---|---|
| 언어 식별 | 통과 | Node.js/Express/Pug 정확 |
| 빌드 도구 식별 | 부분 통과 | npm command는 정확하나 lockfile 기반 manager 명시가 없음 |
| 구조 분류 | 실패 | Single/Mono/MSA 명시 없음 |
| 서비스 탐색 | 통과 | 단일 app, worker/job 부재 정확 |
| 핵심 파일 선택 | 통과 | package, entrypoint, env, state model 사용 |
| 명령어 추론 | 통과 | SCSS build와 production start 직접 근거 |
| 외부 의존성 | 통과 | MongoDB 필수, provider별 선택 dependency 구분 |
| 불확실성 관리 | 통과 | provider 활성화와 file persistence를 미확인 처리 |
| 결과 일관성 | 통과 | component, commands, MongoDB, port, verdict 동일 |

최종 판정: **부분 통과**

## 2.5 antfu-collective/vitesse

### 식별 결과

- TypeScript/Vue/Vite SSG 정적 frontend 1개를 식별했다.
- pnpm 10.30.2, `pnpm build`, Nginx production startup을 정확히 식별했다.
- 두 실행 모두 runtime application server와 external DB/broker가 없다고 판단했다.
- component 이름만 `vitesse`와 `vitesse-web`로 달랐고 핵심 결과는 같았다.

### 분석에 사용한 핵심 파일

| 파일 | 선택 이유 |
|---|---|
| `package.json:1-17` | package manager, Vite SSG build, dev/preview 구분 |
| `pnpm-lock.yaml:1-8` | pnpm lock format 확인 |
| `pnpm-workspace.yaml:1-7` | `packages: []` 확인, workspace file만으로 mono-repo 판단 방지 |
| `Dockerfile:1-18` | Node build stage와 Nginx production stage 확인 |
| `src/main.ts:13-24` | frontend entrypoint와 build-time `BASE_URL` 확인 |
| `netlify.toml:1-17` | static hosting 후보 확인 |

### 정확하게 판단한 항목

- pnpm, TypeScript, Vue, Vite SSG
- 정적 frontend 한 개와 Nginx production runtime
- `vite preview`를 production command로 사용하지 않음
- server-side persistence와 application outbound dependency 부재
- `BASE_URL`을 build-time 설정으로 추정

### 누락하거나 잘못 판단한 항목

- `Single Repository / Frontend Only`를 명시적으로 분류하지 않았다.
- `pnpm-workspace.yaml`이 존재하지만 `packages: []`라는 구조 근거를 분류 결과에 사용하지 않았다.
- 2차 결과는 `pnpm-workspace.yaml`의 dependency catalog line을 framework 근거로 사용했지만 `package.json`만으로 충분했다.

### 불필요하게 분석한 파일

- 2차 결과의 `pnpm-workspace.yaml:24,47,57` framework 인용은 `package.json` dependency와 중복됐다. 이 파일에서는 `packages: []`만 구조 판별에 필요했다.

### 수동 확인이 필요했던 항목

- Kubernetes에서 사용할 static image registry/tag
- Netlify 대신 Kubernetes/Nginx 배포가 실제 목표인지
- hostname/TLS/Ingress 정책

### 평가

| 평가 항목 | 판정 | 근거 |
|---|---|---|
| 언어 식별 | 통과 | TypeScript/Vue/Vite 정확 |
| 빌드 도구 식별 | 통과 | `packageManager`, pnpm lock, Docker build command |
| 구조 분류 | 실패 | Single/Mono/MSA 명시 없음 |
| 서비스 탐색 | 통과 | static frontend 1개 정확 |
| 핵심 파일 선택 | 통과 | package, workspace metadata, Dockerfile, entrypoint 사용 |
| 명령어 추론 | 통과 | build와 Nginx startup 정확 |
| 외부 의존성 | 통과 | runtime DB/broker/outbound 부재를 검색 근거로 처리 |
| 불확실성 관리 | 통과 | image/exposure/probe를 미확인 처리 |
| 결과 일관성 | 통과 | component 이름만 달랐고 주요 판단 동일 |

최종 판정: **부분 통과**

## 2.6 alan2207/bulletproof-react

### 식별 결과

- `react-vite`, `nextjs-app`, `nextjs-pages` 세 개의 독립 frontend 구현을 두 실행 모두 식별했다.
- 각 앱의 yarn build command를 찾고 Next.js의 `yarn start`를 production startup으로 제시했다.
- Vite의 `vite preview`는 production server로 확정하지 않았다.
- test-only mock server 3개를 별도 workload에서 제외했다.

### 분석에 사용한 핵심 파일

| 파일 | 선택 이유 |
|---|---|
| `package.json:1-8` | 세 앱의 yarn install orchestration 확인 |
| `apps/*/package.json:6-18` | component별 build/start와 mock command 확인 |
| `apps/*/yarn.lock` | component별 yarn dependency management 확인 |
| `docs/application-overview.md:30-36` | 세 구현의 선택 관계 확인 |
| `apps/*/src/config/env.ts` | `VITE_APP_*`, `NEXT_PUBLIC_*` 설정 확인 |
| `apps/*/src/lib/api-client.ts` | browser/server의 external API 호출 확인 |
| `apps/*/mock-server.ts` 및 README | mock server가 E2E/development 용도인지 확인 |

### 정확하게 판단한 항목

- formal workspace 설정이 없어도 세 개의 독립 app root 식별
- Vite static build와 두 Next.js server runtime 구분
- mock server를 deployable production component로 오인하지 않음
- 세 frontend 모두 external API URL에 의존함을 식별
- Vite browser caller와 Next.js browser/server caller 차이 식별
- mock `/healthcheck`를 application health endpoint로 오인하지 않음

### 누락하거나 잘못 판단한 항목

- `Mono-Repository / 다중 frontend 애플리케이션`을 명시적으로 분류하지 않았다.
- Next.js `NEXT_PUBLIC_*` 설정의 적용 시점은 실행마다 표현이 달랐다. 한 번은 완전 `미확인`, 한 번은 rebuild 필요 여부를 `추정됨`으로 남겼다.
- 세 app card에서 exact required key를 합쳐 report validator error가 다수 발생했다.

### 불필요하게 분석한 파일

- mock server가 test-only임을 `package.json`과 README로 확정한 뒤에도 개별 MSW handler와 mock DB를 반복 인용했다. health endpoint 오인 방지를 위한 대표 handler 하나 외의 상세 handler 탐색은 workload 판정에 필요하지 않았다.

### 수동 확인이 필요했던 항목

- 세 구현 중 실제 이관 대상
- Vite static hosting 방식
- Next.js production port와 image
- external API의 실제 위치, 인증, CORS

### 평가

| 평가 항목 | 판정 | 근거 |
|---|---|---|
| 언어 식별 | 통과 | TypeScript/React/Vite/Next.js 정확 |
| 빌드 도구 식별 | 통과 | root install script와 app별 yarn lock/build command |
| 구조 분류 | 실패 | Mono-Repo 명시 없음 |
| 서비스 탐색 | 통과 | 세 app 모두 식별, mock server 제외 |
| 핵심 파일 선택 | 통과 | app manifest, env loader, API client, docs 사용 |
| 명령어 추론 | 부분 통과 | Next.js는 정확, Vite production serving은 안전하게 미확인 |
| 외부 의존성 | 통과 | 세 app의 API URL과 실제 caller 위치 식별 |
| 불확실성 관리 | 통과 | target app 선택, static hosting, port를 미확인 처리 |
| 결과 일관성 | 통과 | component와 주요 command/dependency가 동일 |

최종 판정: **부분 통과**

## 2.7 oldboyxx/jira_clone

### 식별 결과

- `api` Express/TypeORM application과 `client` React/Webpack + Express static server 두 개를 식별했다.
- root, API, client production build/start command를 정확히 찾았다.
- API의 PostgreSQL dependency와 client의 build-time `API_URL`을 식별했다.
- 두 실행의 component 이름만 `jira-api`/`api`, `jira-client`/`client`로 달랐다.

### 분석에 사용한 핵심 파일

| 파일 | 선택 이유 |
|---|---|
| `package.json:6-10` | root multi-app orchestration 확인 |
| `api/package.json:6-11` | API build/start 확인 |
| `client/package.json:6-12` | client build/start 확인 |
| `api/src/index.ts:15-46` | DB initialization, Express listener, port 확인 |
| `api/src/database/createConnection.ts:7-15` | PostgreSQL configuration 확인 |
| `api/.env.example:2-7` | DB 및 JWT Secret 이름 확인 |
| `client/server.js:5-13` | static server runtime과 port 확인 |
| `client/webpack.config.production.js:61-66` | `API_URL` build-time injection 확인 |
| `client/src/shared/utils/api.js:8-30` | browser runtime API 호출 확인 |

### 정확하게 판단한 항목

- API/client 두 deployable component
- TypeScript compilation, Webpack build, PM2 production command
- API port 3000, client port 8081
- PostgreSQL required dependency와 JWT Secret
- client `API_URL`이 production bundle에 고정되는 build-time 설정
- browser에서 API로 향하는 방향성 있는 dependency

### 누락하거나 잘못 판단한 항목

- `Mono-Repository / Frontend + Backend`를 명시적으로 분류하지 않았다.
- root와 API는 npm lock을 사용하고 client에는 npm lock과 yarn lock이 공존하지만, manager conflict를 보고하지 않았다.
- 실제 Node version과 PM2 포함 방식은 올바르게 미확인 처리했지만 package manager별 install command 선택도 함께 미확인으로 분리했어야 한다.

### 불필요하게 분석한 파일

- 최종 결과에서 명백히 불필요한 source file은 확인되지 않았다. 문제는 과다 탐색보다 lockfile conflict를 활용하지 않은 데 있었다.

### 수동 확인이 필요했던 항목

- npm과 yarn 중 client의 authoritative manager
- Node version과 PM2 packaging
- PostgreSQL 제공 방식과 credential 공급원
- build-time API URL을 환경별로 생성하는 방식

### 평가

| 평가 항목 | 판정 | 근거 |
|---|---|---|
| 언어 식별 | 통과 | TypeScript/Node/Express와 React/Webpack 정확 |
| 빌드 도구 식별 | 부분 통과 | npm command는 정확, npm/yarn lock conflict 미보고 |
| 구조 분류 | 실패 | Mono-Repo 명시 없음 |
| 서비스 탐색 | 통과 | API/client 모두 식별 |
| 핵심 파일 선택 | 통과 | root/component manifest, entrypoint, build config 사용 |
| 명령어 추론 | 통과 | component별 build/start 직접 근거 |
| 외부 의존성 | 통과 | PostgreSQL과 browser→API 관계 정확 |
| 불확실성 관리 | 통과 | Node version, image, DB 공급 방식을 미확인 처리 |
| 결과 일관성 | 통과 | component 이름 차이 외 핵심 결과 동일 |

최종 판정: **부분 통과**

## 2.8 GoogleCloudPlatform/microservices-demo

### 식별 결과

- 두 실행 모두 12개 repo-owned service identity를 모두 찾았다.
- Java/Gradle `adservice`, Python/pip 서비스, Node/npm 서비스와 그 외 Go/.NET/C++ 서비스를 식별했다.
- Dockerfile과 Kubernetes manifest에서 component별 build/start/port/probe를 추출했다.
- `shoppingassistantservice`를 optional component로 찾고 `redis-cart`를 상태 저장 infrastructure로 찾았다.

### 분석에 사용한 핵심 파일

| 파일 | 선택 이유 |
|---|---|
| `README.md:25-37` | 서비스 목록과 언어의 초기 inventory |
| `kubernetes-manifests/kustomization.yaml:17-35` | default resource와 주석 처리된 optional resource 구분 |
| `src/*/Dockerfile` | 서비스별 build/start/port 확인 |
| `src/adservice/build.gradle` | Java/Gradle dependency와 build 확인 |
| `src/*/requirements.txt` | Python/pip dependency 확인 |
| `src/currencyservice/package.json`, `src/paymentservice/package.json` | Node/npm dependency 확인 |
| `kubernetes-manifests/*.yaml` | Service, Deployment, env, probe, dependency address 확인 |
| `kustomize/components/shopping-assistant/*` | optional service 및 Google Cloud dependency 확인 |
| 주요 service entrypoint | manifest의 address와 required/fallback 동작 교차 확인 |

### 정확하게 판단한 항목

- 모든 repo-owned service identity
- 다언어와 Gradle/pip/npm build 방식
- 서비스별 Docker build/start/port
- HTTP, gRPC, Redis 방향성 관계
- `loadgenerator`가 non-listener process라는 점
- `shoppingassistantservice`의 optional overlay와 Google API/AlloyDB/Secret Manager dependency
- Redis `emptyDir`의 비영속성

### 누락하거나 잘못 판단한 항목

- `MSA Repository`를 명시적으로 분류하지 않았다.
- 1차는 `loadgenerator`를 default Kustomization에서 제외됐다고 정확히 기록했으나, 2차는 default component에 포함했다. 실제 `kubernetes-manifests/kustomization.yaml:24`는 주석 처리되어 있다.
- 2차는 README의 service 목록을 default deployment보다 우선해 잘못된 default/optional 판정을 만들었다.
- `cartservice`가 Redis 부재 시 memory store로 fallback한다고 설명하면서 관계 카드에서는 Redis를 “기본 manifest에서 필수”라고 단정해 application requiredness와 deployment selection을 혼합했다.
- 두 실행 모두 per-component card 대신 큰 Markdown table을 사용해 Skill의 exact output contract를 위반했다.

### 불필요하게 분석한 파일

- 1차 결과는 `genproto` generated file과 test file을 runtime 제외 근거로 인용했다. `protos/`, `genproto/`, `*_test.*` naming과 build/deployment inventory만으로 제외 가능해 대표 파일의 본문을 열 필요가 없었다.

### 수동 확인이 필요했던 항목

- default deployment와 development Skaffold에서의 `loadgenerator` 활성화 차이
- Redis, memory, Spanner, AlloyDB 중 cart state backend
- optional shopping assistant 활성화와 cloud identity/Secret
- image registry/tag overlay

### 평가

| 평가 항목 | 판정 | 근거 |
|---|---|---|
| 언어 식별 | 통과 | Java/Python/Node 및 추가 언어 모두 정확 |
| 빌드 도구 식별 | 통과 | Gradle, pip, npm과 다른 build tool을 Dockerfile 근거로 식별 |
| 구조 분류 | 실패 | MSA 명시 없음 |
| 서비스 탐색 | 부분 통과 | identity는 모두 찾았으나 default/optional role이 반복 실행에서 다름 |
| 핵심 파일 선택 | 통과 | Kustomization, manifests, Dockerfiles, entrypoints 사용 |
| 명령어 추론 | 통과 | component별 build/start를 직접 근거로 제시 |
| 외부 의존성 | 부분 통과 | graph는 정확하나 Redis requiredness 표현이 내부적으로 상충 |
| 불확실성 관리 | 통과 | optional cloud 기능과 image/persistence를 분리 |
| 결과 일관성 | 부분 통과 | service identity는 같지만 default/optional과 Redis 역할 판정이 다름 |

최종 판정: **부분 통과**

# 3. 커버리지 요약

## 정량 요약

| 항목 | 결과 |
|---|---|
| 검증 레포지토리 | 8 |
| 독립 Skill 실행 | 16 |
| Java/Python/Node.js 포함 | 충족 |
| Maven/Gradle/pip/Poetry/uv/npm/yarn/pnpm 포함 | 충족 |
| Single/Mono-Repo/MSA 사례 포함 | 충족 |
| package/unit test | 17/17 통과 |
| 실제 생성 보고서 `validate_report.py` | 0/16 통과 |
| 명시적인 Single/Mono/MSA 분류 | 0/16 |
| deployable component identity 반복 일치 | 8/8 |
| component role/default 여부까지 반복 일치 | 6/8 |
| 최종 readiness verdict | 16/16 `추가 정보 필요` |

## 안정적으로 지원 가능한 범위

- manifest와 runtime entrypoint가 명확한 Java, Python, Node.js 언어/framework 식별
- `pom.xml`, `build.gradle`, `pyproject.toml`, `package.json`, lockfile, Dockerfile에 근거한 build/runtime 탐색
- Dockerfile에 production startup이 있는 단일 backend/API
- package script가 명확한 Node.js application
- static frontend와 server runtime의 구분
- mono-repo의 복수 app root 탐색
- MSA의 서비스 identity와 service-to-service address 탐색
- DB, cache, broker, external API, build-time frontend endpoint 탐색
- 확인되지 않은 image, probe, port, persistence를 `미확인`으로 남기는 동작

## 부분적으로 지원 가능한 범위

- multiple build path가 공존하는 Java project의 authoritative build/start 선택
- 하나의 source package에서 API/worker가 분리되는 multi-process application
- dev/prod Compose가 서로 다른 repository
- formal workspace가 없는 mono-repo와 `packages: []` workspace metadata
- npm/yarn lock이 한 component에 공존하는 repository
- Kustomize overlay와 주석 처리된 default resource가 많은 MSA
- application dependency requiredness와 default deployment selection의 분리
- framework public environment variable의 build/start timing
- exact Markdown output contract 준수

## 현재 지원이 어려운 범위

- 동일 입력에서 default/optional component role을 안정적으로 재현하는 것
- application component, auxiliary workload, third-party infrastructure를 일관된 계층으로 분류하는 것
- repository에 explicit production command가 없을 때 evidence status를 유지하면서 유용한 startup 후보를 제시하는 것
- generated report가 bundled validator를 실제로 통과하도록 exact schema를 재현하는 것
- generic resource/security policy 부재와 실제 analysis blocker를 구분해 readiness verdict를 다양하게 내리는 것

## 반복 성공 패턴

1. `manifest/lockfile + production container/deployment + entrypoint`가 있는 경우 언어, framework, build, startup, port는 안정적으로 맞았다.
2. package manifest만으로 workload를 만들지 않고 runtime entrypoint를 확인하는 규칙은 router, devDependency, mock server를 올바르게 제외했다.
3. frontend API URL은 client code와 build config를 함께 볼 때 실제 caller와 timing까지 정확했다.
4. Dockerfile이 없는 경우에도 Node package script와 entrypoint로 build/start를 찾았다.
5. Secret 값은 출력하지 않고 이름과 사용 위치만 보존했다.

## 반복 실패 패턴

| 범주 | 반복 관찰 |
|---|---|
| Repository structure | 8개 레포지토리, 16개 결과 모두 Single/Mono/MSA 명시 분류 없음 |
| Output schema | 16개 결과 모두 bundled validator 실패 |
| Evidence validity | Poetry 1차 결과에서 실제 파일 길이를 벗어난 line citation이 최소 9개였지만 validator가 탐지하지 못함 |
| Exact keys | `언어/런타임`, `빌드/운영 기동`처럼 required key를 결합 |
| Verdict format | `판정: **추가 정보 필요**`처럼 bold를 넣어 validator가 판정을 인식하지 못함 |
| Component taxonomy | Spring DB, Lab external infra, MSA Redis의 포함 수준이 서로 다름 |
| Default/optional precedence | Lab dev/prod 차이와 MSA의 commented Kustomize resource에서 흔들림 |
| Node manager | npm command는 찾지만 lockfile 기반 manager 선언을 생략하거나 npm/yarn conflict를 놓침 |
| Build semantics | dependency install, application build, image build, official build command를 혼용 |
| Requiredness | code fallback과 default manifest dependency를 하나의 `필수` 값으로 합침 |
| Readiness | 16개 결과 모두 generic 운영 입력 부재를 포함해 `추가 정보 필요`로 종료 |

## 언어·build tool·구조별 패턴

- Java/Maven/Gradle: build file과 CI command 식별은 안정적이었다. dual build project에서 primary path와 production startup 후보는 결정하지 못했다.
- Python/uv: 단일 API는 가장 안정적이었다.
- Python/Poetry: API/worker는 찾았지만 dev/prod configuration conflict에 따라 build 판정이 달라졌다.
- Python/pip in MSA: Dockerfile이 있는 서비스는 build/start가 안정적이었다.
- Node/npm: package script는 안정적이지만 package manager를 별도 결과로 고정하지 않았다.
- Node/yarn: formal workspace가 없어도 app root는 모두 찾았다.
- Node/pnpm: `packageManager`는 찾았지만 `pnpm-workspace.yaml` 존재와 실제 workspace member 유무를 구조 분류에 연결하지 않았다.
- Single: deployable identity는 안정적이나 명시 분류가 없었다.
- Mono-Repo: app root 탐색은 성공했으나 명시 분류와 mixed manager 판정이 없었다.
- MSA: 모든 service identity와 graph는 찾았으나 default/optional role과 external infrastructure 계층이 불안정했다.

# 4. Skill 개선 계획

## 4.1 Repository structure 판정 gate 추가

- 적용 범위: 공통 규칙
- 관찰된 사실: 8개 레포지토리의 16개 결과 모두 deployable component는 찾았지만 `Single`, `Mono-Repo`, `MSA`를 명시하지 않았다.
- 현재 Skill의 문제: component discovery는 있지만 repository topology를 판정하는 단계와 출력 field가 없다.
- 추가 또는 변경할 규칙:
  1. inventory 직후 `Repository Structure`를 반드시 판정한다.
  2. 하나의 application source root는 process가 여러 개여도 `Single Repository / multi-process`로 기록한다.
  3. 서로 다른 app/package root가 둘 이상이면 formal workspace file 유무와 관계없이 `Mono-Repository`로 기록한다.
  4. 독립 build/runtime root가 여러 개이고 runtime network boundary가 있으면 `MSA Repository`로 기록한다.
  5. 결과에 exact key `Repository Structure:`를 추가하고 `확인됨|추정됨|미확인` 근거를 붙인다.
- 변경 대상 파일 또는 절차: `SKILL.md` Required Workflow, `references/repository-analysis-checklist.md`, summary/detailed template, `scripts/validate_report.py`, `tests/test_package.py`
- 기대 효과: 사용자가 요구한 topology 판정이 0/16에서 필수 출력으로 바뀌고, component 수와 structure를 혼동하지 않는다.
- 우선순위: P0

## 4.2 Exact output schema를 생성 규칙으로 승격

- 적용 범위: 공통 규칙
- 관찰된 사실: package test 17개는 모두 통과했지만 실제 보고서 16개는 모두 validator에 실패했다. 결합 key, table card, bold verdict가 반복 원인이었다.
- 현재 Skill의 문제: template은 exact key를 보여 주지만 “각 key를 합치지 말 것”, “component table로 대체하지 말 것”, “verdict value에 Markdown 강조를 넣지 말 것”이 명시되어 있지 않다. unit test는 수작업으로 완벽한 fixture만 검사한다.
- 추가 또는 변경할 규칙:
  1. component마다 여섯 category와 모든 required key를 그대로 반복한다.
  2. `언어/런타임`, `빌드/운영 기동`처럼 key를 합치지 않는다.
  3. summary에서도 component table로 card를 대체하지 않는다.
  4. verdict는 정확히 `- 판정: 준비됨|추가 정보 필요|진행 불가`로 쓰고 value에 bold/backtick을 넣지 않는다.
  5. 파일 저장 요청이면 최종 응답 전에 `validate_report.py`를 실행하고 실패 시 수정한다.
  6. response-only이면 validator와 동일한 self-check 목록을 Completion Gate에 넣는다.
  7. local checkout 분석에서는 validator에 analysis root를 전달해 인용 파일의 존재와 line range를 검사한다. URL 분석에서는 connector가 반환한 blob의 line range를 생성 시점에 확인한다.
- 변경 대상 파일 또는 절차: `SKILL.md` Output Contract/Completion Gate, 두 template, `scripts/validate_report.py`, `tests/test_package.py`, `tests/scenarios.md`
- 기대 효과: 의미적으로 맞지만 기계 소비가 불가능한 보고서를 줄이고 실제 output과 validator의 계약을 일치시킨다.
- 우선순위: P0

## 4.3 Application, auxiliary workload, infrastructure taxonomy 분리

- 적용 범위: 공통 규칙
- 관찰된 사실: Spring의 PostgreSQL은 application과 같은 component card로 포함됐고, Lab의 PostgreSQL/Redis/RabbitMQ/MinIO는 external infrastructure로 제외됐으며, MSA의 Redis는 실행마다 component 포함 수준이 달랐다.
- 현재 Skill의 문제: “deployable component”가 repo-owned application, repo-owned auxiliary job, third-party stateful service를 모두 수용해 결과가 일관되지 않다.
- 추가 또는 변경할 규칙:
  1. candidate를 `application workload`, `repo-owned auxiliary workload`, `third-party infrastructure`, `development/test only`, `library/build only`로 먼저 분류한다.
  2. application card는 앞의 두 범주에만 생성한다.
  3. third-party image 기반 DB/cache/broker는 dependency/infrastructure section에 기록하고 “repository manifest로 함께 배포되는가”를 별도 field로 둔다.
  4. one-time initialization은 Job 후보로 분리한다.
- 변경 대상 파일 또는 절차: `references/repository-analysis-checklist.md`, `references/dependency-analysis.md`, 두 template
- 기대 효과: PostgreSQL, Redis, MinIO 같은 구성 요소가 레포지토리마다 다른 계층으로 나타나는 문제를 줄인다.
- 우선순위: P0

## 4.4 Default, optional, development configuration 우선순위 고정

- 적용 범위: 공통 규칙
- 관찰된 사실: Spring은 H2와 외부 DB profile이 공존했고, Lab은 dev/prod Compose가 달랐으며, MSA 2차 결과는 주석 처리된 `loadgenerator.yaml`을 default resource로 잘못 포함했다.
- 현재 Skill의 문제: README service 목록, development Compose, production Compose, default Kustomization, optional component 사이의 evidence precedence가 없다.
- 추가 또는 변경할 규칙:
  1. runtime source의 required/fallback 동작을 최우선으로 확인한다.
  2. 배포 활성화 판정은 production manifest와 default Kustomization의 실제 활성 entry를 우선한다.
  3. 주석 처리된 resource와 disabled overlay는 default에서 제외하고 `optional`로 기록한다.
  4. README 목록은 inventory seed로만 사용하고 활성화 근거로 사용하지 않는다.
  5. dev-only Compose service는 production component로 승격하지 않는다.
- 변경 대상 파일 또는 절차: `references/workflow.md`, `references/repository-analysis-checklist.md`, `references/evidence-and-readiness.md`
- 기대 효과: Lab scheduler와 MSA loadgenerator 같은 default/optional 판정의 반복 실행 차이를 줄인다.
- 우선순위: P0

## 4.5 Node package manager와 workspace 판정 규칙 추가

- 적용 범위: 공통 규칙
- 관찰된 사실: Vitesse는 `pnpm-workspace.yaml`이 있지만 `packages: []`이고 Single Repository였다. Bulletproof React는 formal workspace file 없이 세 앱을 가진 mono-repo였다. Jira client에는 npm/yarn lock이 공존했지만 conflict가 보고되지 않았다.
- 현재 Skill의 문제: Node 규칙이 `package.json`, workspace file, lockfile을 “inspect”하라고만 하고 authoritative manager와 실제 workspace member 판정 방법을 정의하지 않는다.
- 추가 또는 변경할 규칙:
  1. root와 각 component별로 `packageManager`, lockfile, scripts에서 manager를 기록한다.
  2. 서로 다른 lockfile이 같은 scope에 있으면 `상충됨`으로 기록한다.
  3. workspace file 존재만으로 mono-repo로 판단하지 않고 member glob의 실제 match를 확인한다.
  4. formal workspace가 없어도 root orchestration과 복수 deployable root가 있으면 mono-repo로 판정한다.
- 변경 대상 파일 또는 절차: `references/language-discovery-rules.md`, `references/repository-analysis-checklist.md`
- 기대 효과: npm/yarn/pnpm 식별과 Single/Mono 판정이 lockfile 배치에 따라 흔들리지 않는다.
- 우선순위: P1

## 4.6 Build/start evidence ladder 분리

- 적용 범위: 공통 규칙
- 관찰된 사실: Spring은 production startup 후보를 전부 미확인으로 남겼고, Lab은 Dockerfile 내부 install step과 공식 build command를 실행마다 다르게 취급했다. Vitesse/Bulletproof는 preview와 production server를 올바르게 구분했다.
- 현재 Skill의 문제: dependency install, application build, image build, production startup을 별도 field로 판정하는 evidence ladder가 없다.
- 추가 또는 변경할 규칙:
  1. `dependency install`, `application build`, `image build`, `production startup`을 분리한다.
  2. production evidence precedence는 deployment command/args → container ENTRYPOINT/CMD → production package script → CI release step → README local command 순서로 둔다.
  3. explicit production command가 없고 executable artifact만 확인되면 후보 command를 `추정됨`으로 제시하고 artifact path 미확인은 보존한다.
  4. `vite preview`, `webpack-dev-server`, `bootRun`, `spring-boot:run`은 production 근거 없이 확정하지 않는다.
- 변경 대상 파일 또는 절차: `references/workflow.md`, `references/language-discovery-rules.md`, `references/evidence-and-readiness.md`
- 기대 효과: 보수성을 유지하면서도 Spring executable JAR 같은 유용한 후보를 제공하고 Lab 같은 build status 불일치를 줄인다.
- 우선순위: P1

## 4.7 Dependency requiredness와 deployment selection 분리

- 적용 범위: 공통 규칙
- 관찰된 사실: MSA 결과는 cartservice가 Redis 없을 때 memory store로 fallback한다고 기록하면서 `cartservice -> redis-cart`를 필수로 단정했다. Lab은 broker/result backend를 여러 external service로 나눴다.
- 현재 Skill의 문제: application code가 요구하는 dependency와 default manifest가 선택한 dependency를 하나의 `required` field로 합친다.
- 추가 또는 변경할 규칙:
  1. `application requiredness`와 `selected in analyzed deployment`를 별도 field로 둔다.
  2. fallback이 있으면 application requiredness는 `optional` 또는 조건부로 기록한다.
  3. default manifest가 endpoint를 설정했으면 “default deployment에서 선택됨”으로 기록하되 application 필수로 승격하지 않는다.
  4. dependency matrix와 component card의 requiredness가 같은지 Completion Gate에서 확인한다.
- 변경 대상 파일 또는 절차: `references/dependency-analysis.md`, 두 template, `scripts/validate_report.py`
- 기대 효과: Redis, memory fallback, managed DB overlay가 공존해도 내부적으로 모순 없는 graph를 생성한다.
- 우선순위: P1

## 4.8 High-signal two-pass inventory와 stop rule 추가

- 적용 범위: 공통 규칙
- 관찰된 사실: uv 사례는 generic `.gitignore`와 transitive lock record를 넓게 읽었고, Bulletproof는 test-only임을 확인한 뒤에도 mock handler를 반복 탐색했으며, MSA는 generated/test file 본문을 제외 근거로 사용했다.
- 현재 Skill의 문제: high-signal inventory를 요구하지만 탐색 순서와 중단 조건이 없다.
- 추가 또는 변경할 규칙:
  1. 1차 pass는 root/workspace manifest, lockfile header, Docker/Compose/Kubernetes, CI, env example만 읽는다.
  2. 2차 pass는 각 candidate의 runtime entrypoint와 unresolved dependency/configuration만 읽는다.
  3. generated/test/dev-only 여부가 manifest/path/command로 확정되면 내부 source 탐색을 중단한다.
  4. lockfile은 manager와 direct/resolved runtime version 확인에 필요한 section만 읽는다.
- 변경 대상 파일 또는 절차: `references/workflow.md`, `references/language-discovery-rules.md`
- 기대 효과: 단순 레포지토리에서 불필요한 파일 탐색을 줄이고 MSA에서도 핵심 file budget을 service 수에 비례해 통제한다.
- 우선순위: P1

## 4.9 Readiness blocker 판정 범위 축소

- 적용 범위: 공통 규칙
- 관찰된 사실: 16개 결과가 모두 `추가 정보 필요`였고, 다수 결과가 resource limit, HPA, PDB, serviceAccount 같은 generic 운영 정책을 설계 차단 항목으로 포함했다.
- 현재 Skill의 문제: 저장소에 없는 운영 정책을 만들지 말라는 규칙은 있지만, 그 부재가 실제 후속 설계를 차단하는지 판단하는 기준이 약하다.
- 추가 또는 변경할 규칙:
  1. blocker는 component identity, build/start, image 생성 경로, listener/non-listener, required configuration/dependency처럼 최소 manifest 초안을 실제로 막는 값으로 제한한다.
  2. resource/security/scaling policy는 사용자가 full production readiness를 요청하지 않은 summary에서 non-blocking unknown으로 분리한다.
  3. 기존 manifest로 후보 초안이 가능한 경우 registry naming 같은 외부 결정만으로 모든 분석을 미완료로 취급하지 않는다.
- 변경 대상 파일 또는 절차: `SKILL.md` 준비 상태 판정, `references/evidence-and-readiness.md`, 두 template
- 기대 효과: 모든 repository가 같은 verdict로 수렴하는 현상을 줄이고 분석 완료와 운영 결정 미정 상태를 구분한다.
- 우선순위: P1

## 4.10 실제 생성물 기반 regression fixture 추가

- 적용 범위: 검증 절차
- 관찰된 사실: 수작업 `VALID_SUMMARY` 기반 unit test는 17/17 통과했지만 실제 Skill 생성물은 0/16 통과했다. Poetry 1차 결과의 out-of-range citation도 현재 정규식 기반 validator를 통과 가능한 근거 모양으로 인식됐다.
- 현재 Skill의 문제: validator의 자체 동작만 검사하고 Skill이 실제로 생성하는 변형을 회귀 테스트하지 않는다.
- 추가 또는 변경할 규칙:
  1. 이번 검증에서 관찰한 최소 변형 fixture를 추가한다: combined key, bold verdict, component table, line 없는 path, malformed absence evidence.
  2. Java dual-build, Python multi-process, Node mixed-lock, MSA optional resource의 normalized expected fact fixture를 추가한다.
  3. 반복 결과에서 component set, structure, build/start, required dependency, verdict를 비교하는 deterministic comparison script를 둔다.
  4. `validate_report.py --repo-root <path>`를 추가해 file existence와 cited end line이 실제 file length 이하인지 검사한다.
- 변경 대상 파일 또는 절차: `tests/fixtures/`, `tests/test_package.py`, `tests/scenarios.md`, `scripts/validate_report.py`, 신규 `scripts/compare_reports.py`
- 기대 효과: validator unit test 통과와 실제 Skill output 성공 사이의 차이를 CI에서 조기에 발견한다.
- 우선순위: P0

## 예외 규칙으로 분리할 사례

다음은 한 레포지토리에서만 관찰됐으므로 공통 규칙으로 일반화하지 않는다.

1. Vitesse: `pnpm-workspace.yaml`의 `packages: []`는 workspace metadata가 있어도 실제 member가 없는 예외다.
2. Spring Petclinic: Maven과 Gradle이 동일 application의 동등한 build path로 공존한다. primary tool을 임의 지정하지 않는다.
3. Lab Python Server: production Compose의 worker가 `Dockerfile`과 `.env.development`를 참조한다. 일반 규칙으로 해소하지 않고 repository conflict로 보존한다.
4. Microservices Demo: `loadgenerator.yaml`은 파일과 Deployment가 존재하지만 default Kustomization에서는 주석 처리되어 있다.
5. Bulletproof React: `/healthcheck`는 mock handler에만 존재하므로 production health endpoint로 승격하지 않는다.
6. Jira Clone: production `API_URL`은 runtime env가 아니라 Webpack config에 고정된 build-time 값이다.
7. Lab Python Server 1차 결과의 비정상적으로 큰 line number는 다른 레포지토리에서는 재현되지 않았다. 공통 분석 규칙으로 일반화하지 않고 citation range regression fixture로 보존한다.

## 개선 적용 순서

1. P0: structure gate, component taxonomy, default/optional precedence, exact schema, real-output regression fixture
2. P1: Node manager/workspace, build/start evidence ladder, dependency requiredness, two-pass inventory, blocker 범위
3. P0 변경 후 동일 8개 commit에 2회씩 재실행
4. 종료 기준: structure 분류 16/16, validator 16/16, component role 반복 일치 8/8, 기존 semantic correctness 유지
