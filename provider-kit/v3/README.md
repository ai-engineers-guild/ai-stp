# Public provider conformance kit v3

This directory is the generated, portable contract for provider protocol v3.
A public provider can validate its implementation against these JSON files without
access to the private `ai_stp` or authoring repositories and without depending on
them at runtime.

- `manifest.json` fixes the commands, operations, native vocabularies, provenance,
  and network phases.
- `provider-info.schema.json` is the closed JSON Schema for the `provider-info`
  response.
- `status-response.schema.json` is the closed JSON Schema for the `status` response.
- `conformance-cases.json` lists the required fail-closed classes.
- `SHA256SUMS` binds the exact bytes of the other artifacts.
- `KIT-IDENTITY.json` names exactly one kit revision: an aggregate digest plus
  `kit_version`. Pin the aggregate because it cannot be forged; `kit_version` is
  a readable label, and version `0.1.0` is ambiguous and cannot be a reference
  (`ADR-0085`).

The aggregate is taken from **the `SHA256SUMS` file as stored**, byte for byte,
without normalization: `sha256sum SHA256SUMS` gives exactly `aggregate_digest`
without the `sha256:` prefix. The previous wording said "canonical bytes"; in
this repository, "canonical" means JSON canonicalization, so a reader that
applied it to `SHA256SUMS` would calculate a different value. This is verified
by the kit reader, not by the author.

The tree you are in determines what can be run.

`release_scripts/provider_kit.py` lives in the `ai_stp` repository and generates
these files; the same command validates them there with `--check`. A kit reader
does not have this path—the earlier paragraph promises exactly that—and the
command is named here as the file origin, not as an action.

The kit reader owns a different check, which requires nothing external:
`SHA256SUMS` binds the exact bytes of the other artifacts, and `KIT-IDENTITY.json`
names the SHA-256 of the `SHA256SUMS` file itself, without normalization. The kit
carries these files for that purpose.

Do not edit generated JSON by hand.
