# Source Intake State

Apply this state machine before repository analysis. It preserves the Interview-first AskUserQuestion flow: a missing Target first selects the source method, then collects the target value in a later turn.

```text
start -> source_method_required | target_resolved
source_method_required -> target_value_required
target_value_required -> target_resolved
target_resolved -> purpose_required | analysis_ready
purpose_required -> analysis_ready
```

## Target Resolution

At `start`, resolve exactly one Target in this order:

1. Git URL, Local path or Source archive supplied as Slash Command Input.
2. GitHub URL or Git URL supplied in natural language.
3. Explicit current repository or current workspace.

If no Target is actionable, enter `source_method_required`. Ask exactly one AskUserQuestion using Codex `request_user_input` when available, then stop the turn without repository discovery:

```text
소스를 어떻게 제공하시겠어요?
- Repository URL
- Local directory path
- Source archive
```

If the user selects `Repository URL`, enter `target_value_required` and ask exactly one follow-up AskUserQuestion:

```text
분석할 GitHub 또는 Git repository URL을 입력해 주세요.
```

If the user selects `Local directory path`, enter `target_value_required` and ask exactly one follow-up AskUserQuestion:

```text
분석할 local directory path를 입력해 주세요.
```

If the user selects `Source archive`, enter `target_value_required` and ask exactly one follow-up AskUserQuestion:

```text
분석할 ZIP, tar, tar.gz 또는 tgz archive path를 입력해 주세요.
```

The first source-method question and second target-value question never occur in the same turn. Do not inspect a repository while either `source_method_required` or `target_value_required` is active.

When the Codex `UserPromptSubmit` and `PreToolUse` hooks are installed and trusted, they enforce `source_method_required` and `target_value_required` before a local repository discovery tool runs. The hook cannot display AskUserQuestion itself; it only blocks premature discovery and returns the question text in the deny reason. They permit a standalone installed `SKILL.md` bootstrap read, but reject a command that combines that read with workspace or repository discovery. Codex hosted web tools do not currently invoke `PreToolUse`; their no-discovery rule remains enforced by this skill contract. Without a trusted hook, this state machine remains a best-effort skill contract.

At `target_resolved`, retain the Target kind, location, revision or archive snapshot, subdirectory and read-only access method. A Git URL defaults to its default branch unless a revision is supplied. A Source archive is a ZIP, tar, tar.gz or tgz attachment or local archive path; it is opened read-only and must not execute content or resolve entries outside its extraction root.

## Purpose Resolution

At `target_resolved`, infer the analysis purpose from the request. Treat 빠른 구조 파악, Kubernetes 설계 준비, 이관 문제점 점검 and 전체 상세 보고서 as explicit purposes. An explicit purpose transitions directly to `analysis_ready` without a question.

If the purpose is ambiguous, enter `purpose_required` and ask one AskUserQuestion with these choices: 빠른 구조 파악, Kubernetes 설계 준비, 이관 문제점 점검, 전체 상세 보고서, 기본 분석으로 진행. Do not ask for the Target again. The source-method, target-value and purpose questions never occur in the same turn.

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
