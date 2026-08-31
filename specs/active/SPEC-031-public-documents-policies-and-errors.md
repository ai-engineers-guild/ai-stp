---
description: "SPEC-031: Public documents, versioned policies, and error pages."
last_verified: "2026-08-08"
---

# SPEC-031: Documents, policies, and error pages

## Purpose

The site provides a dedicated documentation section useful to people and agents,
as well as localized legal and service documents. Texts have a version, language,
provenance, and dedicated public API/pages; technical documentation is imported
from a pinned repository source rather than copied manually into web. The public
user-facing source lives in `docs-user-facing/docs/`; the internal `docs/` remains the
repository's normative boundary.

## Scope

Included: docs portal, Markdown import/render, public document API, policy
revision storage, privacy/cookie/service/licensing policies, 404 and global 500
pages. Excluded: an unrestricted user CMS, browser Git authoring, legal advice,
acceptance workflow, or arbitrary remote Markdown.

## Terms

- `PublicDocument` — a document with a stable slug, kind, and language.
- `DocumentRevision` — an immutable localized revision with a digest and source.
- `Technical source` — an allowlisted repository path and exact commit from which
  CI imports documentation.
- `Policy` — a public document kind with the `draft`/`published`/`superseded` lifecycle.

## Requirements

- `REQ-3101`: Public docs nav contains a product overview, CLI/agent quickstart,
  catalog guide, setup/component guide, trust/security guide,
  troubleshooting, and docs for authors.
  Each page identifies the source revision, update time, and language; agent paths
  have a compact machine-readable index with no hidden prompt content.
- `REQ-3102`: Technical docs obtain their source only from an allowlisted repository,
  path, and exact commit in the CI import scenario. Web/API does not fetch raw Git content
  from a user-supplied URL or during the request path.
- `REQ-3103`: Policy kinds include `privacy`, `cookies`, `service_rules`,
  `personal_data_consent`, and `author_content_and_license`. The latter clearly separates the platform license from
  author content, prohibits illegal/harmful uploads, and does not promise platform
  security review of content.
- `REQ-3104`: PublicDocument and DocumentRevision store slug, kind, locale,
  source type/ref/path, content digest, Markdown source, renderer version,
  lifecycle, published_at, and supersession link. Changing published text creates
  a new revision; the old published URL remains available and identifies its successor.
- `REQ-3105`: The API returns only the published revision for the requested locale or
  an explicitly declared fallback. Draft/pending policy, editor identity, internal
  review, and source credentials do not enter the public API/cache.
- `REQ-3106`: Markdown documents use the renderer/policy from SPEC-029.
  Technical docs and policies have a table of contents, stable heading anchors,
  copy link, print-friendly view, and an accessible heading hierarchy.
- `REQ-3107`: `/[locale]/not-found` is a complete 404 page with links to the
  catalog, documentation, and home. Root `global-error` is a minimal 500 page
  that does not disclose the error message/stack, with retry, a request/correlation reference
  when available, and safe support/docs links. Both are available without a session.
- `REQ-3108`: The site footer links to current published policy revisions and the
  licensing page. Links are visible on public and authenticated surfaces; locale
  parity and archive history are preserved.

## States and errors

An unknown public slug and unavailable locale do not disclose the existence of a draft and return
404. A render/import error leaves the previous published revision in place and creates
an observable operator result; public read returns a safe unavailable state on dependency failure.
The 500 page never serializes a server exception.

## Security and privacy

Policy text contains no secrets, internal incident data, or personal data.
Repository import verifies the allowlist, commit pinning, path traversal, and digest.
The public docs cache is invalidated only after an atomic publish; user-supplied
Markdown is not added to the platform documentation corpus.

## Compatibility and migration

Repository `docs-user-facing/docs/**` becomes the canonical public technical source;
`docs/**` remains the canonical internal normative source. An imported revision
does not replace the source checkout. Policy tables and public APIs are added
additively. No mandatory acceptance of a new policy is introduced without a
separate ADR and product decision. `SPEC-055` and `ADR-0135` record that
decision for new-account onboarding only.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-3101`–`REQ-3102` | CI import test proves the exact commit/path/digest and agent index. |
| `REQ-3103`–`REQ-3105` | Contract/storage tests prove locale handling, immutable revisions, fallback, and draft redaction. |
| `REQ-3104` | Storage test proves revision immutability, digest, source ref, and supersession link. |
| `REQ-3106` | Markdown/a11y snapshots verify the ToC, anchors, and renderer policy. |
| `REQ-3107` | Browser tests prove the locale 404, root 500, retry, and absence of stack data. |
| `REQ-3108` | Route test verifies footer links to published policy revisions in RU/EN. |
