---
type: article
slug: signed-publishing
locale: en
title: What an author signature actually proves
description: Follow an ai_stp publication attestation from the active device key to the exact object coordinates it protects.
published_at: 2026-08-15
tags: [trust, publishing, signature]
draft: false
---

A publication signature is not a decorative string. It is an Ed25519 proof produced by an active device and bound to one exact publication record.

![A device signature binding every publication coordinate](/content/illustrations/signed-publication.svg)

## The signed coordinates

The confirmation record covers the artifact digest, object identity, version, policy and device identity. Changing any coordinate produces a different message and invalidates the signature.

## What the server checks

1. The device belongs to the publishing account and remains active.
2. The public key verifies the complete canonical confirmation record.
3. The record coordinates match the server-side publication plan exactly.

This prevents a valid signature for one version from being replayed for another. It also makes a copied, truncated or substituted proof useless.

## What it does not prove

An author signature proves authorization and integrity of intent. Safety scans and component verification remain separate evidence, so readers can see precisely which claim each signal supports.
