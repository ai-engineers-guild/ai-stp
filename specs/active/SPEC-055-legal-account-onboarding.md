---
description: "SPEC-055: Versioned legal policies and required account onboarding."
last_verified: "2026-08-31"
---

# SPEC-055: Legal account onboarding

## Purpose

The public service records a user’s informed acceptance of the exact service
rules and personal-data consent needed to operate an account. This is an
account-activation control, not a marketing-consent system or a claim of legal
advice.

## Scope

Included: repository-backed English and Russian legal policy source, immutable
published revisions, first-login onboarding, acceptance evidence, and privacy
defaults. Excluded: advertising, behavioural analytics, a consent-management
vendor, and collection of a source IP as acceptance evidence.

## Terms

- `Policy revision` — one immutable localized published document with its own
  revision ID, source digest, version, and effective date.
- `Acceptance evidence` — the narrow account-to-revision record created by the
  onboarding completion request.
- `Onboarding pending` — the account status allowed to read legal onboarding,
  complete it, and log out, but not to use ordinary account functions.

## Requirements

- `REQ-5501`: The reviewed source of each policy is the exact Markdown under
  `docs-user-facing/legal/{locale}/{slug}/{version}/document.md`,
  with matching slug, locale, policy version, and effective date in
  frontmatter. Application startup publishes a new immutable revision only
  when the source digest changes.
- `REQ-5502`: `service_rules` and `personal_data_consent` are separate,
  required documents. Privacy, cookie, and licensing notices remain public
  information pages and are not represented as consent merely because read.
- `REQ-5503`: A newly created OAuth account starts `onboarding_pending`.
  Pending accounts may read their onboarding state, complete it, and log out;
  all ordinary authenticated API surfaces reject them.
- `REQ-5504`: Completion accepts only the current localized revision IDs for
  both required documents in one transaction. It records account, revision,
  acceptance type, acceptance time, locale, and source; the pair is unique and
  an account becomes `active` only after both records exist.
- `REQ-5505`: Acceptance evidence contains no raw IP address, provider access
  token, browser fingerprint, or checkbox text. Network abuse controls and
  ordinary security logs are separate from consent evidence.
- `REQ-5506`: Accounts and publisher listings are private by default. The web
  build ships no analytics or marketing tracker and no optional-cookie banner.
- `REQ-5507`: The public document API and web page identify policy version,
  effective date, immutable revision ID, and historical revision when its ID is
  explicitly requested.
- `REQ-5508`: A public policy page links to the exact Markdown source in the
  public GitHub repository, pinned to the deployed commit when available. The
  published body is read from that repository-tracked file and is not altered
  by runtime operator substitutions.

## States and errors

`onboarding_pending` redirects a web user to onboarding and produces a typed
permission denial on ordinary authenticated API calls. A stale or substituted
revision ID is rejected, leaving the account pending. Repeating the same valid
completion is safe and does not duplicate acceptance evidence.

## Security and privacy

Legal source is packaged from the public repository rather than fetched from a
mutable remote URL at request time. Operator identity and contact details are
literal reviewed content in each version, so the Git blob, published digest,
and accepted revision describe the same text. Deployers still review the policy
for processing locations, retention, and applicable law before public launch.

## Compatibility and migration

The migration keeps pre-existing accounts active. New registrations use the
onboarding state. New policy text is a new policy version/revision; it must not
rewrite old evidence.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-5501`, `REQ-5507`, `REQ-5508` | Document tests load the versioned repository source, publish revisions, retain source commit/path, and retrieve both current and superseded revisions. |
| `REQ-5502` | Contract and API tests expose two separate required revision IDs and do not treat disclosure pages as acceptance records. |
| `REQ-5503`–`REQ-5505` | API test proves a pending session is gated, stale IDs fail, both exact records are stored once, and activation follows. |
| `REQ-5504` | Onboarding storage test verifies the unique exact-revision pair, acceptance timestamp, locale, and state transition. |
| `REQ-5506` | Web/session tests prove the pending redirect and default-private session/profile behaviour. |
