# Runtime Signal Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide v2, source-span-addressable runtime evidence for the reviewed Node.js, Python, Java, and Go source constructs without executing source or turning defaults and prose into facts.

**Architecture:** Keep `scripts/repository_evidence.py` as the scanner, evidence serializer, cache owner, and CLI boundary. Add `scripts/runtime_signal_extractors.py` as the language-pluggable, pure-static extraction module; it returns typed signal candidates and per-file diagnostics, while the scanner converts candidates into v2 evidence records and caches complete file outcomes.

**Tech Stack:** Python 3 standard library, `unittest`, existing repository inventory, existing per-file JSON cache.

## Global Constraints

- Output new scans as `repository-evidence/v2`; validator accepts v1 with its historical identity rules.
- Every v2 evidence record has top-level `provenance`: runtime extractor facts use `EXTRACTED`; pre-existing scanner and pattern-pack facts use `INFERRED`.
- Keep `status` separate from provenance; directly recognized runtime constructs use `confirmed` only for source existence, never a deployability or readiness conclusion.
- Runtime evidence kinds are exactly `runtime_config_read`, `runtime_listener`, `runtime_outbound_connection`, `runtime_writable_path`, and `runtime_background_registration`.
- Support only included source files and the current inventory language contract: Node `.js`, `.jsx`, `.ts`, `.tsx`; Python `.py`; Java `.java`; Go `.go`.
- Never execute, import, install dependencies for, or otherwise run the target repository.
- Do not derive a runtime fact from a comment, docstring, string literal, README, dependency declaration, test-only source, or framework default.
- Redact secret values before evidence or cache persistence; retain only safe endpoint structure and configuration-key names.
- A failed extractor produces a sorted `diagnostics.runtime_extraction` item with path, language, extractor name/version, stable code, and redacted length-limited message; it does not abort other files.
- `scan_repository(..., runtime_signals_enabled=False)` and CLI `--no-runtime-signals` disable only runtime extraction and preserve deterministic universal evidence.
- File-cache compatibility includes runtime-extraction enabled state and the selected language extractor name/version; clean and warm-cache output must be byte-for-byte equivalent.
- Every implementation commit references `#36`.

## File Responsibilities

- `scripts/runtime_signal_extractors.py`: pure language registry, lexical boundary handling, reviewed static extractors, signal/diagnostic result models, and cache descriptors.
- `scripts/repository_evidence.py`: v2 `EvidenceRecord`, record identity/serialization, file outcome cache, conversion of runtime candidates into evidence, output diagnostics, and CLI toggle.
- `scripts/validate_repository_evidence.py`: v1 compatibility path and strict v2 provenance/diagnostic validation.
- `tests/test_repository_evidence.py`: scanner, validator, cache, CLI, and backwards-compatibility integration tests.
- `tests/test_runtime_signal_extractors.py`: four-language five-signal matrix and lexical/test-source negative unit tests.

---

### Task 1: v2 Evidence Contract Vertical Slice

**Files:**

- Modify: `scripts/repository_evidence.py:20-430, 582-650, 1078-1165`
- Modify: `scripts/validate_repository_evidence.py:1-274`
- Modify: `tests/test_repository_evidence.py:68-170`

**Interfaces:**

- Consumes: existing `EvidenceRecord`, `stable_evidence_id`, cache entry JSON, and v1 validator artifacts.
- Produces: `EvidenceRecord.provenance: str`, `build_evidence_record(..., provenance: str = "INFERRED")`, and v2 payload validation while preserving explicit v1 validation.

- [ ] **Step 1: Write failing v2 contract tests**

Add tests that assert a scanner payload has `schema_version == "repository-evidence/v2"`, every record has `provenance == "INFERRED"`, each v2 ID includes provenance in its canonical identity, and a v1 payload generated with its old ID still validates. Add malformed v2 cases that omit provenance or use `EXTRACTED` on an unsupported kind and assert the validator returns `invalid_provenance`.

```python
self.assertEqual(payload["schema_version"], "repository-evidence/v2")
self.assertEqual({item["provenance"] for item in payload["evidence"]}, {"INFERRED"})
self.assert_validator_rejects(missing_provenance, "invalid_provenance")
self.assertEqual(v1_validation.returncode, 0, v1_validation.stdout)
```

- [ ] **Step 2: Run the contract tests to prove the current v1 implementation fails**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_repository_evidence.RepositoryEvidenceTests.test_collector_emits_stable_schema_identity_source_and_provenance -v`

Expected: FAIL because the payload is v1 and records do not contain `provenance`.

- [ ] **Step 3: Implement the v2 record and validator boundary**

Set `EVIDENCE_SCHEMA_VERSION = "repository-evidence/v2"`. Add the top-level `provenance` field to `EvidenceRecord`; pass it through `build_evidence_record`, serialization, cache restoration, sort/identity calculation, and record validation. Define `ALLOWED_PROVENANCE = {"EXTRACTED", "INFERRED"}`. Keep existing collectors on their default `INFERRED` provenance. Add an explicit v1 normalization/validation branch that verifies v1 IDs using the former canonical input before treating its effective provenance as `INFERRED`; do not rewrite a v1 record ID using the v2 identity rule.

```python
def stable_evidence_id(kind, status, data, source=None, absence=None, provenance="INFERRED"):
    identity = {"absence": absence, "data": data, "kind": kind,
                "provenance": provenance, "source": source}
    return f"ev_{hashlib.sha256(canonical_json(identity).encode()).hexdigest()[:20]}"
```

- [ ] **Step 4: Run focused v2 and legacy validation tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_repository_evidence.RepositoryEvidenceTests.test_collector_emits_stable_schema_identity_source_and_provenance tests.test_repository_evidence.RepositoryEvidenceTests.test_validator_accepts_current_legacy_evidence_shape tests.test_repository_evidence.RepositoryEvidenceTests.test_validator_rejects_malformed_repository_evidence -v`

Expected: PASS. A v2 scanner artifact validates; legacy schema `1` and prior v1 compatibility fixtures validate only through their historical identity rules.

- [ ] **Step 5: Commit the v2 contract slice**

```bash
git add scripts/repository_evidence.py scripts/validate_repository_evidence.py tests/test_repository_evidence.py
git commit -m "feat: add v2 evidence provenance contract" -m "refs #36"
```

### Task 2: Node.js Runtime Signal Vertical Slice

**Files:**

- Create: `scripts/runtime_signal_extractors.py`
- Modify: `scripts/repository_evidence.py:228-430, 991-1165`
- Modify: `scripts/validate_repository_evidence.py:190-252`
- Create: `tests/test_runtime_signal_extractors.py`
- Modify: `tests/test_repository_evidence.py:20-67, 242-410`

**Interfaces:**

- Consumes: v2 `build_evidence_record`, included `FileRecord.language`, secret-redaction helper, and per-file cache API from Task 1.
- Produces: `RuntimeSignalExtractor`, `RuntimeSignal`, `RuntimeExtractionDiagnostic`, `RuntimeExtractionOutcome`, `runtime_extractor_for(language)`, and Node extraction integrated with scanner output.

- [ ] **Step 1: Write failing Node positive, negative, and cache tests**

Create a Node fixture with explicit `process.env` reads, `server.listen(process.env.PORT || 3100, "0.0.0.0")`, a supported outbound client using `DATABASE_URL`, `fs.writeFile(process.env.DATA_PATH, value)`, and a reviewed scheduler/worker registration. Assert all five runtime kinds are `EXTRACTED`, `confirmed`, `node`, span-addressable, and use the Node extractor descriptor. Add comments, string literals, README prose, `tests/server.test.js`, a package dependency, and `app.listen()` without a literal port; assert none create runtime evidence. Add clean/warm cache and `--no-runtime-signals` integration assertions.

```python
self.assertEqual(runtime_kinds, {
    "runtime_config_read", "runtime_listener", "runtime_outbound_connection",
    "runtime_writable_path", "runtime_background_registration",
})
self.assertFalse(any(item["source"]["path"].startswith("tests/") for item in runtime_items))
self.assertEqual(warm.stdout, clean.stdout)
```

- [ ] **Step 2: Run Node tests to prove the runtime-extractor module and toggle are absent**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runtime_signal_extractors.NodeRuntimeSignalExtractorTests tests.test_repository_evidence.RepositoryEvidenceTests.test_runtime_signals_can_be_disabled_independently -v`

Expected: FAIL because the module, runtime kinds, and CLI option do not exist.

- [ ] **Step 3: Implement the pluggable extractor and Node end-to-end path**

Create a pure `runtime_signal_extractors.py` registry with one extractor object per language, initially fully implementing Node and returning empty outcomes for the other registered languages. Define a lexer that ignores line/block comments and string-literal-only API text while retaining literals used as supported call arguments. Define `RuntimeExtractionOutcome(signals, diagnostics)` and stable descriptors `{language, name, version}`. In the scanner, convert Node candidates to the five v2 kinds with `provenance="EXTRACTED"`; preserve separate config and listener/writable/outbound records from the same span. Refactor cache entries from `list[EvidenceRecord]` to a complete file outcome that stores/restores records and runtime diagnostics. Include `runtime_signals_enabled` and the Node descriptor in cache identity. Emit a sorted `diagnostics.runtime_extraction` array and add `--no-runtime-signals`.

```python
@dataclass(frozen=True)
class RuntimeSignal:
    kind: str
    line: int
    data: dict[str, Any]

class RuntimeSignalExtractor(Protocol):
    language: str
    name: str
    version: str
    def extract(self, path: str, lines: list[str]) -> RuntimeExtractionOutcome: ...
```

- [ ] **Step 4: Run Node slice tests and evidence validation**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runtime_signal_extractors.NodeRuntimeSignalExtractorTests tests.test_repository_evidence.RepositoryEvidenceTests.test_runtime_signals_can_be_disabled_independently tests.test_repository_evidence.RepositoryEvidenceTests.test_per_file_cache_reuses_unchanged_evidence_and_matches_a_clean_run -v`

Expected: PASS. Universal evidence remains when runtime extraction is disabled; Node runtime evidence, diagnostics, and cache outcomes are deterministic.

- [ ] **Step 5: Commit the Node vertical slice**

```bash
git add scripts/runtime_signal_extractors.py scripts/repository_evidence.py scripts/validate_repository_evidence.py tests/test_runtime_signal_extractors.py tests/test_repository_evidence.py
git commit -m "feat: extract node runtime signals" -m "refs #36"
```

### Task 3: Python Runtime Signal Vertical Slice

**Files:**

- Modify: `scripts/runtime_signal_extractors.py`
- Modify: `tests/test_runtime_signal_extractors.py`
- Modify: `tests/test_repository_evidence.py`

**Interfaces:**

- Consumes: Node-complete registry, `RuntimeSignalExtractor.extract`, v2 scanner conversion, and cache outcome API from Task 2.
- Produces: `PythonRuntimeSignalExtractor` with five reviewed Python signal families and language-specific cache descriptor.

- [ ] **Step 1: Write failing Python matrix and test-boundary cases**

Add a `.py` fixture with `os.getenv`/`os.environ`, an explicit `uvicorn.run` or `app.run` literal listener, supported database/HTTP configuration use, `open(..., "w")` or `Path.write_text`, and reviewed Celery/scheduler registration. Add `tests/test_worker.py`, a triple-quoted docstring mentioning `uvicorn.run(port=8000)`, dependency-only `pyproject.toml`, and a runner without a literal port. Assert all five positive kinds are `EXTRACTED` and all negative sources produce none.

```python
self.assertEqual({item["data"]["language"] for item in python_runtime_items}, {"python"})
self.assertNotIn("tests/test_worker.py", {item["source"]["path"] for item in python_runtime_items})
```

- [ ] **Step 2: Run Python matrix tests to demonstrate the registered extractor is still empty**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runtime_signal_extractors.PythonRuntimeSignalExtractorTests -v`

Expected: FAIL because no Python runtime signals are returned.

- [ ] **Step 3: Implement the reviewed Python extractor**

Recognize only direct `os.getenv`, `os.environ[...]`, supported explicit server runners, reviewed HTTP/database/broker calls, writable `open` modes and `pathlib` writers, and reviewed task/scheduler decorators or registrations. Use lexical handling for `#` comments and triple-quoted docstrings. Emit only literal host/ports, safe literal paths, safe endpoint structure, and configuration-key references. Do not import source, call Python AST execution, or infer FastAPI/Flask defaults.

- [ ] **Step 4: Run Python plus shared scanner/cache tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runtime_signal_extractors.PythonRuntimeSignalExtractorTests tests.test_repository_evidence.RepositoryEvidenceTests.test_runtime_signal_cache_version_invalidates_only_matching_language -v`

Expected: PASS. Python records are span-valid, test/docstring content is excluded, and a Python extractor version change does not invalidate Node cache entries.

- [ ] **Step 5: Commit the Python vertical slice**

```bash
git add scripts/runtime_signal_extractors.py tests/test_runtime_signal_extractors.py tests/test_repository_evidence.py
git commit -m "feat: extract python runtime signals" -m "refs #36"
```

### Task 4: Java Runtime Signal Vertical Slice

**Files:**

- Modify: `scripts/runtime_signal_extractors.py`
- Modify: `tests/test_runtime_signal_extractors.py`
- Modify: `tests/test_repository_evidence.py`

**Interfaces:**

- Consumes: shared signal models, v2 conversion, and language-descriptor cache identity from Tasks 1-3.
- Produces: `JavaRuntimeSignalExtractor` with five reviewed Java signal families.

- [ ] **Step 1: Write failing Java matrix and framework-default regressions**

Add a `.java` fixture containing `System.getenv`, an explicit `ServerSocket` or `HttpServer` listener with a literal port and host, a reviewed JDBC/HTTP/broker setup, `Files.write` or output-stream write with a literal/config path, and `@Scheduled` or executor registration. Include a Spring dependency declaration, `SpringApplication.run`, comments/string literals mentioning ports, `src/test/java/AppTest.java`, and no explicit server port. Assert only explicit reviewed constructs generate the five runtime kinds.

```python
self.assertFalse(any(item["data"].get("port") == 8080 for item in spring_default_items))
self.assertTrue(all(item["provenance"] == "EXTRACTED" for item in java_runtime_items))
```

- [ ] **Step 2: Run Java tests to demonstrate no Java extractor implementation exists**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runtime_signal_extractors.JavaRuntimeSignalExtractorTests -v`

Expected: FAIL because no Java runtime signals are returned.

- [ ] **Step 3: Implement the reviewed Java extractor**

Recognize only direct `System.getenv`/`System.getProperty`, explicit server constructors/builders, reviewed connection construction, `Files`/stream writes, and `@Scheduled` or reviewed executor submission. Exclude package dependencies, Spring default behavior, tests, comments, and string-literal text. Preserve only safe endpoint pieces and configuration-key names.

- [ ] **Step 4: Run Java slice and validator tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runtime_signal_extractors.JavaRuntimeSignalExtractorTests tests.test_repository_evidence.RepositoryEvidenceTests.test_collector_emits_stable_schema_identity_source_and_provenance -v`

Expected: PASS. Java fixture output has valid v2 IDs, source spans, provenance, and no framework-default listener evidence.

- [ ] **Step 5: Commit the Java vertical slice**

```bash
git add scripts/runtime_signal_extractors.py tests/test_runtime_signal_extractors.py tests/test_repository_evidence.py
git commit -m "feat: extract java runtime signals" -m "refs #36"
```

### Task 5: Go Runtime Signal Vertical Slice and Completion Verification

**Files:**

- Modify: `scripts/runtime_signal_extractors.py`
- Modify: `tests/test_runtime_signal_extractors.py`
- Modify: `tests/test_repository_evidence.py`
- Modify: `README.md`
- Modify: `references/evidence-and-readiness.md`

**Interfaces:**

- Consumes: v2 evidence/validator, file outcome cache, language registry, and the Node/Python/Java slice tests.
- Produces: `GoRuntimeSignalExtractor`, all-four-language matrix proof, failure-isolation contract, and user-facing evidence contract documentation.

- [ ] **Step 1: Write failing Go matrix, failure-isolation, and all-language cache tests**

Add a `.go` fixture with `os.Getenv`, explicit `http.ListenAndServe` or `net.Listen`, reviewed `sql.Open`/HTTP/broker construction, `os.WriteFile`/`os.OpenFile`, and reviewed cron/worker registration. Add `_test.go`, comments/string literals, `go.mod` dependency text, and a listener without an explicit literal port. Inject a registered extractor that raises a secret-like exception and assert its file produces one sorted redacted diagnostic while other languages still emit evidence. Populate a four-language cache, change only Go extractor version, and assert only Go misses/invalidates while Node/Python/Java are hits and cached output equals a no-cache scan.

```python
self.assertEqual(diagnostic["code"], "extractor_failure")
self.assertIn("[REDACTED]", diagnostic["message"])
self.assertEqual(cache_diagnostics["hit"], 3)
self.assertEqual(cache_diagnostics["invalidated"], 1)
```

- [ ] **Step 2: Run Go and completion tests to demonstrate the final language and failure contract are missing**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runtime_signal_extractors.GoRuntimeSignalExtractorTests tests.test_repository_evidence.RepositoryEvidenceTests.test_runtime_extractor_failure_isolated_and_cached tests.test_repository_evidence.RepositoryEvidenceTests.test_runtime_signal_cache_version_invalidates_only_matching_language -v`

Expected: FAIL because Go signals and the explicit extractor-failure diagnostic cache outcome are not implemented.

- [ ] **Step 3: Implement the reviewed Go extractor and final contract hardening**

Recognize direct `os.Getenv`/`os.LookupEnv`, explicit `net.Listen`/`http.ListenAndServe` literals, reviewed SQL/HTTP/broker construction, `os.WriteFile`/write-mode file handles, and reviewed cron/worker registration. Exclude bare `go func()` and all test/comment/string/dependency evidence. Catch any extractor exception at the scanner boundary, redact and limit its message, sort diagnostics, and cache the complete outcome. Update README and evidence reference to state v2 provenance, runtime-signal scope, independent disablement, and diagnostics behavior.

- [ ] **Step 4: Run focused acceptance and complete suite**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runtime_signal_extractors tests.test_repository_evidence -v`

Expected: PASS for the complete four-by-five matrix, all negative boundaries, v1 compatibility, failure isolation, disabled runtime extraction, selective per-language invalidation, and warm/clean equivalence.

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`

Expected: PASS for the full repository suite.

- [ ] **Step 5: Commit the Go and completion slice**

```bash
git add scripts/runtime_signal_extractors.py scripts/repository_evidence.py scripts/validate_repository_evidence.py tests/test_runtime_signal_extractors.py tests/test_repository_evidence.py README.md references/evidence-and-readiness.md
git commit -m "feat: complete runtime signal extraction" -m "refs #36"
```
