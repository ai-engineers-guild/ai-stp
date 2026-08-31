---
description: "Runbook: provider update."
last_verified: "2026-08-28"
---

# Provider update

## Preparing a signed release

After receiving a byte-identical candidate from the closed release harness, the publisher
key is created and stored only outside the checkout. The command prints the public key and
deterministic `key_id`, which are then pinned separately in consumer policy:

```bash
python apps/cli/tools/provider_release.py keygen \
  --private-key /secure/ai-stp/provider-release-ed25519.pem
```

The manifest signs the exact executable, commit, URL, platform profile, and
monotonic sequence. For the current release profile, specify only the actually
proven `linux` and `x86_64`; portable code paths are not macOS evidence:

`--publisher` is required and has no default. Previously, the tool substituted
a publisher that the distributed `provider-policy.toml` no longer
trusts—in other words, it signed releases on behalf of an organization from which the estate
had migrated.

```bash
python apps/cli/tools/provider_release.py sign \
  --private-key /secure/ai-stp/provider-release-ed25519.pem \
  --provider-id claude-setup-system \
  --provider-version 0.0.16 \
  --publisher NDDev-OpenNetwork \
  --repository github.com/NDDev-OpenNetwork/claude-setup-system \
  --commit <exact-commit> \
  --license AGPL-3.0-or-later \
  --artifact /secure/candidates/claude-setup-system-0.0.16 \
  --artifact-url https://github.com/NDDev-OpenNetwork/claude-setup-system/releases/download/0.0.16/claude-setup-system-0.0.16 \
  --entry-point claude-setup-system-0.0.16 \
  --protocol-version 3 \
  --sequence 1 \
  --supported-os linux \
  --supported-arch x86_64 \
  --output /secure/candidates/claude-setup-system-0.0.16.manifest.json
```

`--provider-id` is what the provider calls itself in `provider-info`, and it is
`<name>-setup-system`, not the former repository name. Verified against released
`0.0.16` versions: `claude-setup-system`, `codex-setup-system`, `pi-setup-system`.

Before publication, `verify` rereads the exact artifact bytes and applies
the same consumer trust contract. The private key, candidate bytes, and
intermediate manifests are not committed; only the public key and exact digests
of published artifacts enter the repository after immutable publication.

## Release preparation

1. Record the public repository, commit, protocol version, and related issue.
2. Run the public checks and the closed authoring-environment barrier.
3. Build a reproducible artifact and manifest with its hash, size, and sequence.
4. Sign the release with a permitted key or publisher under the current trust policy.
5. Obtain Linux x86_64 evidence for the selected release line. macOS evidence is
   required only before macOS is added to the support matrix in the future under `ADR-0062`.
6. For protocol v2, run the capability probe on each OS. `enforced` is accepted
   only with launcher identity, SHA/version, and positive control of
   DNS-UDP/IPv4/IPv6; `unavailable` blocks the local phase before the provider runs.

## Promotion

1. Separately promote the pinned version in the closed authoring environment.
2. Update the consumer manifest in `ai_stp` in a separate PR.
3. Verify the source, signature, hash, rollback protection, platform, and `provider-info`.
4. Install the new version beside the old one and run diagnostics and contract checks.
5. Atomically switch the current pointer. User targets are not updated automatically.

## Post-switch verification

1. Fetch `provider-info` again and verify the actions and version.
2. Run a safe plan against a test target, then state and recovery.
3. Record the exact artifact, commands, results, and skipped platforms.
4. Record `network_requirement`, the actual `network_enforcement`, and evidence for
   every completed phase. Linux/Bubblewrap evidence does not prove macOS; without
   separate real-host evidence, macOS remains `not_verified`.

## Rollback

On error, point back to the previous installed, verified version. Do not use `latest` or download a new artifact during rollback. If the release has been revoked, block new installations and publish the list of affected versions and recovery instructions.
