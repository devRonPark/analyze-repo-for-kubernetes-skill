# OSS Runtime Fixture Evaluation Design

## Goal

Validate each Node.js, Python, Java, and Go runtime-signal extractor against a
real public GitHub repository while keeping repository tests deterministic,
small, and independent of network access.

## Fixture model

Each language receives one selected public OSS repository and a minimal fixture
containing only source files needed to demonstrate all five runtime signal
families: configuration read, listener, outbound connection, writable path,
and background registration. Tests run only the copied fixture; they never
clone, fetch, execute, import, or install the upstream repository.

## Provenance manifest

Every fixture has a machine-readable manifest recording the upstream GitHub
URL, immutable commit SHA, license, copied upstream paths, and source retrieval
date. The test asserts that the manifest and fixture source are present before
scanning. Upstream contents are reviewed manually at the pinned commit before
being copied.

## Candidate selection

Select one repository per language only when its license permits the stored
source fixture, the pinned revision exposes all five signal families through
the reviewed static APIs, and the selected source paths are small enough to
understand independently. Prefer first-party source files over generated,
test, example, vendored, or dependency code.

## Test contract

For each fixture, scan with `--no-cache` and assert all five runtime evidence
kinds are present with `provenance: EXTRACTED`, the expected language, valid
repository-relative source spans, and no runtime evidence from the fixture
manifest or non-source metadata. A separate manifest-validation test prevents
silently changing the pinned upstream revision or copying untracked source.

## Maintenance boundary

Changing an upstream fixture requires updating its pin, source manifest, and
expected evidence in one reviewable commit. Upstream changes are never fetched
during CI; refreshing a fixture is an explicit, reviewed maintenance action.
