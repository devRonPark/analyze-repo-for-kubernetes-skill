# Dependency Analysis

Represent dependencies as directed relationships from a logical source component to a target.

## Required Relationship Fields

- source component
- target component or external system
- dependency type
- protocol or mechanism
- endpoint or configuration name when known
- required or optional
- build-time or runtime
- Execution Locus
- evidence status and file locations

## Execution Locus Values

Use one of:

- browser
- server process
- worker process
- scheduled/job process
- build pipeline
- deployment controller
- human/administrative
- external system
- Unknown

The logical source and execution locus can differ. A static frontend component may logically depend on an API, while the actual network caller is the user's browser rather than the Nginx Pod.

## Dependency Types

Examples include HTTP, gRPC, SQL, message queue, cache, SMTP, object storage, filesystem, package import, generated client, and build artifact.

## Required Output

Produce both a dependency matrix and a text dependency graph. The two representations must agree. Separate build-time relationships from runtime relationships and do not treat package declarations alone as proof of runtime communication.
