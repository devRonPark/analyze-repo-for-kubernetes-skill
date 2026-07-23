# Kubernetes Migration Assessment

## 1. Assessment Scope

- Source type:
- Repository URL or local path:
- Access method:
- Resolved repository root:
- Branch or commit:
- Analyzed path:

## 2. Executive Summary

Summarize architecture, migration posture, and the most important unresolved decisions.

## 3. Component Inventory

| Component | Path | Type | Deployable | Containerization | Evidence |
|---|---|---|---|---|---|

## 4. Component Details

For each deployable component include purpose, language and runtime, build command, production startup command, listener or no listener, health behavior, storage, configuration with Application Phase, dependencies with Execution Locus, and evidence.

## 5. Repository Dependency Matrix

| Source | Target | Type | Protocol | Phase | Execution Locus | Required | Evidence |
|---|---|---|---|---|---|---|---|

## 6. Repository Dependency Graph

```text
source --[relationship; Execution Locus]--> target
```

## 7. Configuration and State

Document configuration timing, secret names without values, writable paths, and persistence requirements.

## 8. Kubernetes Migration Risks

List migration-specific risks and conflicting evidence.

## 9. Required Inputs

List missing information and user decisions needed for the next design step.

## 10. Final Readiness Verdict

- Verdict: Ready | Needs Input | Blocked
- Rationale:
