---
description: "Boundary, directory, and build process for public user documentation."
last_verified: "2026-08-10"
---

# Public User Documentation

Public user documentation lives in `docs-user-facing/docs/`. It is a help center for a
developer and their Agent: how to install the CLI, understand the catalog,
select components, build a setup, evaluate trust, and recover from an error.

`docs/` remains the repository's internal normative environment. ADRs,
specifications, contracts, engineering rules, and runbooks are not copied into
`docs-user-facing/docs/`; public pages link to them only when the reader needs the source
of truth.

The site is built with a separate configuration:

```bash
just user-docs-build
```

Local preview:

```bash
just user-docs-serve
```

The public-site artifact is written to `.site-user-docs/`. It can be served by
a static container or a dedicated edge route without running `apps/web`.

In Compose, public user documentation is served by a separate `docs` service.
In development it is published at `http://localhost:8011`; in production,
the host's nginx routes a dedicated `AI_STP_DOCS_HOST` name to the port the `docs`
service publishes on loopback (`ADR-0135`).

Links from `apps/web` use `AI_STP_USER_DOCS_URL`. In development this is
`http://localhost:8011`; in production it is the HTTPS URL of the docs
subdomain. The `/docs` path remains reserved for API documentation and is not
used as the help center.

Public-site navigation is defined alongside the content through
`docs-user-facing/docs/ru/.pages`. Markdown remains the base format. If a page needs contract
data, it must link to the canonical owner in `docs/`, `specs/active/`, or
`schemas/` rather than copying a normative definition.
