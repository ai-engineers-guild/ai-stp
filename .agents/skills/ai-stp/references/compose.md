# Compose

To add or remove a member of a saved setup, start the `change` intent.
Do not type `ai-stp setup compose plan`, `ai-stp setup compose apply`, or
`ai-stp setup update apply`. The engine mints a new setup identity, records
lineage to the source, and installs the derived pin. The original setup id
stays restorable.

1. Pass `harness_id`, the source `setup_id`/`setup_version` when known, and
   `component_id`/`component_version`. Omitted source means the first-party
   `baseline` for that harness. Omitted action is `add`.
2. Call `ai-stp task start` with intent `change` and execute continuation
   `argv` only when `actor` is `cli`. Relay one blocked question through `ai-stp task answer`.
3. Report the derived setup id, whether a new identity was minted, and native
   verification. Envelope `ok` alone is not enough.

A custom composition that is not one member delta is expert select: resolve
`select propose` / `select confirm` from machine help, then pass the confirmed
proposal into the `install` intent. Confirmation freezes a private setup; it
does not install it. Do not type compose plan or apply. Recast, materialize,
and portability stay in machine help; do not choreograph those plan/apply
leaves from this playbook.

Do not reconstruct a published setup component by component; use
[install](install.md).
