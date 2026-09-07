---
description: "Local setup identities, verified native recovery bindings and CLI selection."
last_verified: "2026-09-07"
---

# Preserved setups

A preserved setup is an immutable local identity for captured native configuration,
separate from a portable SetupVersion and the provider backup reference. SPEC-068
owns requirements; ADR-0167 owns the separation of identities.

SQLite migration 32 adds `preserved_setup`, keyed by `stable_id`, with unique
`operation_id` referencing `operation_plan`. It stores `target_id`, canonical
`provider_target`, `target_scope`, `provider_id`, `backup_ref`, `snapshot_digest`,
`roots`, `excluded`, and `created_at`. Coverage arrays are JSON. Migration 34 adds
`base_root`: `target` by default, or `parent` for the declared companion cover.
The registry holds no recovery payload bytes. The operation binding makes
registration and recovery retries idempotent.

Registration requires the exact stored provider plan and fresh status: snapshot
operation, digest, base and coverage must equal the capture binding, verification
must be `verified`, and the slot must be held against retention. Missing, damaged,
unheld or differently bound evidence cannot become a preserved setup. Restoration
rechecks the provider, target, scope and snapshot digest during planning.

`setup preserve plan` creates an ordinary installation plan for complete capture.
`install approve` binds its digest; `install apply` invokes the provider and returns
`preserved_setup_id` only after evidence verification. Native installation and
replacement also register the previous setup.

`setup preserved list` works after restarting the CLI. Without provider observation,
`verification=recorded_verified` describes the original evidence and
`target_state=not_observed` makes no present-tense claim. `setup preserved show
--setup <id> --provider <executable>` checks current snapshot availability and
whether the whole covered target matches.

`setup restore plan --preserved-setup <id>` creates a new return plan and includes
preservation of the current configuration. Its ordinary approve/apply lifecycle
also returns the newly preserved current setup identity.

`setup preserve recover --operation <id> --provider <executable>` recovers the
identity after a lost response. It checks the bound release, exact original plan
and fresh status. It invokes neither apply nor provider recovery and does not
change the installation journal state. Missing evidence refuses. The recovered
setup can be selected for return even while the original installation is `partial`.

Dropping the new tables or fields may destroy the only index of retained recovery
copies. Preserve the registry and provider pools when returning to an older CLI;
old readers may not expose the identities. Migrations 33 and 34 declare no
destructive reverse.
