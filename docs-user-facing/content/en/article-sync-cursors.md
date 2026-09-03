---
type: article
slug: sync-cursors
locale: en
title: A cursor is a checkpoint, not a page number
description: "Private sync resumes from the last applied record. Catalog pagination ends at null. Do not treat them as one convention."
published_at: 2026-08-13
tags: [sync, cursor, reliability]
draft: false
---

Private sync is an ordered ledger for one account. Its cursor identifies the last record already delivered, so a client can resume after interruption without guessing an offset. Catalog listing is a different reading model: it pages a public set and is allowed to end at `null`. Treating both as “pagination” hides the recovery guarantee that `sync pull` actually needs.

The operator verb is `sync pull`. This page is not a tutorial. The help center owns the command surface. What belongs here is why the cursor means resume, and why copying a catalog client onto the private stream will replay history or skip it.

![A sync checkpoint advancing past the final non-empty page](/content/illustrations/sync-cursor.svg)

## Advance on every non-empty page

A pull starts from an opaque, account-bound cursor over the server outbox. The server stores no per-client cursor row. The client is the checkpoint. The cursor is not an offset, not an entity id, and not authorization over another account. Forged or foreign cursors are rejected.

A non-empty page always returns the cursor of the last sequence it served, including the last non-empty page, even when no further rows exist in that read. The client persists that value only after applying the page successfully. Persist-then-apply is how duplicates appear. Apply-then-crash-without-persist is how the same page comes back, which is safe because receipts are idempotent.

The batch is bounded. Partial success is not reported as success. The journal and the cursor stay where they were until the page is applied atomically. `sync pull` is an apply with an explicit confirmation flag, not a background drain that the CLI pretends finished.

## Ask once more

A request after the saved cursor returns an empty page. That empty response confirms the current end of the ledger. It does not send the client back to its first record. It may repeat the input cursor, or return `null` only when the client had never supplied one. Neither form means “there will never be another event.” It means “you are caught up as of this read.”

A later event appears on the next pull from the saved cursor, by itself, without a full replay. That is the whole point of a checkpoint. Restarting from zero after every empty page would re-apply history the device already has. Skipping the empty confirmation would leave the client unsure whether the last non-empty page was complete.

Timeouts after acceptance retry with the same idempotency key. The receipt comes back; a second revision does not. A revoked device is rejected before any revision, head, outbox or receipt is written. Conflict is explicit: diverging heads return enough ancestry to merge, apply no last-write-wins rule, and do not change the server head. Merge is a later, explicit revision with two parents. The server does not merge fields for you, and it does not touch the installed harness target.

The MVP stream is narrow on purpose. It carries the cross-device developer passport, a permitted device summary, private component and setup revisions, scoped consent, and tombstones. It does not carry artifact bytes, backups, a full device or project passport, absolute paths, secrets or environment values. A cursor cannot widen that allowlist.

## Keep catalog semantics separate

Public catalog pagination has a different job. It enumerates a filtered public set with an opaque cursor the client returns verbatim. `next_cursor` is always present and is `null` on the last page. Page size defaults to twenty and clamps at one hundred. A cursor belongs to one view: components and setups are separate resources, and a cursor issued with one filter, sort or deprecation flag is invalid for another.

That `null` is a correct end-of-set marker for a public list. It is a wrong end-of-stream marker for a private ledger that will grow. If a sync client treated `null` as “start over,” it would replay. If a catalog client treated “always return the last record’s cursor, even on the last page” as “there must be another page,” it would spin.

The two guarantees are therefore opposite at the boundary:

- catalog: last page may say `null`; the set is complete for that filter;
- sync: last non-empty page still carries a cursor; an empty page means caught up, not rewind.

Operators who automate both surfaces should keep two cursor stores. Do not share one “page token” helper. Do not parse the cursor. Do not use it as an object id.

`sync preview` classifies heads without moving them. `sync push` sends one exact local head as a durable, replay-safe event. `sync pull` is the read-and-apply of one bounded page. None of those commands is catalog search.

See also: the [CLI](https://ai-stp.aiguild.space/en/docs/cli) page in the help center, which places `sync pull` on the command map.
