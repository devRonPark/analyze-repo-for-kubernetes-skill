# Runtime Signal Extraction Design

## Goal

Add a deliberately small, static runtime-signal extraction slice for Node.js,
Python, Java, and Go. It must supply Kubernetes-relevant evidence without
executing repository code, inferring framework defaults, or becoming a general
code-intelligence system.

## Scope and boundaries

The extractor recognizes only these runtime facts when an explicit supported
source construct is present:

- Environment or configuration reads.
- Server bind/listener host and port.
- Outbound client, database, broker, or DSN construction hints.
- Writable filesystem paths.
- Worker, scheduler, or background-process registration.

It does not build call graphs, resolve symbols, execute or import source code,
classify deployables, make readiness decisions, or emit framework-default
ports. Package dependencies, prose, comments, README files, and test-only
source cannot create a runtime signal.

## Evidence contract

Runtime findings use dedicated evidence kinds for the five supported signal
families. Each finding includes:

- A valid repository-relative structured source span and matching human
  citation.
- `language`, extractor `name`, and semantic `version`.
- An explicit `provenance` value. Runtime extractor output is `EXTRACTED`;
  existing deterministic pattern-pack facts are `INFERRED`.
- Existing analysis `status`, which remains separate from provenance.

The evidence identity includes provenance so an extracted and an inferred item
cannot collapse into one record. Sensitive inline values are redacted before a
record or cache entry is persisted.

These required additions advance scanner output to `repository-evidence/v2`.
The validator continues to read and validate v1 artifacts with their historical
identity rules and treats their provenance as legacy-compatible `INFERRED` for
validation purposes; the new scanner emits v2 only.

The five signal families are five explicit evidence kinds rather than one
generic kind with a discriminator in `data`. This preserves a stable contract
for validation and downstream triage.

The kinds are `runtime_config_read`, `runtime_listener`,
`runtime_outbound_connection`, `runtime_writable_path`, and
`runtime_background_registration`. A directly recognized source construct uses
`status: confirmed` and `provenance: EXTRACTED`; this says only that the
construct exists at the cited span, not that it is deployable or ready.

For a listener such as `app.listen(process.env.PORT || 3000)`, extraction emits
the `PORT` configuration-read evidence and a distinct listener evidence for the
explicit literal fallback `3000`. It does not claim the whole expression is one
resolved port. Outbound DSN or URL extraction retains only safe structure
(scheme, safe host/port, and referenced configuration keys); credentials and
query values are never persisted as evidence text or data.

## Extractor architecture

`RuntimeSignalExtractor` is a small interface with language, name, version,
and a single file-extraction operation. A registry maps the inventory language
of each included source file to its reviewed extractor. A shared dispatcher:

1. skips files classified as test-only and lines that are comments; test-only
   includes `test`, `tests`, and `__tests__` directories plus language-conventional
   file names such as `*_test.go`, `test_*.py`, `*_test.py`, `*.test.*`,
   `*.spec.*`, and `*Test.java`;
2. invokes at most the extractor registered for the file language;
3. converts only reviewed source constructs to typed evidence;
4. catches failures per file and appends a structured runtime extraction
   diagnostic without interrupting universal evidence collection.

Node.js, Python, Java, and Go each register an independent extractor name and
version. Node.js input is limited to the extensions the existing inventory
classifies as `node`: `.js`, `.jsx`, `.ts`, and `.tsx`; module-extension support
outside that inventory contract is not part of this slice.

The first implementations are intentionally conservative line-oriented static
recognizers. They only match explicit calls or expressions for their language
and do not substitute defaults when a host, port, endpoint, or path is absent.
No third-party parser is introduced. Source syntax outside the reviewed subset
is ignored. A registered extractor that cannot process a supported fragment or
raises an exception emits a per-file diagnostic.

Recognition is limited to code tokens, not text inside line comments, block
comments, docstrings, or string literals. Listener records contain only an
explicit numeric literal port and a safe literal host. A dynamic host or port
expression is not a resolved listener value; when it reads a configuration key,
that key is represented by separate config-read evidence.

A writable operation targeting a configuration expression emits both the
config-read and writable-path kinds, with `path_config_key` rather than an
invented path value. Safe absolute and relative literal filesystem paths are
both retained; URL- or credential-shaped values are excluded and every retained
value passes the existing secret-redaction boundary.

The reviewed subset is limited to common runtime APIs: Node.js `process.env`,
listener calls, selected `fs` writes, and timer/worker registration; Python
`os.getenv`/`os.environ`, explicit server runners, writable `open` or path
writes, and scheduler/worker registration; Java `System.getenv`, explicit
server constructors, `Files`/stream writes, and `@Scheduled` or executor
registration; and Go `os.Getenv`, explicit `net`/`http` listeners, `os` writes,
and reviewed scheduler or worker registration. Generic method names such as
`connect`, `write`, or `start` are not evidence by themselves.

One source span can emit more than one kind when it directly supports distinct
facts: `db.connect(process.env.DATABASE_URL)` produces both a config-read and
an outbound-connection record. Background registration remains narrower than
general asynchronous execution: bare Go goroutines and generic async calls are
not evidence; only reviewed scheduler, worker-queue, or executor registration
APIs are.

## Cache integration

The #35 per-file cache remains the cache owner. Each cache outcome contains
both evidence records and any runtime extraction diagnostics. Its compatibility identity
includes the source language and the selected runtime extractor name/version
(or an explicit no-runtime-extractor marker), plus whether runtime extraction
is enabled. Therefore a change to one
language extractor invalidates the relevant file entries while preserving cache
reuse for unrelated files. Cache restoration accepts valid evidence from both
the universal and runtime extractors and restores diagnostics. A clean scan and
a warm cached scan must produce identical JSON evidence and diagnostics.

## Failure behavior

Unsupported source forms are ignored. An extractor exception or syntax error
it explicitly reports produces a deterministic diagnostic with the file path,
language, extractor name/version, and redacted reason. Other files, universal
pattern evidence, and the final evidence payload remain available. Diagnostics
are metadata rather than readiness or deployability decisions, rendered in the
top-level `diagnostics.runtime_extraction` array. Runtime extraction is enabled
by default and can be disabled independently with an API parameter and the CLI
`--no-runtime-signals` option; universal evidence collection continues.

Each diagnostic has a stable machine-readable `code` and a redacted,
length-limited human-readable `message`. Diagnostics sort by repository-relative
path, language, extractor name/version, then code so filesystem traversal and
cache state cannot change payload order.

## Verification

Focused fixtures cover all four languages and all five signal families, with
an explicit four-by-five matrix of source-span and provenance assertions.
Negative fixtures prove that comments,
README text, test files, dependency declarations, and framework default ports
do not produce extracted runtime evidence. Tests also cover secret redaction,
per-file failure isolation, independent disablement, and exact cached-versus-
clean output equivalence. An extractor version change must invalidate only that
language's file entries, retain cache hits for unrelated languages, and still
match a clean run. The existing evidence validator and full unit suite remain
green.
