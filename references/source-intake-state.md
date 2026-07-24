# Source Intake State

Apply this state machine before repository analysis. It preserves the existing Interview-first AskUserQuestion flow: a missing Target produces one question and ends the turn.

```text
start -> target_required | target_resolved
target_required -> target_resolved
target_resolved -> purpose_required | analysis_ready
purpose_required -> analysis_ready
```

## Target Resolution

At `start`, resolve exactly one Target in this order:

1. Git URL, Local path or Source archive supplied as Slash Command Input.
2. GitHub URL or Git URL supplied in natural language.
3. Explicit current repository or current workspace.

If no Target is actionable, enter `target_required`, ask one AskUserQuestion for the concrete Git URL, Local path or Source archive, and stop the turn. Do not ask a second question or inspect a repository in that turn.

At `target_resolved`, retain the Target kind, location, revision or archive snapshot, subdirectory and read-only access method. A Git URL defaults to its default branch unless a revision is supplied. A Source archive is a ZIP, tar, tar.gz or tgz attachment or local archive path; it is opened read-only and must not execute content or resolve entries outside its extraction root.

## Purpose Resolution

At `target_resolved`, infer the analysis purpose from the request. Treat 빠른 구조 파악, Kubernetes 설계 준비, 이관 문제점 점검 and 전체 상세 보고서 as explicit purposes. An explicit purpose transitions directly to `analysis_ready` without a question.

If the purpose is ambiguous, enter `purpose_required` and ask one AskUserQuestion with these choices: 빠른 구조 파악, Kubernetes 설계 준비, 이관 문제점 점검, 전체 상세 보고서, 기본 분석으로 진행. Do not ask for the Target again. The Target question and purpose question never occur in the same turn.

Create `ResolvedAnalysisRequest` at `analysis_ready`:

```text
target: kind, location, revision, subdirectory, access
intent: repository_structure_overview | kubernetes_design_preparation | migration_risk_assessment | full_repository_assessment | baseline_kubernetes_analysis
scope: repository | deployable components | migration-relevant components | entire repository
focus: purpose-specific analysis areas
output_mode: summary | detailed
provider: target-derived
phase: analysis_ready
```

Map 전체 상세 보고서 to `full_repository_assessment`, `entire repository`, all required analysis areas and `output_mode: detailed`. Map 빠른 구조 파악 to component topology, entrypoints and runtime dependencies; Kubernetes 설계 준비 to build, runtime, configuration, network and state; 이관 문제점 점검 to blockers, gaps and deployment readiness; 기본 분석으로 진행 to deployable components, runtime dependencies and design inputs. The other purposes use `output_mode: summary`.

`provider` is derived from the Target kind and `phase` is derived from this state machine. Never ask the user to select `summary`, `detailed`, `provider` or `phase`.

Only `analysis_ready` may call a repository discovery tool. An inaccessible Target remains unresolved until the user provides a safe, readable alternative; never request credential values.
