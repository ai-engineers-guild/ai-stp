---
type: article
slug: immutable-artifacts
locale: en
title: Publish bytes, not promises
description: "A published X.Y is one digest of one archive. Catalog copy cannot outrun the bytes it names."
published_at: 2026-08-14
tags: [artifact, digest, publishing]
draft: false
---

Catalog copy can describe an artifact. It cannot replace it. ai_stp accepts the archive bytes first, verifies them, stores them under an immutable key, and only then lets a publication become public. A row that names a digest the store does not hold is not a release. A filename is not a version. A branch, a tag and `latest` are not provenance.

The rule is small and strict: one published `X.Y` is one payload. If the bytes change, the number changes. If the number is taken, another archive cannot claim it.

![Archive bytes moving through verification into immutable storage](/content/illustrations/immutable-artifact.svg)

## Upload is a verification step

The server reads the archive within a strict size limit. It rejects unsafe structure: zip-slip paths, undeclared files, secret-like names, unmanaged binaries, and a component root that is actually the whole project repository. It calculates the digest and compares it with the publication plan. Only matching bytes enter immutable object storage.

The storage key is content-addressed and opaque. Knowing the key is not authorization to read the bytes. Consumers go through the artifact route. Presigned URLs are not the public contract.

Re-writing the same bytes under the same key is idempotent. Writing different bytes under an existing key is a typed conflict. That is how two catalog rows — two versions, or two objects that happen to share a payload — can point at one key without turning the store into a mutable bucket.

A public version also requires a full passport, a public GitHub repository at an exact commit and subpath, a licence, non-empty tags from the closed vocabulary, and a declared harness. The source of the bytes is the commit, not the branch name the author happens to have checked out today.

## Confirmation depends on storage

Confirmation checks that the planned object still exists and has the expected size and digest. A database row alone is insufficient. Public catalog fields cannot outrun the bytes they promise.

The publication plan is itself immutable: identity, version, policy, digest, expiry. Confirming it is a separate operator action bound to that plan hash. An expired or mutated plan is not patched. The author builds a new plan from the same released version, or releases a new `X.Y` if the bytes changed.

For a setup the unit of confirmation is a set, not a lonely setup plan. Every pinned component that is not yet public is planned first. The setup is last. Confirming a setup before its pins is a defect, not a shortcut. An already public participant is listed and not replanned. A participant rejection stops the set in a resumable partial state: published objects stay published.

Credential-dependent checks never send secret values to the server. They run on the author’s device and produce a signed attestation bound to the digest. The server still recalculates the hash and the non-executable structure rules itself. An author’s report does not replace that recalculation.

## One X.Y, one payload

Once a version is published, another archive cannot claim the same `X.Y` identity. Consumers download the exact verified bytes and compare the returned digest without trusting a mutable filename or a description field.

Lifecycle state does not rewrite bytes. `deprecated` is the author’s statement about the future of their own object: the version remains readable and the payload remains reachable, because every allowed pin would break if the bytes disappeared. `blocked` and `hidden` stop new installations. They still do not mutate the archive. Historical validation snapshots stay historical.

A concurrent offline release of the same number on two devices does not move a published number. The first revision the server accepts keeps `X.Y`. The losing unpublished version is reissued under the next available minor with the same content and a new passport. Published identity is not a race you can win by pushing harder.

Forking creates a new identity. Publishing a clone of someone else’s object under a new namespace, with unchanged bytes, is refused. A derived public object needs a substantive change, a new version, and redistribution rights that are actually known. Unknown rights fail closed.

## What operators should pin

Pin the digest and the `X.Y` together. Read the inventory before confirm. Treat cache as cache: if the CLI answered from a last-known copy, it will say when the platform last confirmed those bytes. Do not infer freshness from a version string that looks recent.

See also: [Publishing](https://ai-stp.aiguild.space/en/docs/publishing) in the help center.
