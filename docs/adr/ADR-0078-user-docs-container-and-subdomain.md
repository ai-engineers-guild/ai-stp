---
description: "Decision to serve public user documentation through a separate container and subdomain route."
last_verified: "2026-08-10"
---

# ADR-0078: User documentation container and subdomain

Status: accepted.

## Context

`ADR-0077` separated public user documentation from internal `docs/` and chose
MkDocs Material. This left an operational boundary: how to serve the built site
in dev and staging/prod without breaking the already occupied API path `/docs`.

In the current topology, dev runs without Caddy: `web` is published at
`localhost:3000`, and `api` at `localhost:8000`. Staging/prod use Caddy as the
public edge. FastAPI continues to own `/docs`, `/redoc`, and `/openapi.json`, so
user documentation cannot safely occupy the same path.

## Options

1. Serve user documentation from `apps/web`. This mixes the help center with
   the application and retains an unnecessary Next.js/Fumadocs layer.
2. Mount user documentation at `/docs`. This conflicts with the API docs and
   dev rewrite.
3. Introduce a separate `docs` service: publish it at `localhost:8011` in dev,
   and route a separate `AI_STP_DOCS_HOST` host through Caddy in staging/prod.

## Decision

Option 3 is accepted. `Dockerfile.user-docs` is introduced with two targets:

- `dev` runs `mkdocs serve` on internal port `8000`; compose publishes it as
  `http://localhost:8011`;
- `prod` builds the static MkDocs site and serves `/srv` through Caddy on
  internal port `8080`.

Web links to public user documentation come from `AI_STP_USER_DOCS_URL`. In
dev, the default value is `http://localhost:8011`; in staging/prod, it is the
HTTPS URL of the documentation subdomain.

Prod Caddy receives a second host, `AI_STP_DOCS_HOST`, and proxies it to `docs`.
The primary host continues routing `/v1`, `/docs`, `/redoc`, and
`/openapi.json` to `api`, and all other requests to `web`.

## Consequences

- Dev compose gains a third published port: `8011` for user documentation. This
  is a dev exception alongside the direct `web` and `api` ports.
- Prod compose gains an internal `docs` service; publicly it is accessible only
  through the Caddy host `AI_STP_DOCS_HOST`.
- Staging/prod must define the matching pair:
  `AI_STP_DOCS_HOST=docs.example.com` and
  `AI_STP_USER_DOCS_URL=https://docs.example.com`.
- The API docs route `/docs` remains and is not used for user documentation.

## Reconsideration conditions

The decision is reconsidered if Caddy ceases to be the public edge, if user
documentation requires a server-side runtime, or if the API docs move away
from `/docs` and a verifiable opportunity arises to safely occupy that path
with the help center.
