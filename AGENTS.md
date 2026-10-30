# ai-stp working rules

## Source of truth

The current user task takes precedence. Implemented code, generated schemas and
executable tests define behavior. Keep documentation limited to current usage,
engineering boundaries and operations. Track work and release evidence in GitHub;
do not add requirements catalogues, ADR collections, roadmaps or session reports.

## Code map

- `apps/cli`: Rust CLI and library; the product engine. Start with its README
  and `ai-stp help --agent --json` for implemented commands.
- `apps/api`, `apps/worker`, `apps/platform`: HTTP, jobs and server services.
- `apps/web`: account, catalog and generated HTTP client.
- `apps/desktop`: Tauri shell consuming the native CLI JSON contract.
- `packages`: shared models, canonicalization, passports, sources and schemas.
- `skills/canonical`: agent guidance; projections are generated.

Regenerate `schemas/v1`, `skills/projections` and the contract
inventory with `just back-gen`; native projections with `just cli-gen`;
documentation indexes with `just docs-gen`. Do not hand-edit generated output.
Published provider-kit bytes retain their original provenance references, which
resolve against their source revision in Git history.

## Product boundaries

A setup configures one harness. Component kinds are `instruction`, `skill`, `mcp`,
`hook`, `command`, `agent`, `plugin`, `setting` and `cli`. Published setup/component
versions are exact and immutable. Author identity and byte verification are separate.

The CLI selects, validates and assembles. Only the public harness installation
component writes final harness state. Setup systems are ai-stp components with
separate repositories. Harness executables remain user/vendor managed; never
install, pin, update or remove them. The system does not call model APIs or require
a model key. Active-agent changes require staged replacement, handoff and restart.
A mechanical refusal is a refusal, not permission for an alternate bypass.

## Authority and data

Complete authorized reversible work without repeated permission requests, including
committing, merging, tagging, publishing and deploying verified changes. Use an
exact plan/digest, revalidate preconditions and make retries idempotent. Report the
chosen action, evidence and rollback path.

A separate decision is needed only for deleting data without recovery, linking
someone else's account or new credentials, elevating system privileges, or changing
an existing object's visibility or access. Do not create backups or snapshots unless
requested. Restrict cleanup to the authorized project and hosts. Preserve credentials,
user runtime state and other projects. Secrets never enter logs, fixtures or docs.

## Changes and checks

Keep permanent local/remote `dev` and `main`. Branch from current `dev`, PR into
`dev`, then promote same-repository `dev` into `main` after exact-SHA checks.
Use merge commits; preserve history. See [Git workflow](docs/engineering/git-workflow.md).
Stage only intended paths. The agent does not pass `--author` or add fictional
`Co-authored-by` / `Generated-by` lines. Read identity using
`git config --global --get user.name` and `git config --global --get user.email`.
The agent does not change `user.name` or `user.email`.

Run affected checks through `just`: `docs-check`, `back-static`, `back-test`,
`cli-check`, `web-check`, and `desktop-check` for desktop changes. `just --show
check` gives the aggregate; CI runs its shards. Record commands and observed results
on the exact final SHA in the PR. Generated output and its source change together.
Finish with a diff review, current documentation and synchronized branches.

Source authoring and ordinary code validation may share a host. Compiling checks,
unit tests, formatting, linters and LSP use its existing managed toolchains,
cache and leases. Real application, GUI, emulator and resource-heavy integration
workloads use their assigned execution targets; platform acceptance stays on
the corresponding native hosts. Keep source-check compilation separate from
application deployment and runner-fleet admission.
An admitted local store is sufficient for local code checks. Shared network
storage requires acceptance of the semantics the operation actually uses; its
unfinished adoption does not block unrelated validation in an available local
environment. Do not change runner fencing or shared profiles to run a check.

Use the existing host-managed Cargo/uv/Bun frontends and the approved network-cache
client contract. Preserve compiler, platform, lockfile and checksum identity. Read
Cargo's `target_directory` and `build_directory` from locked offline metadata;
do not construct their paths, add checkout-local target overrides or bootstrap a
missing compiler/profile. Coordinate shared profile changes with its owner.
Verify that each local check's frontend and external subcommands retain this
managed placement. Run unsupported entry points in CI until their native owner
qualifies local use.
Keep host paths, configuration and runtime receipts outside public Git. Cleanup
belongs to the native provider or NDS Cleaner, with verified ownership, leases
and observed last use. The payload retention target is 24 hours, selected only
after the owning consumer's native acceptance; preserve legacy 72-hour and
terminal-evidence floors until separately admitted. Installed environments, pinned application
artifacts and live runtime data remain with their owners; filesystem age alone
does not make them disposable.
Managed store placement and a selected frontend do not establish central-only
transport. Preserve canonical locks, integrity and credential precedence, and
qualify cold, warm, fresh-offline and cold-outage behavior before cache rollout.
Use the existing shared bootstrap/network authority; do not create a per-project
relay, rewrite locks or silently fall back to public transport for unqualified sources.

For `apps/web` changes, read [web DESIGN](apps/web/DESIGN.md) and
[product DESIGN](docs/product/DESIGN.md). Compose interfaces from registered
atoms/molecules/organisms/layouts/screens and theme icons. Adapt before creating;
new components need a reason, Storybook story and component test. Raw select/table
primitives and direct Radix imports belong only in their owning kit component.

Code, comments, identifiers, commits and documentation are English; explicitly
localized product content may use its locale. Add no speculative dependencies,
empty abstractions or duplicate documentation.
