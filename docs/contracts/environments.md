---
description: "Project environment composition, native reservations and prerequisite inspection."
last_verified: "2026-09-07"
---

# Project environments

`environment plan --operation <id> --operation <id>` composes exact native child
plans. SPEC-069 owns behavior. Each child keeps its harness and SetupVersion;
the aggregate does not create a SetupVersion belonging to several harnesses.

The existing transaction response gains `kind`: `single_setup` or `environment`.
Environment headers have null setup and harness identities. Children identify
their original harness, setup stable ID and version. Reservations use canonical
physical paths from digest-bound complete capture coverage. Paths resolve against
`native_capture.base_root`, including the declared companion when it is `parent`.

Approval, application, status, cancellation and recovery use `install transaction`.
Repeated `--provider-for <harness>=<executable>` selects each provider independently;
omission uses that harness's recorded or acquired provider. A generic `--provider`
cannot ambiguously select an executor for several products.

SQLite migration 33 adds `transaction_kind` and permits separate harnesses at one
scope. Existing single-setup digests stay unchanged. No destructive downgrade is
declared: preserve the registry and settle active operations with a compatible
reader before rolling back a release.

An uncertain child stops forward work. Recovery verifies each original retained
snapshot, settles only its bound journal, and plans reverse-order restoration
through the original providers. The child's terminal `partial` state remains
accurate even when a separate return compensates its effects. Repeating recovery
of a terminal aggregate creates no additional effect.

`environment inspect` is the read-only preparation surface of SPEC-070. It reports
prerequisite observations and concrete CLI argument arrays. Native verification
remains a separate provider observation; program installation receipts alone
never label the whole environment ready.
