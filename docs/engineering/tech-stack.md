---
description: "Target MVP stack and rules for choosing dependencies."
last_verified: "2026-08-05"
---

# Stack

## Application

| Area | Choice |
|---|---|
| Language | Python 3.12 and 3.14 — both are checked in CI |
| Dependency management | uv and one root `uv.lock` after bootstrap code |
| CLI | Click on `ADR-0057`; machine JSON is mandatory |
| Device key and secrets | Ed25519 via `cryptography`; `keyring` with a closed list of trusted backends via `ADR-0058` |
| Local registry | standard `sqlite3` with WAL and own migration runner via `ADR-0059`; Alembic and SQLAlchemy are not used in CLI |
| Cloud CLI client | `httpx` with limited timeouts and retries; transport is part of `Endpoint`, so mock from #71 and real server go the same path |
| Schemas | Pydantic 2; JSON Schema and OpenAPI 3.1 are generated from models |
| API | FastAPI |
| Server DB | PostgreSQL |
| Local DB | SQLite |
| ORM/migrations | SQLAlchemy 2, Alembic |
| Worker | PostgreSQL-backed queue |
| Object storage | RustFS/S3 |
| HTTP | httpx |
| Frontend | Next.js App Router (React, RSC + Server Actions) on `ADR-0043`; TypeScript 7 as typecheck + side TS6 for `typescript-eslint`; Tailwind 4 with tokenized theme (light/dark); bilingualism `next-intl`; standard `shadcn/ui` + Radix by atomic design (atoms/molecules/organisms/layouts); typed client from `schemas/v1/openapi.json` via `@hey-api/openapi-ts`; client store `zustand`; forms `react-hook-form` + `zod`; ESLint flat config lint (type-aware, full prohibition `any`); tests Vitest + Testing Library + Playwright + MSW; package manager `bun` with `bun.lock` in separate Node-workspace `apps/web` |
| Email | Resend |
| Format/lint | Ruff |
| Types | Pyright strict |
| Tests | pytest, Hypothesis, contract/golden/integration |
| Docs | MkDocs, Markdownlint, Mermaid |

`keyring` and `cryptography` are dependencies of `apps/cli` according to `ADR-0058`. `keyring` is imported lazily: its import takes about 100 ms — three times more than Click — and most calls do not open the storage. The backend it selects is only accepted from a closed list: it has been measured that with `keyrings.alt` installed, `PlaintextKeyring` is preferred, writes pass silently, and the secret is written to disk in base64 while the library reports success.
Schemas and the OpenAPI document are not written by hand: the only source is the `packages/contracts` models, and `just back-gen` generates both artifacts from them. A handwritten OpenAPI alongside the generated schemas would be a second source of truth, which is prohibited by `SPEC-015` REQ-1508. The document validation is performed by `openapi-spec-validator` in the `dev` group; `httpx` is needed only on the client side and is moved to the optional dependency `ai-stp-contracts[mock]`.
Python workspace created: root `pyproject.toml` with a single `uv.lock` — the source of truth for all Python dependencies. Documentation tools live in the `docs` group, development tools — in the `dev` group; the temporary `docs_scripts/requirements.lock.txt` was removed by the same change. Node tools are fixed in `docs_scripts/bun.lock`: one package manager per language, `npm` is not called. Two active Python sources of truth are not allowed.

## Project index

- manifests and lockfiles;
- tree-sitter for structure where justified;
- LSP adapters for Python, TypeScript/JavaScript, Rust, Go, and Dart/Flutter;
- parsers of information formats and general parsing of limited safe text;
- local search using SQLite without a separate search service;
- embeddings and vector storage are absent in the MVP.

## Toolset

The initial setup configures a single full profile `mvp-full` on `ADR-0019`. The composition is defined by a versioned policy, not by the current contents of the project; specific versions are selected from supported manifests at the implementation stage.

## Dependency Rules

- a new dependency closes a specific gap;
- version and transitive resolution are locked;
- external executable tools are not mixed in the same Python environment;
- provider-specific dependency resides in adapter/provider;
- a custom build backend is not created without proven need;
- the model interface client is not included in the MVP dependencies for `ADR-0022`;
- APM/SX are not mandatory dependencies.
