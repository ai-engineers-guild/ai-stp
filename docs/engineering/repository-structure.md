---
description: "Target monorepository structure and code ownership rules."
last_verified: "2026-08-05"
---

# Repository structure

```text
apps/
  cli/
  api/
  worker/
  web/
packages/
  foundation/
  identity/
  passports/
  projects/
  registry/
  composition/
  assurance/
  contracts/
  sync/
  installations/
  providers/
  storage/
  tool_runner/
schemas/
skills/
  canonical/
  projections/
tests/
  unit/
  property/
  integration/
  api/
  scenario/
  contract/
  e2e/
  fixtures/
  golden/
docs/
specs/
```

## Boundaries

`apps/*` contains entry points and dependency assembly. A feature package owns the models, use cases, and ports of its domain. `storage` implements storage, but not business rules. `providers` adapts public provider contracts. `tool_runner` runs external tools, but does not determine the final verdict. `foundation` contains only genuinely cross-cutting primitives. `contracts` owns the `/v1` wire boundary: request and response models, shared conventions for headers and cursors, and the mapping from error codes to statuses. It contains no business rules and makes no network calls; `apps/api` must conform to it, not generate it.

The internal organization of `apps/api` and `apps/worker` follows vertical slices with a shared core under `ADR-0037`, while data representation is separated into DTOs, domain entities, and ORM entities. Platform and CLI tests are separated by subdirectories and markers under `docs/engineering/testing.md`. The job-queue table schema lives in the shared Alembic migration tree under `SPEC-018` and `ADR-0038`.

Generic packages named `domain`, `common`, `utils`, or `manager` are prohibited unless they have a narrow domain responsibility. Empty directories are not committed; structure is introduced when its first behavior appears.

Materialized in phase 1: `packages/foundation` (typed identifiers, canonical JSON, byte input, hash domains, content revisions, exact references, canonical timestamps, machine envelope), `packages/passports` (passport envelope, five kinds, facts, component-version and setup-version passports), `packages/assurance` (author-verification record), `packages/contracts` (frozen `/v1` boundary, fixture corpus, mock transport and conformance suite, machine-help shape), `apps/cli` (parser, envelope, commands, device identity, tiered secret storage, local registry with developer and device passports, `/v1` cloud client, and catalog cache), `schemas/v1` with generated schemas, and `tests/{unit,property,contract,golden}`.

`apps/cli` is structured so that each command is declared exactly once. The command registry declares descriptors as data; the parser is assembled from the registry, and `help --agent` renders the same descriptors, so the parser and machine help cannot diverge. Click remains a thin layer under `ADR-0057`: it parses arguments and invokes a use case, but does not build the envelope, choose error codes, or determine the exit code.

Materialized in sprint 1: `packages/contracts`, the frozen `/v1` boundary. It sits at the top of the package chain, so it owns the repository schema-generation entry point: the `just back-gen` and `just back-static` targets invoke `ai_stp_contracts.schemas` and generate both `schemas/v1/*.schema.json` and `schemas/v1/openapi.json`.

The package intentionally carries three things that usually live in tests: the fixture corpus, mock transport, and conformance suite defined by `docs/contracts/fixture-corpus.md`. They are shared with the server track: a corpus under `tests/` cannot be imported from another application, and two independently written example sets would match only by accident. The mock requires `httpx`, so it is exposed through the optional `ai-stp-contracts[mock]` dependency: the server side needs the corpus and conformance suite, but not the HTTP client.

The remaining directories appear with their first behavior.
