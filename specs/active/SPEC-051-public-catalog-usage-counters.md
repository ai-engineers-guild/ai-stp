---
description: "SPEC-051: Private events and public catalog view and download counters."
last_verified: "2026-08-16"
---

# SPEC-051: Public catalog usage counters

## Purpose

Show comparable aggregates on the card and detail views for views of the public detail page and successful artifact downloads, without creating user history or presenting a download as a successful installation.

## Scope

Only an authorized public detail read and the server's completed delivery of artifact bytes are counted. `CLI install success`, harness telemetry, account analytics, unique users, and public raw events are out of scope. The exact contract is owned by `docs/contracts/catalog-usage-metrics.md`.

## Terms

- **Detail view** — a successful public response from the detail page.
- **Artifact download** — successful server delivery of artifact bytes; not
  install success.
- **Keyed digest** — a short-lived HMAC attribute for a window; raw IP, user-agent,
  account, and device are not stored.

Wire semantics are owned by `docs/contracts/catalog-usage-metrics.md`;
the architectural decision is `ADR-0097`.

## Requirements

- `REQ-5101`: The public projection contains `detail_views_count` and
  `artifact_downloads_count`; card, detail, and API use the same server aggregate.
- `REQ-5102`: A view is counted after a successful public detail response. A download
  is counted after successful delivery of bytes; an attempt, redirect, preflight, error,
  or metadata request does not increment the counter.
- `REQ-5103`: Download means delivery of bytes, differs from install success, and does
  not change install eligibility, verification, or trust.
- `REQ-5104`: Anti-abuse uses a short-lived keyed digest derived from a minimal
  network attribute, object/action, and window. Raw IP, user-agent, account/device
  identity, and a stable cross-window identifier are not stored; the secret is rotated.
- `REQ-5105`: Dedup rows are deleted according to a short documented retention period;
  aggregates do not allow reconstruction of a visitor, and event rows are not public.
- `REQ-5106`: Necessary server-side fraud prevention does not require analytics consent
  and does not load a tracker; optional analytics remains consent-gated.
- `REQ-5107`: A feature flag disables recording and display of both counters; the disabled
  state preserves the existing surfaces without false zeros.
- `REQ-5108`: Concurrent repeats within the same window produce one atomic increment;
  different windows and actions are independent.
- `REQ-5109`: The compact responsive UI shows two labeled values; RU/EN,
  screen-reader labels, and card/detail parity are covered by tests.

## States and errors

When the flag is disabled, the `usage_metrics` field remains empty; an absent value
is not equal to zero. An attempt, redirect, preflight request, error, or
metadata-only request does not increment the download counter. Repeats within the
same window produce one atomic increment.

## Security and privacy

Anti-abuse protection does not store the source address, client string, account,
device, or a stable cross-window identifier. Deduplication rows have a short
lifetime. Necessary server-side protection does not require analytics consent
and does not load an external tracker.

## Compatibility and migration

The fields are additive and nullable when the feature is disabled. Rollback disables
recording/display and preserves aggregates until a separate managed deletion.

## Acceptance criteria

| Requirement | Executable evidence |
|---|---|
| `REQ-5101` | API and component tests confirm card/detail/API parity for the same aggregate. |
| `REQ-5102` | Tests confirm an increment only after a successful detail response and delivery of bytes. |
| `REQ-5103` | Tests confirm that download differs from install success and that eligibility remains unchanged. |
| `REQ-5104` | Privacy tests find no raw identifiers or stable cross-window identifier. |
| `REQ-5105` | Tests confirm short retention for dedup rows and the absence of public event rows. |
| `REQ-5106` | Tests confirm no-consent and no-tracker behavior for necessary anti-abuse protection. |
| `REQ-5107` | Feature-profile tests confirm the absence of recording and fields when disabled. |
| `REQ-5108` | A PostgreSQL concurrency test confirms one increment per window. |
| `REQ-5109` | RU/EN component tests confirm a compact accessible UI. |
