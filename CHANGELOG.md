# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Changed

- Added an explicit read-only analyst role and repository prompt-injection boundary.
- Simplified missing-target intake to one concrete Repository URL or Local path question.
- Separated repository facts from inferred Kubernetes design candidates.
- Added structured absence evidence with `검색(scope=..., pattern=..., result=없음)`.
- Differentiated summary relationship output from detailed matrix and graph output.
- Updated report validation and tests for the revised evidence and output contracts.

## 0.1.0 - 2026-07-23

### Added

- Interview-first target selection for Repository URL and Local path.
- Target Resolution Gate that prevents the skill package from becoming the analysis target.
- Summary and detailed report modes.
- Execution Locus and Application Phase classifications.
- Dockerfile-independent repository discovery rules.
- Package and report validators.
- Qwen Code installation and update scripts.
- GitHub Actions test workflow.
