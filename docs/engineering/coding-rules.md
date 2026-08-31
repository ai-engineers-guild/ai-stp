---
description: "Rules for errors, I/O, security, and predictable behavior."
last_verified: "2026-08-03"
---

# Implementation rules

## Machine output

Machine output uses a versioned JSON envelope, a stable error code, and an operation ID; it contains no ANSI/Rich formatting or secrets, and handles unknown fields according to the version policy.

## Files and paths

Use `pathlib`, absolute targets for mutating operations, checks that do not follow links, rejection of directory traversal, symbolic and hard links, and special devices, bounded reads, and atomic replacement with `fsync` where durability is required.

## Process execution

Use `shell=False`, an argument array, the exact executable path, a filtered environment, time and stdout/stderr size limits, process-group termination, and result-schema validation.

## Errors

Errors are typed by cause and are not logged twice. Retries are allowed only for explicitly transient and idempotent operations. A partial result preserves the last confirmed state, and a fallback must not silently change semantics.

## Configuration

Startup fails closed on uncertainty, defaults are explicit, an unknown sensitive key is an error, secrets are redacted, and the complete environment is never printed.

## Determinism

The digest is computed from canonical bytes, normalized paths, and the schema version. A representation that depends on the interpreter version must not be hashed.

## Frontend (apps/web)

The rules below belong to `apps/web` and are enforced by its gates under `ADR-0043`;
the stack and its selection belong to `ADR-0043`, not this section.

### Component organization

Components follow atomic design: `atoms` (primitives without business meaning),
`molecules` (combinations of atoms), `organisms` (composite blocks with behavior), and
`layouts` (page shells); pages are assembled by App Router routes. Imports flow only
downward through the layers: `atoms` do not import `molecules`, `molecules` do not
import `organisms`, and so on; the import-boundary lint rejects violations.

### Type discipline

- Complete prohibition of `any`: strict TypeScript 7 catches implicit `any`; explicit
  `any` and unsafe structural access (`no-unsafe-*`) are caught by type-aware
  `typescript-eslint`.
- No duck typing: identifiers, keys, and tokens are expressed nominally (branded
  types), not as bare strings; external data (API responses, environment, form input)
  is accepted only through types generated from `#71` and `zod` schemas; structural
  casts that bypass validation are prohibited.
- No god objects: a module is constrained to one responsibility and limited in size;
  a generic dumping-ground `utils`, a single global context, and a single global store
  are prohibited; the store is split into narrow slices along responsibility boundaries.

### Theme, color, and strings

- Colors come only from semantic theme tokens (CSS variables); a hard-coded color
  value in a component is prohibited and rejected by lint (`REQ-2214`).
- Light and dark themes are supported from launch; a component must not depend on a
  single theme.
- User-facing strings are localized through `next-intl`; literal user-facing text in
  markup is prohibited (`ADR-0035`, `REQ-2203`).

### Server-client boundary

Private data and secrets are read on the server and do not enter the client bundle;
`"use client"` is added only where needed. Authorization decisions are not made on the
client: route protection reads the server session, while the final rule remains with
the API (`ADR-0018`, `REQ-1003`, `REQ-1011`).
