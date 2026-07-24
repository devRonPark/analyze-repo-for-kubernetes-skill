# Source Intake State

Apply this state machine before repository analysis. It preserves the existing Interview-first AskUserQuestion flow: a missing Target produces one question and ends the turn.

```text
start -> target_required | target_resolved
target_required -> target_resolved
target_resolved -> analysis_ready
```

## Target Resolution

At `start`, resolve exactly one Target in this order:

1. Git URL, Local path or Source archive supplied as Slash Command Input.
2. GitHub URL or Git URL supplied in natural language.
3. Explicit current repository or current workspace.

If no Target is actionable, enter `target_required`, ask one AskUserQuestion for the concrete Git URL, Local path or Source archive, and stop the turn. Do not ask a second question or inspect a repository in that turn.

At `target_resolved`, retain the Target kind, location, revision or archive snapshot, subdirectory and read-only access method. A Git URL defaults to its default branch unless a revision is supplied. A Source archive is a ZIP, tar, tar.gz or tgz attachment or local archive path; it is opened read-only and must not execute content or resolve entries outside its extraction root.

Only `analysis_ready` may call a repository discovery tool. An inaccessible Target remains unresolved until the user provides a safe, readable alternative; never request credential values.
