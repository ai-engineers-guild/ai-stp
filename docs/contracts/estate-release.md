---
description: "Immutable estate release record binding one consumer cut to exact provider evidence."
last_verified: "2026-09-04"
---

# Estate release

`ai-stp-estate-release/1` is one immutable record of a consumer cut and the
provider identities it was measured against. It is not a GitHub Release, not a
PyPI upload, and not a workflow artifact. Those may *carry* a record; they are
not the record.

The public consumer identity is one Python distribution, `ai-stp-cli`
(`ADR-0146`). Historical six-package cuts remain valid inputs for old records;
a new complete verdict names that one distribution and refuses a silent
six-package claim that the candidate did not build.

## Identity

The document is a closed JSON object. Required root fields:

- `schema_id` — exactly `ai-stp-estate-release/1`;
- `record_id` — stable identifier of this record, not of the product;
- `created_at` — UTC timestamp;
- `consumer` — repository, exact 40-character commit, optional tag and
  release URL;
- `distributions` — each published filename with an exact `sha256:` digest;
- `providers` — seven OpenNetwork setup-systems, each with repository, exact
  commit, exact tag, native artifacts and optional wheels;
- `evidence` — matrix rows;
- `known_limitations` — strings, may be empty;
- `verdict` — `complete`, `incomplete`, or `failed`.

Optional identities (`web`, `provider_kit`, `checksums_digest`, `sbom_digest`,
`record_provenance`) are recorded when present. Their absence does not invent
values.

Every digest is `sha256:` plus 64 lowercase hex characters. `latest`, `main`,
`master`, and `head` are refused as tags, commits, URLs, and image names.

## Verdict

The stored `verdict` is a claim. Validation recomputes it:

- `failed` when any required evidence row is `failed`;
- `incomplete` when a required row is missing, `skipped`, or `inconclusive`,
  when a row's consumer commit disagrees with `consumer.commit`, when a
  provider row's tag disagrees with that provider's recorded tag, or when a
  web-only cut claims `complete`;
- `complete` only when every required row is `passed` against those identities.

A validator that trusted the written verdict would make the field decorative.
Changing any artifact digest, swapping evidence from another SHA, or omitting a
required matrix row invalidates `complete`.

Required legs are the six native pairs Linux/macOS/Windows × x86_64/arm64.
Required slices are named by the record's `required_slices` list; an empty list
cannot yield `complete`.

## Offline validation

`just estate-validate <path>` reads the document and retained metadata only.
It does not fetch GitHub, PyPI, or the host. Recomputing a digest requires the
named file to sit beside the record or under `--artifacts`.

## Building a record

`python -m release_scripts.build_estate_record` (or `just estate-record`) writes
one document from a version, exact consumer commit, SHA256SUMS, and explicit
provider `repository=tag@commit` identities. It does not fetch. The written
`verdict` is always `computed_verdict`; an empty evidence matrix or a missing
six-leg slice cannot become `complete`.
