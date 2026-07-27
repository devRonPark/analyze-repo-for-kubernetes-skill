# OSS Runtime Fixture 후보 조사 (2026-07-27)

## 결론

현 `runtime_signal_extractors.py` v1의 API·한 줄 매칭 경계로는 **언어당
하나의 실제 OSS 저장소에서 다섯 runtime signal family를 모두 검증하는
fixture 후보를 선정하지 않았다.** 아래 후보는 원본 GitHub source와
`LICENSE`를 고정 commit에서 직접 확인한 partial evidence이며, 성공한
fixture 후보가 아니다.

특히 writable-path 규칙은 `fs.writeFile(process.env.KEY, ...)`,
`open(os.environ["KEY"], "w")`,
`Files.write(... System.getenv("KEY") ...)`,
`os.WriteFile(os.Getenv("KEY"), ...)`처럼 **환경 변수 읽기와 쓰기 호출이
한 source line 안에 있어야** 한다. 실제 애플리케이션은 대개 값을 먼저
변수에 담거나 구성 객체를 거치므로 이 조건을 충족하지 않는다. 검색에서
발견된 다수의 일치는 test, benchmark, CI helper 또는 build script였다.

따라서 이 문서는 #46의 fixture를 추가할 근거가 아니라, 현재 설계의
후속 결정을 위한 evidence다. 부족한 근거를 fixture로 복사하거나 source를
합성하지 않는다.

## 평가 기준

- 모든 인용은 `2026-07-27`에 확인한 GitHub의 immutable commit blob과
  해당 commit의 `LICENSE`다.
- `예`는 현 extractor가 해당 line을 실제로 수집할 수 있음을 뜻한다.
  `아니오`는 아래 선택된 최소 source path에 family 근거가 없음을 뜻하며,
  저장소 전체의 런타임 동작 부재를 뜻하지 않는다.
- fixture는 원본 source만 포함해야 하며 test·example·vendor·generated
  code 및 CI/build script를 우선 후보에서 제외한다.

| 언어 | 저장소 / 고정 revision | 라이선스 | config | listener | outbound | writable | background | 판정 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Node.js | [`webpack/webpack-sources`](https://github.com/webpack/webpack-sources/tree/0872bcd7639be8c3559571b10f03aae20135c461) | [MIT](https://github.com/webpack/webpack-sources/blob/0872bcd7639be8c3559571b10f03aae20135c461/LICENSE) | 예 | 아니오 | 아니오 | 예 | 아니오 | 제외: benchmark source이며 5-family 불충족 |
| Python | [`MeshInspector/MeshLib`](https://github.com/MeshInspector/MeshLib/tree/d76fb2548fc31400842e6550d6c223ec4fbc4fa5) | [비상업·교육 전용](https://github.com/MeshInspector/MeshLib/blob/d76fb2548fc31400842e6550d6c223ec4fbc4fa5/LICENSE) | 예 | 아니오 | 아니오 | 예 | 아니오 | 제외: fixture 재배포에 부적합한 라이선스 및 CI helper |
| Java | [`actionbronson/LazyMan`](https://github.com/actionbronson/LazyMan/tree/c7282057e6675c5d667553a6c55e6c2fcd5bb559) | root `LICENSE` 없음 (확인 불가) | 예 | 아니오 | 아니오 | 예 | 아니오 | 제외: 라이선스 불명확·hosts 수정 utility |
| Go | [`plandex-ai/plandex`](https://github.com/plandex-ai/plandex/tree/e2d772072efadbe41d2946d97d79be55532dbab5) | [MIT](https://github.com/plandex-ai/plandex/blob/e2d772072efadbe41d2946d97d79be55532dbab5/LICENSE) | 예 | 아니오 | 아니오 | 예 | 아니오 | 제외: 실제 application source이나 현 five-family 단일-repo 기준 불충족 |

## 원본 source 근거

### Node.js — `webpack/webpack-sources`

- 고정 revision: `0872bcd7639be8c3559571b10f03aae20135c461`
- 원본 경로: [`benchmark/run.mjs#L194-L195`](https://github.com/webpack/webpack-sources/blob/0872bcd7639be8c3559571b10f03aae20135c461/benchmark/run.mjs#L194-L195)
- `fs.writeFile(process.env.BENCH_OUTPUT, ...)`는 `process.env` config read와
  `fs.writeFile` writable path를 동시에 만족한다.
- 그러나 경로가 production application source가 아닌 benchmark이고,
  listener (`.listen`), PostgreSQL `new Client({ connectionString: ... })`,
  `setInterval`의 원본 근거를 이 최소 source 후보에서 제공하지 않는다.

### Python — `MeshInspector/MeshLib`

- 고정 revision: `d76fb2548fc31400842e6550d6c223ec4fbc4fa5`
- 원본 경로: [`scripts/devops/collect_artifact_stats.py#L15-L16`](https://github.com/MeshInspector/MeshLib/blob/d76fb2548fc31400842e6550d6c223ec4fbc4fa5/scripts/devops/collect_artifact_stats.py#L15-L16)
- `open(os.environ['STATS_FILE'], 'w')`는 config read와 writable path를
  만족한다.
- 그러나 source는 devops script이고, pinned `LICENSE`는 non-commercial /
  education-only 조건이므로 repository fixture에 복사하지 않는다. listener,
  `requests.get(os.getenv(...))`, `.add_job` 근거도 제공하지 않는다.

### Java — `actionbronson/LazyMan`

- 고정 revision: `c7282057e6675c5d667553a6c55e6c2fcd5bb559`
- 원본 경로: [`src/Util/EditHosts.java#L108-L113`](https://github.com/actionbronson/LazyMan/blob/c7282057e6675c5d667553a6c55e6c2fcd5bb559/src/Util/EditHosts.java#L108-L113)
- `Files.write(Paths.get(System.getenv("WINDIR") + ...))`는 config read와
  writable path를 만족한다.
- root `LICENSE` blob이 존재하지 않아 보관·복사 권한을 확인할 수 없다.
  또한 Windows hosts file utility는 Kubernetes runtime representative source가
  아니며 `DriverManager.getConnection(System.getenv(...))`, literal
  `HttpServer.create(new InetSocketAddress(...))`, `@Scheduled` 근거를 제공하지 않는다.

### Go — `plandex-ai/plandex`

- 고정 revision: `e2d772072efadbe41d2946d97d79be55532dbab5`
- 원본 경로: [`app/cli/stream_tui/run.go#L102-L104`](https://github.com/plandex-ai/plandex/blob/e2d772072efadbe41d2946d97d79be55532dbab5/app/cli/stream_tui/run.go#L102-L104)
- line 102의 `os.Getenv("PLANDEX_REPL")`와 line 104의
  `os.WriteFile(os.Getenv("PLANDEX_REPL_OUTPUT_FILE"), ...)`는 config read 및
  writable path를 직접 제공한다.
- 이는 실제 application source이고 MIT지만, 선택된 source에
  `sql.Open(... os.Getenv(...))`, literal `http.ListenAndServe("host:port", ...)`,
  `cron.AddFunc`가 없다. 따라서 이 저장소를 five-family fixture로 복사하지 않는다.

## 결정이 필요한 사항

현재 #46 명세의 “언어별 단일 저장소 + 모든 다섯 family” 조건을 유지하려면
extractor의 API 경계를 현실적인 명시적 source 패턴으로 확장한 뒤 후보 조사를
다시 해야 한다. 예를 들어 환경 변수를 앞선 line에서 변수에 할당한 뒤 그 변수를
`Files.write`/`os.WriteFile`에 전달하는 형태는 현재 수집하지 않는다.

반대로 extractor 변경 없이 #46을 진행하려면 명세를 다음 중 하나로 명시적으로
바꾸어야 한다.

1. 언어별 fixture를 여러 공개 OSS source 조각으로 허용하고 family별 upstream
   provenance를 manifest에 보관한다.
2. language fixture가 다섯 family 전체가 아니라, 실제 OSS에서 확보 가능한
   extractor API family만 검증하게 범위를 축소한다.

두 선택 모두 현재 명세의 단일-repo·five-family 계약을 바꾸므로, 결정 전에는
fixture·테스트를 추가하지 않는다.
