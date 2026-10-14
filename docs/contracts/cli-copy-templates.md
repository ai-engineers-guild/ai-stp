---
description: "Canonical native CLI commands and agent handoffs for web copy blocks."
last_verified: "2026-10-14"
---

# CLI copy templates

`ai_stp_contracts.cli_copy` owns the executable commands, release URL and agent
prompts. `web_projections.py` generates the TypeScript projection. The native
`apps/cli-v2/scripts/verify.py` checks commands and required flags against the
actual Rust command registry. Web tests preserve exact catalog identities.

Object inspection uses `registry show` or `registry version` with an exact
identifier and version. Selection impact is a read-only local command. Owner
creation starts the author intent. New local identities use explicit `init`;
existing Python state requires the explicit migration plan/apply boundary.
Account copy starts a provider-specific plan; the agent applies its digest and
polls the resulting session. A plan alone does not issue a browser code.

Catalog installation copy is an **agent prompt**, not a shell command. It
preserves the selected object and exact version and asks the agent to obtain
local target/source/provider facts from the native install input schema. The
browser cannot supply those facts and never emits an incomplete install argv.
Local paths, credentials and access tokens are never interpolated by the web.
Harness installation and updates remain owned by the harness and its user.

The landing links to the version-bound native GitHub Release. Its notes own archive
verification and installation for Linux, macOS and Windows. There is no Python
runtime prerequisite. Provider execution is currently Linux-only; the other
platforms expose their supported native operations without claiming installation.

Copy buttons insert the source text exactly and report clipboard failures.
They do not claim that copying installed anything. Documentation links retain
the local `/docs` entrypoint.
