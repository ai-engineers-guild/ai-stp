---
description: "Decision to structure server applications as vertical slices with a shared core and separate DTO, domain, and ORM entities."
last_verified: "2026-08-05"
---

# ADR-0037: Feature-slice architecture for server applications

Status: accepted.

## Context

The `apps/api` and `apps/worker` applications begin materializing in the platform phase. `docs/engineering/repository-structure.md` already sets the boundary: `apps/*` holds entry points and dependency assembly, while a feature package owns its area's models, scenarios, and ports. An internal application-code organization principle is needed to prevent a `service`/`manager` layer from spreading and to avoid mixing transfer shape, domain model, and storage table. `SPEC-010` requires web and CLI to invoke the same application scenario, while `SPEC-017` requires one envelope and one route for a shared operation. Without an explicit decision, vertical areas readily dissolve into horizontal layers with shared rules.

## Options

1. Horizontal `routers`/`services`/`models` layers. Familiar, but distributes one area across three directories, encourages a generic `service` without domain responsibility, and mixes levels.
2. One Pydantic domain model serving simultaneously as DTO, domain entity, and ORM row. Fewer classes, but couples transfer shape, domain invariants, and storage schema; changing one breaks the others.
3. Vertical slices by area with a shared core and explicit separation of DTO, domain entity, and ORM entity. More types, but each area is autonomous and level boundaries are verifiable.

## Decision

Option 3 is accepted.

`apps/api` and `apps/worker` are organized as vertical slices by area, such as `health` and `system`. Each slice holds its route or handler, application scenario, DTO, and area storage adapters. Shared cross-cutting content lives in the application's shared core: envelope and correlation, error handlers mapping to the code registry, observability provider, settings, and logging.

Data shape is separated into three independent levels:

- a Pydantic DTO describes boundary input and output and participates in OpenAPI;
- a domain entity expresses area invariants and does not depend on transport or storage;
- a SQLAlchemy ORM entity describes a table and does not leave the storage layer.

Conversions between levels are explicit. OpenAPI is treated as a code projection, while contract truth lives in fixtures `#71`; drift fails the equivalence check.

## Consequences

- `SPEC-017` receives skeleton requirements, and `SPEC-018` inherits the same principle for the worker;
- a generic `service`/`manager` without narrow domain responsibility is prohibited by `repository-structure.md`;
- level separation creates more types and explicit conversions, covered by area unit tests;
- OpenAPI-to-fixtures `#71` equivalence becomes a mandatory contract test;
- no empty directories are created; structure arrives with the area's first behavior.

## Reconsideration conditions

This decision will be reconsidered if separating DTO, domain, and ORM creates conversions without domain value in most areas, or if a demonstrated need arises to make OpenAPI, rather than fixtures `#71`, the contract source.
