---
type: article
slug: immutable-artifacts
locale: en
title: Publish bytes, not promises
description: Why ai_stp verifies an archive before confirmation and keeps one immutable payload for every X.Y version.
published_at: 2026-08-14
tags: [artifact, digest, publishing]
draft: false
---

Metadata can describe an artifact, but it cannot replace it. ai_stp accepts the archive bytes first, verifies them, and only then allows the publication to become public.

![Archive bytes moving through verification into immutable storage](/content/illustrations/immutable-artifact.svg)

## Upload is a verification step

The server reads the archive within a strict size limit, rejects unsafe structure, calculates its digest and compares it with the publication plan. Only matching bytes enter immutable object storage.

## Confirmation depends on storage

Confirmation checks that the planned object still exists and has the expected size and digest. A database row alone is insufficient: public metadata cannot outrun the bytes it promises.

## One X.Y, one payload

Once a version is published, another archive cannot claim the same X.Y identity. Consumers download the exact verified bytes and can compare the returned digest without trusting a mutable filename or description.
