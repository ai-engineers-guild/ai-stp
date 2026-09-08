---
description: "ADR-0170: The CLI updates itself through the installer that owns the PyPI distribution."
last_verified: "2026-09-08"
---

# ADR-0170: The CLI updates itself through its owning installer

Status: accepted

## Context

`ai-stp-cli` is one public distribution (`ADR-0146`). Users install it with
`uv tool`, pipx, or a dedicated venv. Provider/harness update already exists and
replaces attested setup-system binaries, not this wheel. A published newer wheel
does not change an old executable already on PATH. The installed `0.0.17` line
cannot grow a notifier after the fact.

PyPI is the publication channel for this distribution. Providers default to
GitHub attested releases (`ADR-0146`) with an explicit index path (`ADR-0141`).
Those channels stay distinct.

## Options

1. Tell operators to run `uv tool upgrade` in documentation only.
2. Build a private package manager that unpacks wheels over `sys.prefix`.
3. Detect the owning installer, pin an exact PyPI artifact, and invoke that
   installer; keep provider and setup lifecycles separate.

## Decision

**Option 3.** `ai-stp update` is a first-class command family. It never calls
`provider update` or `harness update`. It never uses `sudo`,
`--break-system-packages`, or a rewrite of an editable checkout.

Apply installs the exact planned wheel through:

- `uv tool install` with the staged wheel for `uv_tool`;
- `pipx install --force` of that wheel for `pipx`;
- the venv interpreter's `python -m pip` for a dedicated pip venv.

Shared and system environments receive a migration plan, not a mutation.
`source_managed` installations report that fact and stop.

Startup notification is opportunistic and fail-open. The JSON envelope remains
the only stdout object in machine mode. A check that writes the updater cache is
an explicit exception to read-only I/O and is not hidden inside `doctor`.

Legacy `0.0.17`/`0.0.20` require one bootstrap with the current installer to
reach an updater-enabled release. After that, this family is the supported path.

## Consequences

- `packaging` is a declared CLI dependency for PEP 440 comparison.
- Configuration grows four `update.*` fields (`docs/contracts/cli-config.md`).
- Wire models live in `docs/contracts/cli-self-update.md` and
  `urn:ai-stp:schema:v1:cli-self-update-*`.
- Provider acquisition default remains GitHub. Qualifying the provider index
  path is a separate remaining item (roadmap B16), not a silent fallback here.

SPEC-072 owns acceptance.
