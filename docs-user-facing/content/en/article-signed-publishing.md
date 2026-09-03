---
type: article
slug: signed-publishing
locale: en
title: What a device signature actually proves
description: "An Ed25519 proof binds one active device to one publication plan. It does not make the bytes safe."
published_at: 2026-08-15
tags: [trust, publishing, signature]
draft: false
---

A publication signature is not a decorative string on a catalog card. It is an Ed25519 proof produced by an active device and bound to one exact publication record. The private key never leaves the device. The server never receives it. What the server can check is the public key, the device’s revocation state, and whether the signed coordinates still match the plan.

If you treat that proof as a safety scan, you will install objects the signature never claimed were harmless. If you treat it as optional ceremony, you will accept a plan that no device belonging to the account actually confirmed.

![A device signature binding every publication coordinate](/content/illustrations/signed-publication.svg)

## The signed coordinates

The confirmation record covers the artifact digest, object identity, version, policy version, tool and harness versions where the attestation requires them, account, device and time. Changing any coordinate produces a different message and invalidates the signature.

That is the point of canonicalization. A valid signature for version `1.2` cannot be replayed onto `1.3`. A signature over one digest cannot be attached to another archive that happens to share a name. A truncated payload, a copied proof from another account, or a record with a field quietly dropped is a different message. The verifier does not “fill in the obvious bits.”

Credential-dependent checks — the ones that need the author’s own tokens or a live harness — run only on that device. The signed attestation names the test identifiers and the result. It does not include secret values, issuing URLs, or environment bodies. Revoking the device immediately blocks new confirmations. Old signatures remain what they were: proofs that that device, while active, attested those coordinates.

`attestation sign` writes a new owner-only file. It does not overwrite an existing one. `publication plan` accepts such files explicitly, checks identity, version, digests, account, device, duplicates and the signature before any HTTP call, and then sends only the public wire fields. Source bytes, local paths and session tokens stay off the passport.

## What the server checks

Three questions, in order:

1. The device belongs to the publishing account and remains active. A revoked device is a permanent rejection, not a prompt to retry with the same key.
2. The public key verifies the complete canonical confirmation record. Partial records fail. Altered records fail.
3. The record coordinates match the server-side publication plan exactly: digest, identity, version, policy. A signature that is valid in the abstract and bound to a different plan is still a mismatch.

The server also recalculates the artifact hash and the non-executable structure rules. That recalculation is `platform_digest_verified` and `platform_structure_verified`. It is not the same evidence as `author_attested`. Five proof sources exist and they are not collapsed into one field called `verified`: author attestation, platform digest, platform structure, provider installation test, and a separate runtime test. Each is shown with its source and its limits.

This prevents a valid signature for one version from being reused for another. It also makes a copied, truncated or substituted proof useless. Idempotent retries of the same confirm return the original plan result; they do not mint a second signature.

## What it does not prove

A device signature proves authorization and integrity of intent: this account, from this still-active device, confirmed this exact plan over these bytes. It does not prove that the content is safe to run.

Safety scans remain separate evidence. `component_verified` remains a policy decision over current mandatory checks, not a side effect of a signature. `author_verified` remains a namespace decision, not a device proof. A signed publication from an unverified author is still `experimental` until consent says otherwise. A signed publication from a verified author is still unverified as a component until the checks pass.

The signature does not prove that the author’s local tools were honest, that a credential-dependent test exercised the interesting path, or that a later policy version would still accept the same bytes. Expired evidence drops `component_verified` without touching the signature file.

Readers should look especially carefully at `mcp`, `hook` and `plugin`. Those kinds widen permissions or change the target. A signature tells you who intended to publish them. It does not tell you what they will do after the provider writes native state.

See also: [Trust and safety](https://ai-stp.aiguild.space/en/docs/trust-and-safety) and [Security checks](https://ai-stp.aiguild.space/en/docs/security-checks) in the help center.
