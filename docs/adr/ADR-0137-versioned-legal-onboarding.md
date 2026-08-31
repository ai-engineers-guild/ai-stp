---
description: "Decision to activate new accounts only after exact immutable service-rules and personal-data-consent revisions are accepted."
last_verified: "2026-08-31"
---

# ADR-0137: Versioned legal onboarding

Status: accepted.

## Context

OAuth registration receives a verified provider identity and the service stores
account-related personal data. A generic click through a mutable web page is
not sufficient evidence of what a user accepted. The project is a free public
open-source service and does not need advertising or a consent-management
platform.

## Decision

The repository packages a reviewed policy set in EN and RU under
`legal/{locale}/{slug}/{version}/document.md`. Startup reads those exact files
and publishes them through the existing immutable `PublicDocument` /
`DocumentRevision` path. Runtime configuration does not substitute operator
details into legal text. The public site links to the Markdown at the deployed
Git commit, making the Git blob, rendered page, and acceptance evidence
auditable as one source.

New OAuth accounts are `onboarding_pending`; they become active only after a
single request confirms the exact current `service_rules` and
`personal_data_consent` revisions.

An acceptance row contains only the account, document revision, acceptance
kind, timestamp, locale, and server source. It is unique per account,
revision, and kind. It deliberately does not retain source IP, user agent, a
provider token, or a copy of the checkbox label. Historical documents remain
publicly addressable by revision ID.

Privacy, cookie, and licensing pages are disclosures, not forced “consents”.
The default public profile and publisher listing are off. The web deployment
does not load analytics or marketing tags, so an optional-cookie banner is not
needed.

## Consequences

- the database has a small additive account state and acceptance-evidence table;
- OAuth callback needs a web onboarding redirect; ordinary API authentication
  rejects pending accounts;
- changing policy source creates a new revision without altering prior evidence;
- no external consent SaaS, tracking cookie, or raw-IP consent ledger is added;
- legal adequacy still requires review of the stated operator identity,
  retention choices, processing locations, and applicable law before launch.

## Review conditions

Revisit this decision when the service adds minors, paid services, marketing,
analytics, a different controller/operator, or processing not described by the
policy source.
