# Repository Navigation Corpus

This directory stores reviewed observations and candidate navigation rules for repository analysis under constrained LLM context.

## Layout

- `manifest.json`: 40-repository research sample, 10 each for Node.js, Java, Python and Go
- `schema/observation.schema.json`: observation record contract
- `observations/<language>/`: pinned, repository-specific navigation traces
- `rules/<language>/`: candidate rules derived from reviewed observations

## Validation

```bash
python3 scripts/validate_navigation_corpus.py
```

```bash
python3 -m unittest tests.test_navigation_corpus -v
```

A repository entry moves from `unpinned` to `pinned` only after it has a 40-character commit SHA and a checked-in observation file. Candidate rules must identify their source observations and remain candidates until supported by multiple repositories or explicitly documented as framework-specific.

## Research principle

The corpus does not treat scanner output as the final Kubernetes design. Scanner and navigation rules reduce the search space, while the LLM verifies runtime meaning from targeted source ranges and records unknown or conflicting fields instead of guessing.
