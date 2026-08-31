---
description: "Decision to use Typer as the CLI command parser."
last_verified: "2026-08-04"
---

# ADR-0013: CLI command parser

Accepted on 2026-08-04. Superseded by `ADR-0057-click-as-cli-parser.md`: the parser is built
from the command registry, so the type-annotated functions for which Typer was chosen
do not exist, while Typer itself brings in Rich and a vendored compatibility layer for
Click. Read this record only for the context of the original choice.

## Context

`tech-stack.md` declared the choice between Typer and argparse deferred to a separate ADR, but that ADR did not exist. Phase 1 depends on this choice because the command skeleton is created before schemas and local state.

The command surface is large from the outset: about seventeen groups, with each mutating command having a plan–apply pair and separate confirmation. The machine contract itself does not depend on the parser: our code, rather than the library, forms the JSON envelope, error codes, and `operation_id` according to `contracts/cli-json.md`.

The estimate of seventeen groups at the time of the decision was based on the `cli-api-contract` document, which was retired during the move to a single owner for each normative fact. The complete command surface currently has no owner: `docs/agent/machine-help.md` describes the entry point, and the list will appear in `apps/cli` with generated machine help. The number remains here as the historical scale of the decision, not as a current requirement.

The dependency policy requires a concrete gap, a pinned version, an owner, and a removal path for every new dependency.

## Options

1. Standard-library `argparse`. Zero dependencies, but seventeen subparser trees with plan–apply pairs produce substantial repetitive code, while parameter typing remains manual.
2. `Typer`. A thin layer over Click, with commands declared through type annotations. Two transitive dependencies, but it matches the adopted Pydantic 2 style and removes most boilerplate.
3. `Click` directly. The same dependency weight as Typer, but without deriving parameters from annotations.
4. A custom parser. Rejected immediately: no custom framework is created without demonstrated need.

## Decision

Typer is used.

The parser remains a limited `apps/cli` application layer: it parses arguments and invokes a scenario, but does not form the JSON envelope, define error codes, or make confirmation decisions. Human-readable and machine output are separate; `--json` enables the strict envelope.

The Typer version is pinned in the root `uv.lock` with the first code.

## Consequences

- CLI contract tests verify the envelope and exit codes, not library behavior;
- replacing the parser affects only `apps/cli` and changes no machine contract, so the dependency removal path remains short;
- Click and Typer appear in the dependency tree and undergo license and security checks like all other dependencies;
- `tech-stack.md` no longer contains a deferred choice.

## Reconsideration conditions

The decision is reconsidered if Typer is no longer maintained, if it begins imposing output behavior incompatible with the strict envelope, or if the dependency policy prohibits transitive dependencies of this class in the core.
