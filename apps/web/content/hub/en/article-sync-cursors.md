---
type: article
slug: sync-cursors
locale: en
title: A cursor is a checkpoint, not a page number
description: Understand how the private sync ledger advances without replaying the last page or restarting from the beginning.
published_at: 2026-08-13
tags: [sync, cursor, reliability]
draft: false
---

Private sync is an ordered ledger. Its cursor identifies the last record already delivered, so a client can resume after interruption without guessing an offset.

![A sync checkpoint advancing past the final non-empty page](/content/illustrations/sync-cursor.svg)

## Advance on every non-empty page

Even the final non-empty response carries the cursor of its last record. The client persists that value only after applying the page successfully.

## Ask once more

A request after the saved cursor returns an empty page. That empty response confirms the current end of the ledger; it does not send the client back to its first record.

## Keep catalog semantics separate

Public catalog pagination has a different reading model and may use `null` at its final page. Treating both cursors as one generic pagination convention would hide their distinct recovery guarantees.
