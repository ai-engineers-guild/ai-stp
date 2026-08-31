---
description: "Canonical HarnessBundle ZIP container with separate logical and byte-level identities."
last_verified: "2026-08-09"
---

# ADR-0049: Canonical HarnessBundle Container

Status: accepted.

## Context

The contract already required the builder to produce identical bytes and a structure
containing `bundle.json`, the setup passport, two reports, files, and attestations,
while the provider protocol declared the `ai-stp-bundle/1` format. The implementation,
however, stored only the hashes and sizes of source files. It discarded their content,
did not include the passport or separate reports in the package, and the cross-platform
oracle compared only the JSON manifest. Such a result cannot be passed to the provider
and does not prove `REQ-607` and `REQ-625`.

A directory without a container has no single byte sequence. An ordinary ZIP or tar
created with host settings carries timestamps, ordering, compression, and OS metadata,
so the same tree can produce different bytes on Linux and macOS.

## Decision

`ai-stp-bundle/1` is an uncompressed ZIP container. Member order is fixed:

```text
bundle.json
setup-passport.json
composition-report.json
conversion-report.json
files/
files/<managed path>...
attestations/
```

Managed files follow the manifest's canonical order. For every ZIP member, the date
is fixed to `1980-01-01T00:00:00`, the creator is Unix, extra/comment fields are empty,
and the mode is fixed; JSON content is serialized under RFC 8785. No compression is
used, so the compressor version does not affect the result. `files/` and
`attestations/` are present even when empty.

The package has two identities:

- `bundle_digest` — a domain-separated hash of canonical `bundle.json` without the
  `bundle_digest` field itself; it binds the passport, reports, and file manifest
  without self-reference;
- `artifact_digest` — the ordinary SHA-256 of the exact ZIP bytes received by the
  provider.

`bundle.json` contains `bundle_digest`. The consumer returns both identities and the
container size. The provider first validates the `artifact_digest` of the exact bytes
passed to it, then safely parses the container and independently recomputes the
logical identity and every member. A match of one identity does not replace the other.

The passport comes from a confirmed `SetupVersion`, not from a project ID or proposal
snapshot. An unconfirmed proposal has no package: without a `SetupVersion`, there is
no normative installation identity under `ADR-0012` and `ADR-0027`.

The size limit applies to the completed container, including JSON, the ZIP directory,
and service directories. Exceeding it blocks the entire package; no partial archive
is returned.

## Compatibility

Old local `select bundle` responses containing only metadata are not published
artifacts and are not migrated. A provider release must explicitly declare
`ai-stp-bundle/1` and pass the literal golden oracle. Any change to ordering, ZIP
metadata, required-member names, or the identity algorithm creates a new format
rather than silently extending v1.

## Consequences

The builder produces actual portable bytes and can prove a change in content,
passport, report, or container. The cost is holding the complete package in memory
during the build stage; this is bounded by the current 64 MiB limit. Binding these
bytes to provider plan/apply is a separate subsequent change to the consumer lifecycle
and cannot again be replaced by a plan digest.

## Reconsideration Conditions

The decision will be reconsidered if streaming packages larger than the current limit
are required, or if a standard signed container with the same deterministic and safe
properties emerges.
