# Source Intake State

Apply this state machine before repository analysis. It preserves the Interview-first AskUserQuestion flow: a missing Target first selects the source method, then collects the target value in a later turn.

```text
start -> source_method_required | target_resolved
source_method_required -> target_value_required
target_value_required -> target_supplied | target_resolved
target_supplied -> target_resolved
target_resolved -> purpose_required | analysis_ready
purpose_required -> analysis_ready
```

Use stable source-method IDs instead of branching on AskUserQuestion labels.

| ID | User-facing choice | Next state |
| --- | --- | --- |
| `remote_git` | 원격 Git URL | `target_value_required` with a remote Git URL prompt |
| `local_checkout` | 로컬 checkout 경로 | `target_value_required` with a Local path prompt |
| `source_archive` | 소스 압축 파일 | `target_value_required` with an archive path prompt |

Legacy Codex hook labels such as `Repository URL`, `Local directory path` and `Source archive` may be accepted as aliases, but the recorded source-method state is always `remote_git`, `local_checkout` or `source_archive`.

## Source Method Selection

At `start`, resolve exactly one Target in this order:

1. Remote Git URL, Local path or source archive supplied as Slash Command Input.
2. GitHub URL or Git URL supplied in natural language.
3. Explicit current repository or current workspace.

If no Target is actionable, enter `source_method_required`. Ask exactly one AskUserQuestion using Codex `request_user_input` when available, record the selected stable ID, then stop the turn without repository discovery:

```text
분석 대상 애플리케이션 소스 코드 제공 방식을 알려주세요.
- 원격 Git URL
- 로컬 checkout 경로
- 소스 압축 파일
```

The first source-method question and second target-value question never occur in the same turn. Do not inspect a repository while `source_method_required` is active.

## Target Value Collection

If the user selects `remote_git`, enter `target_value_required` and ask exactly one follow-up AskUserQuestion:

```text
분석할 원격 Git URL을 알려주세요.
```

If the user selects `local_checkout`, enter `target_value_required` and ask exactly one follow-up AskUserQuestion:

```text
분석할 Local path를 알려주세요.
```

If the user selects `source_archive`, enter `target_value_required` and ask exactly one follow-up AskUserQuestion:

```text
분석할 소스 압축 파일의 Local path를 알려주세요.
```

If a source method and concrete value are supplied together, skip `target_value_required`. Do not inspect a repository while `target_value_required` is active.

For a `local_checkout` value, run [source_intake.py](../scripts/source_intake.py) with `accept --source-method local_checkout --value <path>`. It validates the exact path, resolves the Git root and emits one JSON object with `state: resolved`, target, revision, subdirectory and read-only access method. Never substitute a similar path after a failure.

Remote Git and archive values enter `target_supplied` until their dedicated acquisition slices resolve them. They must not be treated as a resolved analysis root yet. A Git URL defaults to its default branch unless a revision is supplied. A source archive is a ZIP, tar, tar.gz or tgz attachment or local archive path; it is opened read-only and must not execute content or resolve entries outside its extraction root.

When the Codex `UserPromptSubmit` and `PreToolUse` hooks are installed and trusted, they enforce `source_method_required` and `target_value_required` before a local repository discovery tool runs. The hook cannot display AskUserQuestion itself; it only blocks premature discovery and returns the question text in the deny reason. They permit a standalone installed `SKILL.md` bootstrap read, but reject a command that combines that read with workspace or repository discovery. Codex hosted web tools do not currently invoke `PreToolUse`; their no-discovery rule remains enforced by this skill contract. Without a trusted hook, this state machine remains a best-effort skill contract.

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
