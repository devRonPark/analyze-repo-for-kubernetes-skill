# OSS Runtime Fixture Evaluation Design

## Goal

Validate each Node.js, Python, Java, and Go runtime-signal extractor against a
real public GitHub repository while keeping repository tests deterministic,
small, and independent of network access.

## Fixture model

Each language receives a set of selected public OSS source fragments and a
minimal fixture containing only files needed to demonstrate all five runtime
signal families: configuration read, listener, outbound connection, writable
path, and background registration. A fragment may come from a different
repository when the current extractor's reviewed API boundary makes a single
repository criterion unrepresentative. Tests run only the copied fixture; they
never clone, fetch, execute, import, or install the upstream repository.

## Provenance manifest

Every fixture has a machine-readable manifest recording, for every source
fragment, the upstream GitHub URL, immutable commit SHA, license, copied
upstream path, signal family, and source retrieval date. The test asserts that
the manifest and fixture source are present before scanning. Upstream contents
are reviewed manually at the pinned commit before being copied.

## Candidate selection

Select a source fragment only when its license permits the stored fixture, the
pinned revision exposes its assigned signal family through the reviewed static
API, and the selected path is small enough to understand independently. Prefer
first-party source files over generated, test, example, vendored, dependency,
CI, or build code. Each language's fragment set must collectively cover all
five signal families.

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
