---
description: "Immutable estate release record binding one consumer cut to exact provider evidence."
last_verified: "2026-09-08"
---

# Estate release

`ai-stp-estate-release/2` is one immutable record of a consumer cut and the
provider identities it was measured against. It is not a GitHub Release, not a
PyPI upload, and not a workflow artifact. Those may *carry* a record; they are
not the record. The complete-verdict rule is `ADR-0172`; historical /1 records retain ADR-0160. Requirements live in
`SPEC-061`.

The public consumer identity is one Python distribution, `ai-stp-cli`
(`ADR-0146`). Historical six-package cuts remain valid inputs for old records;
a new complete verdict names that one distribution and refuses a silent
six-package claim that the candidate did not build.

## Identity

The document is a closed JSON object. Required root fields:

- `schema_id` — `ai-stp-estate-release/2` for new records; /1 is a legacy reader;
- `record_id` — stable identifier of this record, not of the product;
- `created_at` — UTC timestamp;
- `consumer` — repository, exact 40-character commit, optional tag and
  release URL;
- `distributions` — each published filename with an exact `sha256:` digest;
- `providers` — seven OpenNetwork setup-systems, each with repository, exact
  commit, exact tag, native artifacts and optional wheels;
- `evidence` — matrix rows. A row may name `provider` (the attested
  repository identity). Consumer slices leave it empty; the `launch` slice
  requires it to fill a cell;
- `not_verified_platforms` — for /2, `linux/arm64`, `macos/x86_64`,
  `windows/arm64`; these are outside required beta qualification;
- `known_limitations` — strings, may be empty. They explain a cell; they
  do not fill one and they do not change the recomputed verdict;
- `verdict` — `complete`, `incomplete`, or `failed`.

Optional identities (`web`, `provider_kit`, `checksums_digest`, `sbom_digest`,
`record_provenance`) are recorded when present. Their absence does not invent
values.

Every digest is `sha256:` plus 64 lowercase hex characters. `latest`, `main`,
`master`, and `head` are refused as tags, commits, URLs, and image names.

## Verdict

The stored `verdict` is a claim. Validation recomputes it:

- `failed` when a required-platform evidence row is `failed` (/1 retains its
  historical any-row failure rule);
- `incomplete` when a required row is missing, `skipped`, or `inconclusive`,
  when a row's consumer commit disagrees with `consumer.commit`, when a
  launch row's tag disagrees with that provider's recorded tag, when the
  recorded providers are not exactly the seven attested OpenNetwork
  repositories, when `software` or `launch` is absent from `required_slices`,
  or when a web-only cut claims `complete`;
- `complete` only when every required row is `passed` against those identities.

A validator that trusted the written verdict would make the field decorative.
Changing any artifact digest, swapping evidence from another SHA, or omitting a
required matrix row invalidates `complete`. A `known_limitations` string that
names an undeclared launch does not replace the cell.

Required /2 legs are Linux x86_64, Windows x86_64 and macOS arm64.
Linux arm64, Windows arm64 and macOS x86_64 are not_verified. Historical /1
records retain the six native pairs Linux/macOS/Windows × x86_64/arm64.
`software` is a consumer slice: the required legs, no provider identity.
`launch` is a provider slice: seven attested repositories × the required legs
(21 cells for /2; 42 for /1). An empty `provider` on a launch row fills nothing. Skipping or
omitting Antigravity because launch is undeclared cannot yield `complete`;
recording those cells as `failed` yields `failed`.

Required slices are named by the record's `required_slices` list; an empty
list cannot yield `complete`. A complete cut must include both `software`
and `launch`.

## Offline validation

`just estate-validate <path>` reads the document and retained metadata only.
It does not fetch GitHub, PyPI, or the host. Recomputing a digest requires the
named file to sit beside the record or under `--artifacts`.

## Building a record

`python -m release_scripts.build_estate_record` (or `just estate-record`) writes
one document from a version, exact consumer commit, SHA256SUMS, and explicit
provider `repository=tag@commit` identities. It does not fetch. The written
`verdict` is always `computed_verdict`; an empty evidence matrix, a missing
required-platform consumer slice, a missing launch cell, or a skipped launch cell
cannot become `complete`. This format does not retag a historical release.
