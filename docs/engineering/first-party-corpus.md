---
description: "Verifiable inventory of the actual bytes and passports in the first-party launch corpus."
last_verified: "2026-09-05"
---

# First-party launch corpus

The normative composition of the catalog belongs to
[ADR-0034](../adr/ADR-0034-first-party-launch-corpus.md), and the release threshold —
[release-evidence.md](release-evidence.md). Here is stored a verifiable
inventory of already prepared items, without changing the required composition.

## How the corpus is built

`release_scripts/build_first_party_corpus.py`. Until 2026-08-29 the builder **did not exist**: manifests and built-in artifacts were assembled outside of this repository. That is why the corpus continued to reference the estate, transferred to a personal account and archived on 2026-08-25 — there was nothing to rebuild it from here, so no one noticed.

The collector reads the `setups/nddev-builder/` tree of each setup system on its current `main`, lays out each path according to **the same projection table used by the compiler** (`composition.rule_for`), packs the result, and records its own tree and blob SHA of git as provenance.

There are two things he deliberately does not do. He does not invent a component for a path that is not routed by any rule: the only such path is codex `agents/nddev-builder.toml`, and this is a model confirmation, not an omission (the role of codex is a table `agents.<name>` in the configuration file plus the layer it points to, meaning the configuration satellite, not a component of any kind). And he does not reuse stable identifiers: these are objects from another repository, and the old IDs would imply that the published version came from a source from which it did not come.

## What has been replaced and at what cost

The previous corpus contained 126 objects, of which **120 were called archival repositories** under a personal account. It could not be corrected by editing: `source` and commit are part of the content-addressable passport, and the published `X.Y` is immutable (`REQ-2606`). The only honest correction is other objects with new identifiers.

The price is given as a number, not a paragraph: **126 items with provenance in the archive become 40 with a live source.** 60 role components came from `rldyour-claudecode` and `rldyour-codex` — both archived under the same personal account — and there is no live repository from which they can be reconstructed. This, and not a model decision, is the reason why the role corpus was removed.

Old objects remain published and immutable. Withdrawal is a decision not to sow new ones, not the removal of those already released.

## Composition, measured by assembly

Seven harnesses, 40 objects: 33 components and 7 setups, all versions `1.0`.

| Harness | Components | Types |
|---|---:|---|
| claude-code | 7 | agent 1, command 3, instruction 1, setting 1, skill 1 |
| opencode | 7 | agent 1, command 3, instruction 1, setting 1, skill 1 |
| pi | 6 | command 3, instruction 1, setting 1, skill 1 |
| codex | 5 | command 3, instruction 1, setting 1 |
| grok-build | 4 | agent 1, instruction 1, setting 1, skill 1 |
| antigravity | 2 | plugin 1, setting 1 |
| cursor | 2 | plugin 1, setting 1 |

There are **intentionally no** commits, blob-SHA, or passport digest here. Their live owner is — `ai_stp_contracts.first_party.versions()` and `corpus-sources.json` next to the artifacts; the table in the document was their copy and during one session on 2026-08-29 it became outdated twice. The current values are printed by:

```bash
uv run python -c "from ai_stp_contracts.first_party import versions
for v in versions(): print(v.kind, v.passport.stable_id, v.passport_digest)"
```

Check whether the body has diverged from the providers — by content, not by HEAD:

```bash
just corpus-drift
```

`--drift` indicates how many components and setups have actually shifted, and does not collect anything. The lag on the component is a published state, not a failure: it will be carried by the next version.

The recipe was created on 2026-08-29, and before it, there was a full script call with `--out`. The difference is not cosmetic: the command that needs to be executed manually runs only when it is remembered — and this module is tied to the digest and is not displayed locally, so aside from this command, there is nothing to report as 'content is lagging.' The very first run after the recipe was created showed that it was lagging: ten component files across all seven harnesses and two setups, `codex` and `cursor`; twenty-three objects had not changed (`#461`).

Forty objects of the corpus are the class that is protected from modification and immune to any discrepancy: `passport_digest` refuses silent edits and says nothing about whether the content matches the source.

## Provenance names the commit that produced the bytes

`source.commit` — the last commit that touched `setups/nddev-builder`, not the repository HEAD. Until 2026-08-29, this was the HEAD, and since `source` is included in the content-addressable passport, **all seven setups changed the digest with any release of any provider** — including five whose payload did not move. Measured that day: three provider releases shifted two components out of thirty-three and no setups, while all seven passports differed.

The published `X.Y` is immutable, which is why this made the planted corpus 'obsolete' minutes after planting—forever. This appearance, not the content, twice postponed the reseeding of the catalog.

## Identity Undergoes Reassembly

`new_id` generates a new ULID with each call, so until 2026-08-29 every rebuild replaced all forty identities. With the immutable `X.Y` this meant that the seeded corpus had no path from `1.0` to `1.1`: the next provider change could only be published as forty **new** objects, orphaning the seeded set.

Logical identity of a component is `(harness, kind, slug)`; the logical identity of a setup is its harness.
The rebuild reuses the identifier that the previous build already issued to this object, and prints `new_identities` for paths that were not there before.
Identifiers of the removed estate are still not reused: those objects came from another repository.

The platform set of each setup — three OSes and two architectures — is **queried from the released provider binary** during the build, rather than recorded as a literal. Until 2026-08-29, `["linux"]` and `["x86_64"]` were placed here, and each published setup underestimated its own support for all seven at once. There is intentionally no spare value in the builder: the literal substituted when the query could not be made is what is returned as a copy.

Exact subpaths, Git object SHA, stable IDs, and the **projection path** of each component belong to `first_party/v1/corpus-sources.json`. The contract test restores each Git blob or tree SHA directly from the embedded bytes and file modes, and separately checks that the declared `managed_path` is exactly what the compiler rule will produce.

The third copy of the projection table no longer exists. It was located in `ai_stp_contracts.first_party` until 2026-08-29 and by that time it was already diverging from `PROVIDER_RULES`: the cursor plugin was `plugins/local` in one and `plugins` in the other. A body whose managed path does not match what the compiler will write is set as "verified" and invisible — exactly what happened with 61 codex skills.

`safe` and `full-auto` remain execution profiles of one setup graph, not two content setups. Switching the profile does not change the component, setup artifact, or graph according to `SPEC-008` `REQ-835`; both profiles are checked by the provider lifecycle separately from the content body.

The imported data owner is `ai_stp_contracts.first_party`. It supplies exact bytes of artifacts, full sealed passports, and their hashes in a single set and is used by both parties instead of independent copies. `catalog_identity(harness, posture)` is the compact catalog projection of those identities (`ADR-0156`): setup id, version, passport digest, and per-component stable id, version, passport digest, and adaptation id. It does not mint identifiers.

## Unclosed integration

The server is seeding **not this chassis**: `load_first_party_seed` distributes the manually written Sprint-1 set, while `ai_stp_contracts.first_party.CORPUS` is not imported by anything into `apps/` — `#374` owns this. As long as this is the case, `#162` remains open: a match between CLI and web must be proven on a single published version, not inferred from a local fixture.
