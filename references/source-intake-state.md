# Source Intake State

Use stable source-method IDs instead of branching on AskUserQuestion labels.

| ID | User-facing choice | Next state |
| --- | --- | --- |
| `remote_git` | 원격 Git URL | `awaiting_target_value` with a remote Git URL prompt |
| `local_checkout` | 로컬 checkout 경로 | `awaiting_target_value` with a Local path prompt |
| `source_archive` | 소스 압축 파일 | `awaiting_target_value` with an archive path prompt |

The source-method question must record the selected ID before ending the turn. A method and concrete value supplied together skip `awaiting_target_value`. Do not inspect a repository while the state is `awaiting_source_method` or `awaiting_target_value`.

For a `local_checkout` value, run [source_intake.py](../scripts/source_intake.py) with `accept --source-method local_checkout --value <path>`. It validates the exact path, resolves the Git root and emits one JSON object with `state: resolved`, target, revision, subdirectory and read-only access method. Never substitute a similar path after a failure.

Remote Git and archive values enter `target_supplied` until their dedicated acquisition slices resolve them. They must not be treated as a resolved analysis root yet.
