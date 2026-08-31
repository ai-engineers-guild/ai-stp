---
description: "Authorized reading of owner objects through the CLI."
last_verified: "2026-08-13"
---

# Owner objects in the CLI

`owner objects`, `owner object show`, and `owner version show` are read-only
projections of server-authorized owner models from `packages/contracts`. The
client does not merge them with the public catalog, local passports, or received
grants, and does not attempt to determine ownership itself.

The list accepts an optional closed object-kind filter, bounded page size, and
opaque cursor. The cursor is only returned to the server; the CLI neither parses
nor reconstructs it. Detail addresses an exact kind and stable identifier, while
version detail additionally addresses an exact `X.Y`.

Lifecycle state, visibility, trust lane, independent `author_verified` and
`component_verified` flags, eligibility, evidence, and whether publication may
start are shown exactly as represented by the server model. A received grant
does not create an owner object or permit writing to the original. All three
commands require an active cloud session and do not transmit local bytes or
credentials.
