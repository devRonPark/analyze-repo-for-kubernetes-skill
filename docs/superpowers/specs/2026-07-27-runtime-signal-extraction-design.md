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

## Extractor architecture

`RuntimeSignalExtractor` is a small interface with language, name, version,
and a single file-extraction operation. A registry maps the inventory language
of each included source file to its reviewed extractor. A shared dispatcher:

1. skips files classified as test-only and lines that are comments;
2. invokes at most the extractor registered for the file language;
3. converts only reviewed source constructs to typed evidence;
4. catches failures per file and appends a structured runtime extraction
   diagnostic without interrupting universal evidence collection.

The first implementations are intentionally conservative line-oriented static
recognizers. They only match explicit calls or expressions for their language
and do not substitute defaults when a host, port, endpoint, or path is absent.
No third-party parser is introduced.

## Cache integration

The #35 per-file cache remains the cache owner. Its compatibility identity
includes the source language and the selected runtime extractor name/version
(or an explicit no-runtime-extractor marker). Therefore a change to one
language extractor invalidates the relevant file entries while preserving cache
reuse for unrelated files. Cache restoration accepts valid evidence from both
the universal and runtime extractors. A clean scan and a warm cached scan must
produce identical JSON evidence.

## Failure behavior

Unsupported source forms are ignored. An extractor exception or syntax error
it explicitly reports produces a deterministic diagnostic with the file path,
language, extractor name/version, and redacted reason. Other files, universal
pattern evidence, and the final evidence payload remain available. Diagnostics
are metadata rather than readiness or deployability decisions.

## Verification

Focused fixtures cover all four languages and all five signal families, with
source-span and provenance assertions. Negative fixtures prove that comments,
README text, test files, dependency declarations, and framework default ports
do not produce extracted runtime evidence. Tests also cover secret redaction,
per-file failure isolation, extractor-version cache invalidation, and exact
cached-versus-clean output equivalence. The existing evidence validator and
full unit suite remain green.
