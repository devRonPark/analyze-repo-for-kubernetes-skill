# Evidence Pattern Packs

이 문서는 repository-to-Kubernetes 분석에서 사용하는 근거 패턴 pack의 경계를 정의한다. 패턴은 결론 엔진이 아니라 근거 수집 규칙이다. 패턴은 line-addressable typed evidence를 빠르게 찾고 분류하지만, component decision, production readiness, deployable ownership, default deployment path, requiredness는 판단하지 않는다.

전체 흐름은 `Universal Scanner -> Evidence Pattern Packs -> LLM Triage/Reasoning -> Deterministic Verifier -> Report`이다. Universal scanner와 pattern pack은 candidate evidence를 만들고, LLM triage가 의미를 해석하며, deterministic verifier가 schema, citation validity, unsupported claim, secret leakage를 최종 방어선에서 차단한다.

## Universal scanner

Universal scanner는 파일 시스템을 얕고 넓게 훑어 pattern pack이 읽을 후보를 만든다.

- repository root, subdirectory, workspace root, package root 후보를 기록한다.
- generated output, dependency cache, vendored code, binary asset를 기본 제외한다.
- manifest, lockfile, container definition, deployment manifest, CI workflow, framework configuration, entrypoint, environment access, DB/broker configuration을 우선한다.
- 존재하는 사실은 `path/to/file:line` 또는 `path/to/file:start-end`로, 부재 확인은 `검색(scope=..., pattern=..., result=없음)`으로만 남긴다.
- 파일 존재, key 존재, command 문자열, declared dependency처럼 수집 가능한 사실만 만든다. deployable 여부나 운영 준비 상태는 판단하지 않는다.

## Docker pack

Docker pack은 `Dockerfile`, `Containerfile`, `.dockerignore`, image build 설정에서 containerization 근거를 수집한다.

- `FROM`, `COPY`, `RUN`, `USER`, `WORKDIR`, `ENV`, `EXPOSE`, `ENTRYPOINT`, `CMD`, `HEALTHCHECK`를 typed evidence로 기록한다.
- image build 가능성, runtime command, exposed port, health behavior, writable path 단서를 분리한다.
- Dockerfile이 없으면 실패가 아니라 `검색(scope=..., pattern=Dockerfile|Containerfile, result=없음)` 근거를 만든다.
- `EXPOSE`만으로 Service 필요성이나 production listener를 확인됨으로 판단하지 않는다.

## Compose pack

Compose pack은 `compose.yaml`, `docker-compose.yml`, override 파일에서 local launch evidence를 수집한다.

- service name, image/build, command, entrypoint, ports, expose, volumes, env, depends_on, profiles, networks를 기록한다.
- DB, cache, broker, proxy service는 `저장소에 정의된 런타임 의존성` 후보 근거로 남긴다.
- Compose service는 repository launch definition일 수 있지만, 운영 환경 배포 기준 구성으로 판단하지 않는다.
- host port mapping은 개발 편의일 수 있으므로 production ingress나 Service port로 확정하지 않는다.

## Kubernetes pack

Kubernetes pack은 plain manifest와 GitOps directory 안의 Kubernetes resource 근거를 수집한다.

- `Deployment`, `StatefulSet`, `DaemonSet`, `Job`, `CronJob`, `Service`, `Ingress`, `ConfigMap`, `Secret`, `PersistentVolumeClaim`의 resource kind와 metadata를 기록한다.
- container image, command, args, ports, env, probes, volumeMounts, resources, serviceAccountName을 component별 candidate evidence로 연결한다.
- manifest가 repository launch definition과 상충하면 양쪽을 `상충됨`으로 보존한다.
- Secret 값은 출력하지 않고 key 이름과 사용 위치만 기록한다.

## Helm pack

Helm pack은 `Chart.yaml`, `values.yaml`, `templates/`에서 배포 선언 근거를 수집한다.

- chart name, app version, template resource kind, values key, default image, port, probe, env, volume 설정을 기록한다.
- values override 파일과 environment-specific values를 분리한다.
- template 조건문은 가능한 deployment path 후보를 만들 수 있지만, 활성 운영 경로를 단정하지 않는다.

## Kustomize pack

Kustomize pack은 `kustomization.yaml`과 overlay를 읽어 resource composition 근거를 수집한다.

- resources, patches, images, configMapGenerator, secretGenerator, namespace, commonLabels를 기록한다.
- base와 overlay의 resource 변경을 분리하고, 특정 overlay가 production baseline인지 별도 근거 없이 판단하지 않는다.
- generated Secret 값은 노출하지 않는다.

## GitHub Actions pack

GitHub Actions pack은 `.github/workflows/*.yml`과 `.yaml`에서 CI/CD 근거를 수집한다.

- job name, trigger, path filter, build/test/deploy step, image build/push, Helm/Kustomize/kubectl invocation을 기록한다.
- CI job은 candidate evidence일 뿐이며 deployable ownership이나 production readiness를 직접 뜻하지 않는다.
- release workflow가 있어도 실제 배포 대상과 환경은 workflow step, environment, manifest 근거를 인용해 LLM triage에서 판단한다.

## Java pack

Java pack은 Maven, Gradle, Spring Boot, Jakarta EE, Micronaut, Quarkus 근거를 수집한다.

- `pom.xml`, `build.gradle`, `settings.gradle`, wrapper, `application.yml`, main class, profile config를 기록한다.
- Maven과 Gradle이 공존하면 component별 범위와 wrapper 위치를 분리한다.
- framework dependency는 web/server 가능성의 candidate evidence지만 deployable runtime을 확정하지 않는다.

## Node pack

Node pack은 Node.js와 TypeScript application 근거를 수집한다.

- `package.json`, `packageManager`, workspace 선언, lockfile, framework config, scripts, source entrypoint, env access를 기록한다.
- `dev` script는 development command로, `start`나 framework production build output은 production startup 후보로 분리한다.
- root package manager가 nested component의 더 강한 선언을 덮어쓰지 않는다.

## Python pack

Python pack은 Python service, worker, script 근거를 수집한다.

- `pyproject.toml`, `requirements*.txt`, lockfile, WSGI/ASGI 설정, Celery/RQ worker, management command, migration tool을 기록한다.
- dependency declaration만으로 runtime communication을 확인됨으로 판단하지 않는다.
- notebook, test utility, one-off script는 deployable candidate와 제외 후보를 모두 열어 두고 실행 근거로 판별한다.

## Go pack

Go pack은 Go module과 binary entrypoint 근거를 수집한다.

- `go.mod`, `go.work`, `cmd/`, `main` package, flags, env access, server binding, build workflow를 기록한다.
- 여러 binary가 있으면 component별 command와 listener 여부를 분리한다.
- module 존재만으로 long-running workload를 판단하지 않는다.

## .NET pack

.NET pack은 ASP.NET Core, worker service, console app 근거를 수집한다.

- `.sln`, `.csproj`, `Program.cs`, hosting configuration, `appsettings*.json`, publish profile을 기록한다.
- `launchSettings.json`은 development evidence로만 취급한다.
- hosted service와 HTTP listener를 분리해 component candidate를 만든다.

## Ruby/Rails pack

Ruby/Rails pack은 Rails, Rack, Sidekiq, Rake 근거를 수집한다.

- `Gemfile`, `Gemfile.lock`, `config.ru`, `config/puma.rb`, `config/database.yml`, `Procfile`, Sidekiq config, Rake task를 기록한다.
- Rails app 존재만으로 web, worker, migration job을 모두 배포해야 한다고 판단하지 않는다.
- database config는 secret 값 없이 key와 environment scope만 기록한다.

## PHP/Laravel pack

PHP/Laravel pack은 Laravel, Symfony, PHP-FPM, queue worker 근거를 수집한다.

- `composer.json`, `composer.lock`, `artisan`, route/config files, queue config, scheduler command, PHP-FPM 또는 web server config를 기록한다.
- `artisan serve`는 development command로 취급한다.
- worker와 scheduler는 command 근거가 있을 때 별도 deployable candidate로 둔다.

## Rust pack

Rust pack은 Rust workspace와 binary 근거를 수집한다.

- `Cargo.toml`, `Cargo.lock`, workspace members, binary targets, features, config loader, server bind code를 기록한다.
- crate dependency만으로 runtime dependency를 확정하지 않는다.
- library crate와 runnable binary를 분리한다.

## Platform hints pack

Platform hints pack은 managed platform 또는 repo operation 단서를 수집한다.

- `Procfile`: process type, command, worker/web 구분 candidate evidence를 기록한다.
- `fly.toml`: app name, build, process, service/port, volume, env key를 기록한다.
- `render.yaml`: service type, buildCommand, startCommand, envVar, database linkage를 기록한다.
- `railway.toml`: build/start command, service settings, plugin hint를 기록한다.
- Cloud Foundry: `manifest.yml`, `Staticfile`, buildpack, route, service binding을 기록한다.
- Serverless: `serverless.yml`, function handler, event source, env, package 설정을 기록한다.
- Nx: `nx.json`, project graph, target, executor, cacheable operation을 기록한다.
- Turbo: `turbo.json`, pipeline/task, package relationship, build output hint를 기록한다.
- `Makefile`: build, test, image, run, deploy target command를 기록한다.
- `Taskfile`: task command, dependency, env, platform condition을 기록한다.

Platform hint는 낮은 비용의 discovery accelerator다. hint가 있다고 해서 해당 platform이 production baseline이거나 Kubernetes migration target이 된다고 판단하지 않는다.

## LLM-discovered hint 승격 기준

LLM triage 중 반복적으로 발견되는 단서는 다음 조건을 모두 만족할 때만 maintained pattern으로 승격한다.

- 공식 owner source 또는 널리 검증 가능한 format reference가 있다.
- 실제 repository에서 반복 발견된다.
- 안정적인 path/line fact를 만들 수 있다.
- 읽기 비용을 낮추고 universal scanner보다 의미 있는 precision을 추가한다.
- false positive 위험이 낮고, 위험이 있을 때 상태를 `추정됨` 또는 `미확인`으로 보존할 수 있다.
- fixture로 검증 가능하며 invalid citation과 secret leakage를 verifier가 잡을 수 있다.
- 패턴 결과가 hard-coded analyzer conclusion이 아니라 extractable evidence fact로 표현된다.
