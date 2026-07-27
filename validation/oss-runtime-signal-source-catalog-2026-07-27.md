# OSS Runtime Signal Source Catalog (2026-07-27)

## 목적과 판정 경계

이 카탈로그는 #46 fixture 후보를 찾기 위해 공개 GitHub의 **고정 commit
source**를 현재 `scripts/runtime_signal_extractors.py` v1에 직접 대조한
결과다. source path가 production source인지, commit 시점의 license가
재배포 가능한지, 그리고 그 source line이 실제 extractor의 단일-line
조건을 만족하는지를 모두 확인한다.

`미확보`는 해당 runtime 사실이 세상에 존재하지 않는다는 주장이 아니다. 이
조사에서 fixture로 복사해도 되는, permissive license의 immutable source
fragment를 아직 확보하지 못했다는 뜻이다. 특히 문서, test, example,
benchmark, CI/build helper, vendor/generated path는 positive fixture 후보가
아니다.

## 확인된 재배포 가능 source fragment

아래 source는 source path와 license를 고정 revision에서 직접 확인했고,
표의 exact source line을 extractor에 입력하여 해당 evidence kind가
생성됨을 확인했다.

| 언어 | family | upstream / license | 고정 source | exact source line | 현재 extractor 결과 |
| --- | --- | --- | --- | --- | --- |
| Node.js | config, outbound | [Sharaal/sql-pg — MIT](https://github.com/Sharaal/sql-pg/blob/85733750e3acd90b1cd227f5de4838964a2bdf04/LICENSE) | [`85733750e3acd90b1cd227f5de4838964a2bdf04/src/sql.query.js#L6`](https://github.com/Sharaal/sql-pg/blob/85733750e3acd90b1cd227f5de4838964a2bdf04/src/sql.query.js#L6) | `sql.client = new Client({ connectionString: process.env.DATABASE_URL })` | `runtime_config_read(DATABASE_URL)`; `runtime_outbound_connection(connection_string, DATABASE_URL)` |
| Node.js | config, writable | [informatics-isi-edu/ErmrestDataUtils — Apache-2.0](https://github.com/informatics-isi-edu/ErmrestDataUtils/blob/7af4a92bbe849e006909ebd86fe49d5aa43dd53c/LICENSE) | [`7af4a92bbe849e006909ebd86fe49d5aa43dd53c/export.js#L31`](https://github.com/informatics-isi-edu/ErmrestDataUtils/blob/7af4a92bbe849e006909ebd86fe49d5aa43dd53c/export.js#L31) | `fs.writeFile(process.env.PWD + ..., ...)` | `runtime_config_read(PWD)`; `runtime_writable_path(PWD)` |
| Node.js | background | [HeyPuter/kv.js — MIT](https://github.com/HeyPuter/kv.js/blob/8f52e8936963268ffb4c26d89e52742572fe9dd3/LICENSE.txt) | [`8f52e8936963268ffb4c26d89e52742572fe9dd3/kv.js#L3219`](https://github.com/HeyPuter/kv.js/blob/8f52e8936963268ffb4c26d89e52742572fe9dd3/kv.js#L3219) | `this.cleanupLoop = setInterval(() => {` | `runtime_background_registration(setInterval)` |
| Python | config, outbound, listener | [aws-samples/build-secure-multi-account-vpc-connnectivity-applications-with-amazon-vpc-lattice — MIT-0](https://github.com/aws-samples/build-secure-multi-account-vpc-connnectivity-applications-with-amazon-vpc-lattice/blob/d8265321cb1a61395ba8ee39e066e1bcef28c33d/LICENSE) | [`d8265321cb1a61395ba8ee39e066e1bcef28c33d/applications/apps-eks/backend.py#L6`](https://github.com/aws-samples/build-secure-multi-account-vpc-connnectivity-applications-with-amazon-vpc-lattice/blob/d8265321cb1a61395ba8ee39e066e1bcef28c33d/applications/apps-eks/backend.py#L6), [`#L17`](https://github.com/aws-samples/build-secure-multi-account-vpc-connnectivity-applications-with-amazon-vpc-lattice/blob/d8265321cb1a61395ba8ee39e066e1bcef28c33d/applications/apps-eks/backend.py#L17), [`#L23`](https://github.com/aws-samples/build-secure-multi-account-vpc-connnectivity-applications-with-amazon-vpc-lattice/blob/d8265321cb1a61395ba8ee39e066e1bcef28c33d/applications/apps-eks/backend.py#L23) | `requests.get(os.getenv("LATTICEURL"))`; `app.run(... host='0.0.0.0', port=8081)` | `runtime_config_read(LATTICEURL)`; `runtime_outbound_connection(http, LATTICEURL)`; `runtime_listener(0.0.0.0, 8081)` |
| Python | config, writable | [tech-otaku/cloudflare-dns — MIT](https://github.com/tech-otaku/cloudflare-dns/blob/93910ddc7ad03ec1de6ea88aab2a4fa332806ba5/LICENSE) | [`93910ddc7ad03ec1de6ea88aab2a4fa332806ba5/get-dns.py#L222`](https://github.com/tech-otaku/cloudflare-dns/blob/93910ddc7ad03ec1de6ea88aab2a4fa332806ba5/get-dns.py#L222) | `with open(os.environ['HOME'] + ..., 'w') as f:` | `runtime_config_read(HOME)`; `runtime_writable_path(HOME)` |
| Python | background | [elliott-farrall/skintel — MIT](https://github.com/elliott-farrall/skintel/blob/cb7aa809036d24084b2fd9f078493cd006116d87/LICENSE) | [`cb7aa809036d24084b2fd9f078493cd006116d87/web.py#L378`](https://github.com/elliott-farrall/skintel/blob/cb7aa809036d24084b2fd9f078493cd006116d87/web.py#L378) | `scheduler.add_job(` | `runtime_background_registration(scheduler.add_job)` |
| Go | config, writable | [plandex-ai/plandex — MIT](https://github.com/plandex-ai/plandex/blob/e2d772072efadbe41d2946d97d79be55532dbab5/LICENSE) | [`e2d772072efadbe41d2946d97d79be55532dbab5/app/cli/stream_tui/run.go#L102-L104`](https://github.com/plandex-ai/plandex/blob/e2d772072efadbe41d2946d97d79be55532dbab5/app/cli/stream_tui/run.go#L102-L104) | `os.WriteFile(os.Getenv("PLANDEX_REPL_OUTPUT_FILE"), ..., 0644)` | `runtime_config_read(PLANDEX_REPL_OUTPUT_FILE)`; `runtime_writable_path(PLANDEX_REPL_OUTPUT_FILE)` |

### 정확히 매치하지만 제외한 source

- [`reneweb/oauth2orize_resource_owner_password_example` at
  `8cc1c642e794306c994feb9365cfb21f79bc23d8`](https://github.com/reneweb/oauth2orize_resource_owner_password_example/blob/8cc1c642e794306c994feb9365cfb21f79bc23d8/app.js#L26)는 MIT이고
  `http.createServer(app).listen(process.env.PORT || 3000, ...)`로 Node
  listener 규칙에 정확히 매치한다. 그러나 repository 자체가 명시적
  `example`이므로 #46의 non-example source 조건상 fixture 후보에서 제외한다.
- [`CircleCI-Public/circleci-demo-docker` at
  `f080cac0f844910b6416f8cbb3e40443c62e0251`](https://github.com/CircleCI-Public/circleci-demo-docker/blob/f080cac0f844910b6416f8cbb3e40443c62e0251/main.go#L18)는 MIT이고
  `http.ListenAndServe(":8080", nil)`로 Go listener 규칙에 정확히
  매치한다. 하지만 repository가 CI Docker demo이므로, 명시된 non-CI/demo
  fixture 기준을 보수적으로 적용해 positive fixture 후보에서는 제외한다.

## Language × family coverage audit

| 언어 | config | listener | outbound | writable | background | fixture 판단 |
| --- | --- | --- | --- | --- | --- | --- |
| Node.js | 확인됨 (`sql-pg`, `ErmrestDataUtils`) | 미확보 | 확인됨 (`sql-pg`) | 확인됨 (`ErmrestDataUtils`) | 확인됨 (`kv.js`) | listener가 없어 5-family fixture 불가 |
| Python | 확인됨 (`vpc-lattice`, `cloudflare-dns`) | 확인됨 (`vpc-lattice`) | 확인됨 (`vpc-lattice`) | 확인됨 (`cloudflare-dns`) | 확인됨 (`skintel`) | 5-family fragment set 확보. fixture 복사 전 source 재검토 필요 |
| Java | 미확보 | 미확보 | 미확보 | 미확보 | 미확보 | permissive·production source fragment 5개 미확보 |
| Go | 확인됨 (`plandex`) | 미확보 | 미확보 | 확인됨 (`plandex`) | 미확보 | listener/outbound/background가 없어 5-family fixture 불가 |

## 왜 미확보인가

현재 implementation은 여러 유효한 runtime 관용구보다 좁다. 예를 들어
Node listener는 `.listen`과 같은 line에 `|| <numeric literal>`가 있어야 하고,
Go outbound는 `sql.Open`과 `os.Getenv("UPPERCASE_KEY")`가 같은 line에 있어야
한다. Java writable/outbound도 각각 `Files.write` 또는
`DriverManager.getConnection`과 `System.getenv("UPPERCASE_KEY")`의 동시
출현을 요구한다. Python도 `requests.get`/`open(..., "w")`와 env read를 같은
line에서 요구한다.

이 조건은 명시적인 runtime behaviour를 실제 source에서 찾는다는 장점은
있지만, 설정 값을 먼저 변수·구성 객체로 바꿔 전달하는 일반적인 production
code를 fixture 후보에서 제외한다. 현재 catalog에는 그 결과를 우회하려고
문서·test·예제·합성 파일을 넣지 않는다.

기존 조사에서 확인한 대표적 제외 사례는
[후보 조사](oss-runtime-fixture-candidates-2026-07-27.md)에 보관되어 있다.
예를 들어 Node `webpack/webpack-sources` source는 benchmark이고, Python
`MeshInspector/MeshLib`은 재배포 가능한 license가 아니며, Java
`actionbronson/LazyMan`은 root license를 확인할 수 없다. 이들은 모두
positive fixture source가 될 수 없다.

## #46에 대한 결론

현 extractor v1과 “실제 GitHub OSS, permissive license, non-test/example/CI,
all five families”를 동시에 만족하는 fixture 집합은 이 catalog만으로
증명되지 않는다. 따라서 다음 둘 중 하나가 먼저 review되어야 한다.

1. extractor의 reviewed API boundary를 multi-line data flow까지 확장하고,
   새 경계에 맞는 source fragment를 다시 조사한다.
2. #46의 fixture contract를 현재 실제로 검증할 수 있는 family로 명시적으로
   좁힌다. 이 경우 누락 family를 fixture coverage로 주장하지 않는다.

그 전에는 이 문서의 verified fragment만을 근거로 fixture source를 복사할 수
있으며, Java 또는 Node/Go의 미확보 family를 채운 것처럼 테스트를
작성해서는 안 된다.
