# OSS 분석 성공 코퍼스 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Node.js·Python·Java·Go의 고정된 실제 OSS source 표본 8개에서 repository evidence 분석 성공과 알려진 runtime evidence 회귀를 검증한다.

**Architecture:** `tests/fixtures/oss_runtime/manifest.json`이 source fragment·고정 GitHub SHA·라이선스·원본 line range·기대 runtime kind의 단일 계약이 된다. `tests/test_oss_runtime_fixtures.py`는 각 fixture 디렉터리를 `repository_evidence.py --no-cache`로 별도 분석하고 validator 및 provenance/span 계약을 확인한다. 테스트는 source fixture만 읽고 네트워크·upstream 실행·의존성 설치를 하지 않는다.

**Tech Stack:** Python 3 standard library (`unittest`, `json`, `subprocess`), 기존 `scripts/repository_evidence.py`, `scripts/validate_repository_evidence.py`, 고정 GitHub source fragment.

## Global Constraints

- #46 단일 Vertical Slice는 source fixture, manifest, 회귀 테스트, 시나리오 문서를 함께 제공한다.
- 언어별 독립 OSS 표본은 정확히 2개씩, 총 8개다.
- source는 pinned commit의 production source fragment만 복사한다. 테스트·example·benchmark·CI·vendor·generated source와 전체 repository snapshot은 포함하지 않는다.
- manifest의 `expected_runtime_kinds`는 알려진 positive evidence의 부분집합이며, 빈 배열은 runtime signal 부재 주장이 아니라 분석 성공만 검증한다.
- 모든 scan은 `--no-cache`를 사용하고 fixture 실행·import·dependency install·network access를 하지 않는다.
- 모든 evidence source는 fixture 내부의 repository-relative path여야 하며, serialized output은 `redact_sensitive_text`를 거친 상태여야 한다.
- 각 commit subject/body에는 `refs #46`을 포함한다.

---

## 선택된 고정 source

| fixture id | 언어 | upstream revision | copied upstream path / lines | license | expected runtime kinds |
| --- | --- | --- | --- | --- | --- |
| `node-sql-pg` | node | `Sharaal/sql-pg@85733750e3acd90b1cd227f5de4838964a2bdf04` | `src/sql.query.js`, 1–15 | MIT | `runtime_config_read`, `runtime_outbound_connection` |
| `node-express` | node | `expressjs/express@ae6dd37680e3a00618d6c8a3e522f0ee4eeba1a4` | `lib/application.js`, 1–28 | MIT | `[]` |
| `python-vpc-lattice` | python | `aws-samples/build-secure-multi-account-vpc-connnectivity-applications-with-amazon-vpc-lattice@d8265321cb1a61395ba8ee39e066e1bcef28c33d` | `applications/apps-eks/backend.py`, 1–23 | MIT-0 | `runtime_config_read`, `runtime_listener`, `runtime_outbound_connection` |
| `python-click` | python | `pallets/click@00e592cea702e0b2caa0dee42489fdb1c22cd845` | `src/click/core.py`, 1–28 | BSD-3-Clause | `[]` |
| `java-gson` | java | `google/gson@aebc51a56ca0793c13b841c29f73433b82446695` | `gson/src/main/java/com/google/gson/Gson.java`, 1–28 | Apache-2.0 | `[]` |
| `java-commons-lang` | java | `apache/commons-lang@a316188a6d03b60528ed03e24b7266035007ebb4` | `src/main/java/org/apache/commons/lang3/Validate.java`, 1–28 | Apache-2.0 | `[]` |
| `go-plandex` | go | `plandex-ai/plandex@e2d772072efadbe41d2946d97d79be55532dbab5` | `app/cli/stream_tui/run.go`, 88–108 | MIT | `runtime_config_read`, `runtime_writable_path` |
| `go-cobra` | go | `spf13/cobra@adbc8813901bba65827259daa8e22ff94ec1f30e` | `command.go`, 1–28 | Apache-2.0 | `[]` |

### Task 1: 고정 OSS source와 provenance manifest를 하나의 검증 가능한 fixture 코퍼스로 추가

**Files:**
- Create: `tests/fixtures/oss_runtime/manifest.json`
- Create: `tests/fixtures/oss_runtime/node/sql-pg/src/sql.query.js`
- Create: `tests/fixtures/oss_runtime/node/express/lib/application.js`
- Create: `tests/fixtures/oss_runtime/python/vpc-lattice/backend.py`
- Create: `tests/fixtures/oss_runtime/python/click/core.py`
- Create: `tests/fixtures/oss_runtime/java/gson/Gson.java`
- Create: `tests/fixtures/oss_runtime/java/commons-lang/Validate.java`
- Create: `tests/fixtures/oss_runtime/go/plandex/run.go`
- Create: `tests/fixtures/oss_runtime/go/cobra/command.go`
- Create: `tests/test_oss_runtime_fixtures.py`

**Interfaces:**
- Consumes: manifest entry fields `id`, `language`, `fixture_path`, `source_path`, `upstream`, `commit`, `license`, `upstream_path`, `upstream_lines`, `retrieved_on`, `expected_runtime_kinds`.
- Produces: `load_manifest() -> list[dict[str, object]]`, which rejects malformed or duplicate entries before any scan.

- [ ] **Step 1: Write the failing manifest-contract test**

~~~python
def test_manifest_describes_exactly_two_fixtures_per_language(self):
    fixtures = self.load_manifest()
    self.assertEqual(len(fixtures), 8)
    self.assertEqual(
        Counter(item["language"] for item in fixtures),
        {"node": 2, "python": 2, "java": 2, "go": 2},
    )
    self.assertEqual(len({item["id"] for item in fixtures}), 8)
    for item in fixtures:
        self.assertRegex(item["commit"], r"^[0-9a-f]{40}$")
        self.assertTrue((FIXTURE_ROOT / item["fixture_path"] / item["source_path"]).is_file())
        self.assertTrue(item["upstream"].startswith("https://github.com/"))
        self.assertTrue(item["license"])
        self.assertEqual(len(item["upstream_lines"]), 2)
~~~

- [ ] **Step 2: Run test to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_oss_runtime_fixtures.OssRuntimeFixtureTests.test_manifest_describes_exactly_two_fixtures_per_language -v`

Expected: FAIL because the manifest and fixture sources do not exist.

- [ ] **Step 3: Add exact source fragments and manifest**

Copy only the table's listed source ranges without adapting identifiers or inserting synthetic runtime calls. Use one manifest object per fixture:

~~~json
{
  "id": "node-sql-pg",
  "language": "node",
  "fixture_path": "node/sql-pg",
  "source_path": "src/sql.query.js",
  "upstream": "https://github.com/Sharaal/sql-pg",
  "commit": "85733750e3acd90b1cd227f5de4838964a2bdf04",
  "license": "MIT",
  "upstream_path": "src/sql.query.js",
  "upstream_lines": [1, 15],
  "retrieved_on": "2026-07-27",
  "expected_runtime_kinds": [
    "runtime_config_read",
    "runtime_outbound_connection"
  ]
}
~~~

Apply the same schema to the other seven table entries. Use empty `expected_runtime_kinds` for Express, Click, Gson, Commons Lang, and Cobra; empty does not assert that runtime evidence is absent.

- [ ] **Step 4: Implement manifest loading and rerun GREEN**

~~~python
class OssRuntimeFixtureTests(unittest.TestCase):
    def load_manifest(self) -> list[dict[str, object]]:
        raw = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(raw), {"fixtures"})
        self.assertIsInstance(raw["fixtures"], list)
        return raw["fixtures"]
~~~

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_oss_runtime_fixtures.OssRuntimeFixtureTests.test_manifest_describes_exactly_two_fixtures_per_language -v`

Expected: PASS.

- [ ] **Step 5: Commit the provenance slice**

~~~bash
git add tests/fixtures/oss_runtime tests/test_oss_runtime_fixtures.py
git commit -m "test: add pinned OSS source fixture manifest" -m "refs #46"
~~~

### Task 2: 각 실제 OSS fixture의 분석 성공·schema·runtime 회귀를 end-to-end로 검증

**Files:**
- Modify: `tests/test_oss_runtime_fixtures.py`
- Modify: `tests/scenarios.md`

**Interfaces:**
- Consumes: `load_manifest()` and each fixture directory from Task 1.
- Produces: `run_collector(Path) -> dict[str, object]`, a no-cache scanner result verified by `validate_repository_evidence.validate_payload`.

- [ ] **Step 1: Write the failing end-to-end test**

~~~python
def test_each_real_oss_fixture_completes_with_valid_evidence(self):
    for fixture in self.load_manifest():
        with self.subTest(fixture=fixture["id"]):
            payload = self.run_collector(FIXTURE_ROOT / fixture["fixture_path"])
            self.assertEqual(validate_repository_evidence.validate_payload(payload), [])
            languages = {record["language"] for record in payload["snapshot"]["files"]}
            self.assertIn(fixture["language"], languages)
            runtime = [record for record in payload["evidence"] if record["provenance"] == "EXTRACTED"]
            self.assertTrue(all(record["source"]["path"] == fixture["source_path"] for record in runtime))
            self.assertTrue(all(".." not in record["source"]["path"].split("/") for record in runtime))
            self.assertTrue(all(kind in {record["kind"] for record in runtime} for kind in fixture["expected_runtime_kinds"]))
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            self.assertEqual(serialized, repository_evidence.redact_sensitive_text(serialized))
~~~

`run_collector` invokes `["python3", str(SCRIPT), str(repository), "--no-cache"]`, requires return code zero, and parses only stdout as JSON. It never imports or executes fixture source.

- [ ] **Step 2: Run test to verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_oss_runtime_fixtures.OssRuntimeFixtureTests.test_each_real_oss_fixture_completes_with_valid_evidence -v`

Expected: FAIL until scanner/validator helpers and fixture paths are complete.

- [ ] **Step 3: Add the smallest scanner helper and contract assertions**

~~~python
def run_collector(self, repository: Path) -> dict[str, object]:
    result = subprocess.run(
        ["python3", str(SCRIPT), str(repository), "--no-cache"],
        capture_output=True,
        text=True,
        check=False,
    )
    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
    return json.loads(result.stdout)
~~~

Keep assertions to manifest-declared positive kinds. Do not add an extractor rule, live GitHub request, cache assertion, repository clone, or five-family requirement.

- [ ] **Step 4: Document boundary and verify GREEN**

Add a `tests/scenarios.md` scenario: the eight pinned fragments verify analysis completion, schema/span/redaction contracts, and declared runtime kinds only; five-family completeness belongs to extractor unit tests.

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_oss_runtime_fixtures tests.test_repository_evidence -v`

Expected: PASS with all eight subtests completing without network access.

- [ ] **Step 5: Run full suite and commit the end-to-end slice**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`

Expected: PASS.

~~~bash
git add tests/test_oss_runtime_fixtures.py tests/scenarios.md
git commit -m "test: verify analysis on pinned OSS source corpus" -m "refs #46"
~~~

## Plan self-review

- **명세 범위:** 8개 표본, 고정 SHA, provenance, no-cache 성공, schema, language, span, redaction, declared positive evidence, metadata 비실행을 Task 1–2에 매핑했다.
- **Vertical Slice:** #46 하나가 fixture source부터 end-to-end scanner assertion과 문서까지 제공하며, 추출기 확장이나 live GitHub 실행을 섞지 않는다.
- **빈칸 검사:** 미정 항목·대체 표기·placeholder·미선정 후보가 없고 8개 source의 commit·경로·line range·license·expected kind를 확정했다.
- **계약 일관성:** manifest의 `fixture_path`와 `source_path`를 Task 1 test 및 Task 2 scanner assertion이 같은 의미로 사용한다.
