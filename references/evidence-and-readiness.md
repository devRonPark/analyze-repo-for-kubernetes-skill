# Evidence and Readiness

## Evidence Status

Use exactly one status for every material finding:

- **Confirmed:** directly supported by repository source, executable configuration, or a successful command result
- **Inferred:** strongly suggested by multiple clues but not directly established
- **Unknown:** evidence is missing or insufficient
- **Conflicting:** authoritative sources disagree

Preserve conflicts. Do not silently choose whichever value appears most convenient for Kubernetes design.

## Evidence Priority

Prefer executable source and runtime configuration over comments. Prefer production configuration over development examples. Treat README documentation as useful evidence that must still be checked against source when possible.

## Readiness Verdict

End with exactly one:

- **Ready:** another agent can begin Kubernetes design without a blocking repository fact
- **Needs Input:** design can start, but one or more choices or missing facts require user input
- **Blocked:** a critical fact prevents a responsible design from beginning

List the specific reason for every Needs Input or Blocked verdict. Unknown does not automatically mean Blocked; judge whether the missing fact is required for the next design step.
