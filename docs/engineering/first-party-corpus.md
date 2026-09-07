---
description: "Rebuilding and publishing the first-party corpus from exact attested setup-system releases."
last_verified: "2026-09-07"
---

# First-party launch corpus

`ai_stp_contracts.first_party.versions()` owns the current inventory: complete
sealed passports, exact artifacts, stable identities, and version pins. The
catalog composition belongs to [ADR-0034](../adr/ADR-0034-first-party-launch-corpus.md)
and publication acceptance to [SPEC-021](../../specs/active/SPEC-021-anonymous-catalog-read-and-seed.md).

## Rebuild from an exact provider release

`release_scripts/build_first_party_corpus.py` reads every posture in `POSTURES`
for every requested harness in `REPOSITORIES`. `--release` is required for a
build. The existing attested provider acquisition verifies the release artifact,
source commit, and signer before running `provider-info`. The builder reads that
same source commit for the Git tree and limits each posture's path history to
that commit. A later update to `main` cannot change captured provenance.

Build into a copy of the previous corpus so identifiers and version history are
available and an interrupted capture cannot damage the working corpus:

```bash
cp -a packages/contracts/src/ai_stp_contracts/first_party/v1 /tmp/corpus-next
uv run --locked python release_scripts/build_first_party_corpus.py \
  --out /tmp/corpus-next --release <exact-provider-tag>
```

The report and `corpus-release-pins.json` record the release tag, resolved commit,
artifact digest, and attestation trust level per harness. `corpus-sources.json`
retains source paths, Git object hashes, stable identities, exact versions, and
compiler projection paths. The pin receipt is build evidence outside immutable
passports. Platform support comes from the verified provider capability declaration.

The builder uses `composition.rule_for`; an unrouted path is reported instead of
being silently relabeled. Native Codex agent roles are supported by the current
projection registry. The full report must be reviewed before importing a capture.

## Identity, versions, and provenance

A component's held identity is `(harness, kind, slug, posture)`. A setup's held
identity is `(harness, posture)`. Rebuilding preserves those identities and reports
new ones. Objects from the displaced archived estate retain their historical
identities and public versions; rebuilding does not remove or rewrite them.

`source.commit` names the last commit touching the captured posture at the pinned
release. Component `source_tree` values are Git blob/tree hashes derived from the
actual captured bytes and modes. A provider release that does not change the
payload does not by itself require a new component identity.

Published `X.Y` versions are immutable. `--bump-all` advances all held objects when
a coordinated release changes their passport representation or setup pins;
`--bump-id` advances an explicitly named object. Before publication, compare the
candidate passports with the public exact versions and refuse any same-version
change. A rebuild is not permission to overwrite an existing publication.

## Inspect the current corpus

Read the packaged inventory rather than retaining a hand-copied count:

```bash
uv run --locked python -c "from collections import Counter
from ai_stp_contracts.first_party import versions
items = versions()
print(dict(Counter(v.kind for v in items)))
for v in items: print(v.kind, v.passport.stable_id, v.passport.version, v.passport_digest)"
```

`just corpus-drift` compares captured content with current provider `main` and
reports the exact heads it read. It does not rebuild or refuse ordinary content
lag. Release reproduction uses the explicit tag above; a drift check against a
later `main` answers a different question.

Contract tests reconstruct source Git hashes from packaged bytes, check compiler
placements, validate each closed native projection, and verify exact setup pins.
An unchanged passport digest proves immutability; source comparison proves
whether the corpus still represents the desired provider release.

## Publication

`load_first_party_seed()` is gated dev/test bootstrap. It validates the canonical
corpus and is never the production publication path.
`apps/cli/tools/first_party_launch_publication.py` uses normal authenticated plans,
artifact binding, confirmation, and publication. It resumes by corpus digest and
idempotency keys. Components precede setups; every setup's exact component pins
must exist before confirmation.

Closeout reads the public components and setups through the catalog and their
artifacts through normal storage. Compare stable IDs, versions, passport and
adaptation digests, artifact bytes, and setup provenance with the packaged corpus.
Author verification, target assessment, and technical support remain independent;
a release receipt is not a target assessment or a substitute for account login.
