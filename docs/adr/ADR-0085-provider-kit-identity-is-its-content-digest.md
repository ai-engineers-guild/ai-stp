---
description: "Decision to give the public provider protocol v3 kit a content-addressed identity and a version-bump rule."
last_verified: "2026-08-15"
---

# ADR-0085: The provider kit's identity is its aggregate digest

Status: accepted. Supplements `ADR-0061` without replacing it: that record
continues to own the command set and capability model.

## Context

`ADR-0061` introduced `provider-kit/v3` as an immutable portable contract that
a public provider reads without access to private repositories. The kit carries
`kit_version` and `SHA256SUMS`, which binds the exact bytes of three machine
files.

`kit_version` does not identify the contract. Commit `851e3984`, which
introduced protocol v3, and its successor `797698b3` both published `0.1.0`,
but the latter changed the machine bytes: `recover-operation` was added to
`commands`, `core_commands`, and `apply_commands`; `setup_stable_id` and
`setup_version` were added to provenance; and the command-array bounds in the
`provider-info` schema moved from 5/6 to 6/7. The aggregates of these two
revisions differ:

| Revision | SHA-256 of `SHA256SUMS` |
| --- | --- |
| `851e3984` | `103d2e5e28990f42940a0ea8bb90e57bbd9406cbcb5f2a0ec58c23af731c23bc` |
| `797698b3` | `b220c3994b2219161d46b8db881c68e987b95998c4bf4111e88d0c94de964378` |

Thus, the string `kit_version: 0.1.0` denotes both the six-command and the
seven-command protocol core. A provider claiming conformance to "kit 0.1.0"
cannot say which of the two it conforms to.

At the same time, none of the five public providers references the kit at all:
searching all five repositories for `provider-kit`, `kit_version`, and
`SHA256SUMS` produces no matches. Each carries its own copy of
`provider_protocol_v3.py`—the same blob
`10a9879b6cecdd1e9bb8cbfe4acd0638cc287687`, duplicated five times and not
linked to its source.

This creates no current wire-level divergence: at the inspected HEAD revisions,
all five implement the same command set. What is missing is not compatibility,
but a way to prove it.

## Decision

The kit's identity becomes the **aggregate digest**: the SHA-256 of the
canonical bytes of `SHA256SUMS`, which already covers the three machine files.
It is written to a new generated file, `KIT-IDENTITY.json`, together with
`kit_version` and the protocol version.

The aggregate is intentionally **not** placed inside `manifest.json`: the
manifest is itself covered by `SHA256SUMS`, and writing the aggregate into it
would make the digest an input to itself.

`kit_version` is bumped to `0.2.0` once as a correction. `0.1.0` is declared
ambiguous and must not be used as a reference anywhere.

The roles are separated as follows:

- **aggregate digest** is what the provider pins. It is tamper-evident and does
  not depend on anyone's discipline;
- **`kit_version`** is the human-readable label. It must change together with
  the bytes, and the registry verifies this rule.

The `tests/golden/provider-kit/identity-ledger.json` registry lists released
`kit_version` + aggregate pairs. A test requires the current render's pair to
be present in it and requires that no version and no aggregate be repeated.

## Consequences

Changing machine bytes without bumping the version fails: the new pair
conflicts with the recorded one. This is exactly the error that already
occurred.

The registry **does not** prevent rewriting an existing entry instead of adding
a new one. This is a visible line in the diff and belongs in review: the test
cannot distinguish an intentional correction from a concealed error, and
pretending that it can would be worse than stating that here.

Provenance—which commit produced the kit—is intentionally excluded from the
generated file. The generator would have to read Git, the value would change
with every commit, and the generated artifact would cease to be reproducible
from its inputs. Provenance belongs to the release that publishes the kit, not
to the bytes it publishes.

The five providers must pin the exact identity and verify their copy against
it. This work belongs in their repositories and has been assigned there as
tasks; until it is done, conformance remains a claim rather than proof.

This record does not decide whether to publish the kit externally as an
immutable artifact. Publication is a separate decision; this record creates
the object that can be published.
