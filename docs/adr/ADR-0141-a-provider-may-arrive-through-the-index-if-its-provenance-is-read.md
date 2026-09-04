---
description: "Decision to accept a provider executable delivered as a Python distribution only when PyPI's PEP 740 provenance is verified, and to keep the level unverified until it is."
last_verified: "2026-09-04"
---

# ADR-0141: A provider may arrive through the index, if its provenance is read

Status: accepted.

## Context

Today one path delivers a provider executable. `attested_bind` names the seven
public setup-system repositories, reads the GitHub release for an exact tag,
selects the asset for the platform, checks `SHA256SUMS`, and verifies a GitHub
build attestation before anything runs. The shipped policy pins those
repositories, so a successful verification reports `verified_publisher`
(`docs/contracts/provider-release.md`).

The provider estate is packaging the same seven as Python distributions named
after their repositories, so a consumer could install one from the index
instead of fetching a release asset. The estate has begun registering trusted
publishers for them; PyPI allows three pending registrations at a time, so the
seven arrive in waves.

Nothing in this consumer forbids that today, and that is the problem worth
stating precisely. Planning and applying do not read GitHub: they take
`--provider-manifest`, and the manifest binds the executable by digest. A wheel
that carries the native binary as package data is therefore already drivable,
through a manifest this consumer writes for itself. What the wheel does *not* carry is the fact that
`attested_bind` establishes — that these exact bytes were built by a named
workflow in a named repository — so every such provider would land as
`unverified` and need `--unverified-provider` on each call. That is a delivery
path more convenient than the one it imitates and weaker than it, which is the
combination this system exists to refuse.

The assumption that there is nothing to read was measured and is false. PyPI
serves PEP 740 provenance for files uploaded through trusted publishing:

```text
GET https://pypi.org/integrity/ai-stp-cli/0.0.15/ai_stp_cli-0.0.15-py3-none-any.whl/provenance
→ 200, publisher {kind: GitHub, repository: ai-engineers-guild/ai-stp,
                  workflow: publish-pypi.yml, environment: pypi-cli}
   attestation: version 1, Sigstore bundle (envelope + verification_material)
```

The same request for `ruff 0.16.5` returns 404, so the endpoint answers about
particular files rather than about every name. The triple that the existing
`build_attestations` rule compares — repository, workflow, environment — is
present, and it is inside a signed bundle rather than in mutable metadata.

## Options

**Refuse the index entirely.** Keeps one delivery path and one root of trust.
Costs the estate's chosen packaging and leaves a consumer that could already be
driven from a wheel with no rule saying whether it should be. The refusal would
also be unenforceable rather than principled: `--provider-manifest` already
accepts any executable.

**Accept the index at `unverified`.** Cheapest, and wrong in the direction that
matters. It makes the easy path the untrusted one and trains an operator to
pass `--unverified-provider` habitually, which devalues the flag everywhere
else it appears.

**Accept the index only after verifying PEP 740 provenance, and treat the
verified publisher triple exactly as the GitHub attestation triple is
treated.** Costs a verification dependency and a policy surface for index
publishers. Keeps the property that a level above `unverified` always follows
cryptographic verification of exact bytes.

## Decision

A provider executable delivered as a Python distribution is accepted, and its
trust level is decided by provenance, not by the channel:

1. The distribution carries the native binary as package data at a stable
   relative path, and nothing else is required of it. It does **not** carry a
   release manifest: this consumer materialises one, as `attested_bind` already
   does for a GitHub release, with `signing_key = "attested"` and an empty
   signature, from facts the verification itself proves. The estate has never
   published a signed manifest and is not asked to start — the three signature
   fields of that schema belong to the Ed25519 path, whose `releases` list is
   empty for these providers on purpose.
2. `entry_point` in the materialised manifest names the packaged binary.
   Console scripts are not used: a script entry is a Python shim, and the
   digest and name this consumer checks must belong to the executed bytes.
3. Before the binary runs, the consumer fetches PyPI's provenance for the exact
   file it installed and verifies the Sigstore bundle over that file's digest.
   The publisher triple — repository, workflow, environment — is matched
   against locally pinned policy, the same shape as `build_attestations`.
4. A distribution whose provenance verifies against a pinned publisher reports
   `verified_publisher`, for the same reason the GitHub path does: exact bytes
   bound to a named build, and a publisher pinned by local policy.
5. Anything less reports `unverified`. A missing provenance document, a bundle
   that does not verify, a publisher outside policy, or an index that does not
   serve provenance at all are one outcome, not four gradations.
6. **Order.** This consumer verifies provenance before the estate is advised to
   publish providers to the index, and the index is a second path rather than a
   replacement for GitHub releases. Until the verification ships, a provider
   from a wheel is `unverified` and the operator must say so explicitly on each
   call, which is the honest description of what it then is.

## Consequences

`docs/contracts/provider-release.md` gains the index as a delivery channel and
a fourth verification path beside signature, GitHub attestation, and none; the
four trust values do not change, because the point is that a new channel earns
an existing level rather than inventing one.

The trust policy grows index publisher rules alongside `build_attestations`,
carrying the same fields, so a rule is readable by whoever reads the existing
one.

Asking the estate to publish a signed manifest was considered and rejected
before it was built. It would need either this side signing every provider
release with its offline key — a step in this pipeline per release of theirs —
or their own key pinned here as a publisher, which is a trust decision made to
avoid a packaging question. Neither is necessary, because the manifest is
already something this consumer writes from what it verified.

The index verifier is `pypi-attestations`: the library's `GitHubPublisher`
policy when the module is importable, otherwise the `pypi-attestations`
executable on PATH. That is the same class of external verifier as `gh` on the
GitHub path. The consumer still owns publisher pinning, wheel inspection, and
the spawn-after-verify order. Absence of the verifier is a typed unavailability,
not `verified_publisher`.

Rollback is the absence of policy: with no index publisher rules pinned, every
wheel-delivered provider is `unverified`, which is exactly today's behaviour.

Tests: a verified provenance document against a pinned publisher raises the
level; a bundle that does not verify, a publisher outside policy, and a missing
provenance document each leave it `unverified` and are distinguished from a
successful verification by a control, so the check is shown to discriminate
rather than to pass.

## Revisit conditions

Revisit if PyPI changes or withdraws the provenance endpoint or its bundle
format; if the estate publishes providers through an index that serves no
provenance, which would force the choice between refusing that index and
lowering this bar; or if a second index becomes a delivery channel, at which
point publisher pinning needs a per-index shape rather than one list.
