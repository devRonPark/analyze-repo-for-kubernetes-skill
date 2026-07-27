# OSS Runtime Fixture Evaluation Design

## Goal

Validate that repository analysis finishes safely and deterministically for a
small, representative corpus of real public OSS source, rather than requiring
every individual repository to exhibit every runtime-signal family.

## Corpus model

The corpus contains two fixed, independently selected OSS source fixtures for
each of Node.js, Python, Java, and Go: eight fixtures in total. A fixture is a
minimal copy of the selected upstream production source required for analysis;
it is not a full repository snapshot. Tests run only these copies and never
clone, fetch, execute, import, or install the upstream repository.

Fixtures are selected using pinned GitHub commits, permissive licenses,
production-source paths where available, and language/framework diversity.
Generated, vendored, dependency-cache, test, example, benchmark, CI, and build
paths are excluded from positive fixture selection. A fixture may have no
runtime evidence when its copied source does not use a reviewed API; such a
fixture still verifies analysis completion and output validity.

## Provenance manifest

Every fixture has a machine-readable manifest entry recording its stable name,
language, upstream repository URL, immutable commit SHA, license, copied
upstream path, source retrieval date, and one reviewed expectation: either a
named runtime evidence kind expected from the copied source or `none`.

The tests validate that the manifest contains exactly the eight stored fixture
sources, each source is present and repository-relative, and no manifest or
README metadata becomes runtime evidence. Upstream contents are reviewed at the
pinned commit before copying. The manifest does not record source secrets or
unnecessary upstream content.

## Analysis-success contract

For every fixture, invoke the repository evidence scanner with `--no-cache`.
The scan must complete without an unhandled exception, emit a valid current
evidence schema, identify the fixture's language, and contain only
repository-relative source spans. Values classified as secret-like must remain
redacted in serialized output.

When the manifest declares an expected runtime kind, the scan must emit that
kind with `provenance: EXTRACTED`, the fixture language, and a span in the
declared copied source. The suite does not require all five runtime-signal
families from every repository; signal-family completeness remains covered by
the language extractor unit tests.

## Maintenance boundary

Changing an upstream fixture requires updating its source, manifest pin,
expectation, and regression assertion in one reviewable commit. Upstream changes
are never fetched during CI; refreshing a fixture is an explicit, reviewed
maintenance action. The fixture corpus is a deterministic sample, not a claim
that every arbitrary repository can be analyzed successfully.
