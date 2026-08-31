---
description: "Runbook: server SEO revisions, sitemap, and optional LiteLLM enrichment."
last_verified: "2026-08-29"
---

# SEO publication

## When to use

After a component or setup is published, articles are imported, or a service or
country changes, the page must receive an active base SEO revision without a
model. LiteLLM enrichment is enabled separately and does not block publication.

## Verify

1. The worker processed `seo_build`, and `seo_active_revision` points to
   `state=active`.
2. `GET /v1/seo/subjects/{kind}/{id}?locale=en` returns a profile with
   `Cache-Control: public`.
3. `/sitemap.xml` and `/sitemaps/{kind}-{locale}-{page}.xml` contain only
   `index_eligible` URLs.
4. `/llms.txt` remains compact and links to `/llms/catalog.ndjson`.
5. `/og/{revision_id}.png` returns a 1200×630 image with an `immutable` cache.

## Enrichment

Compose profile `seo_enrichment` starts LiteLLM (`seo-writer`) and CLIPROXY
(official image `eceasy/cli-proxy-api`) on one `internal` network. LiteLLM uses
`http://cliproxy:8317/v1`. Port 8317 is not published to the host. The worker
reads only `AI_STP_SEO_ENRICHMENT_URL`, the process credential, and the alias;
`AI_STP_CLIPROXY_*` enters only the LiteLLM container.

The portable session is JSON under `deploy/cliproxy/auths/` (the CLIProxyAPI
`auth-dir`, mounted at `/root/.cli-proxy-api` in the container). It is neither
an `agy` login nor `~/.gemini`. Files `antigravity-*.json` are copied between
machines; CLIPROXY reloads the directory without restart.

Locally, if CLIPROXY has already logged in on this machine:

```sh
cp "$HOME/.cli-proxy-api"/antigravity*.json deploy/cliproxy/auths/
```

On Windows PowerShell:

```powershell
Copy-Item "$env:USERPROFILE\.cli-proxy-api\antigravity*.json" deploy\cliproxy\auths\
```

Copy the same directory—not browser cookies—to the server:

```sh
scp -r deploy/cliproxy/auths/ user@server:ai_stp/deploy/cliproxy/auths/
```

For the first login or an expired refresh, log in inside the container. The
Antigravity callback listens on `127.0.0.1:51121`.

```sh
docker compose -f docker-compose.dev.yml \
  -f docker-compose.seo-enrichment.yml --profile seo_enrichment \
  exec cliproxy /CLIProxyAPI/CLIProxyAPI -no-browser -antigravity-login
```

On a browserless server, first create a tunnel from the workstation
(`ssh -L 51121:127.0.0.1:51121 user@server`), then run the same `exec` command.
Google returns the code to `localhost:51121`, and SSH carries it to the
container. Do not expose ports 8317 or 51121 to the internet.

```sh
docker compose -f docker-compose.dev.yml \
  -f docker-compose.seo-enrichment.yml --profile seo_enrichment up -d
docker compose -f docker-compose.dev.yml \
  -f docker-compose.seo-enrichment.yml --profile seo_enrichment \
  exec worker python -m ai_stp_platform.seo.enqueue_pending
```

The command first queues `seo_build` for profiles using an old template version
and sends current profiles to `seo_enrich`. After building, the worker queues
enrichment itself. The server reads the canonical origin from
`AI_STP_SEO_PUBLIC_ORIGIN`, falling back to `NEXT_PUBLIC_APP_URL`; in production
this must be the site's external HTTPS URL, not an address from the request.

`enqueue_pending` does not requeue a job already in `dead_letter` with the same
idempotency key. Retry or reset such jobs separately after CLIPROXY is healthy.

The worker rejects vague or incomplete responses before publication and makes
up to five repair attempts with a safe failure reason. If every attempt fails
the quality gate, the deterministic base revision remains active.

Disabling the flag leaves the base revision active. Rollback:
`POST /v1/seo/subjects/{kind}/{id}/rollback`.

## Schema rollback

The tables are additive. Downgrade `0031_seo_projections` removes the SEO tables
and nullable fields `external_product.description`/`source_url`. Without an
active revision, the web uses the current presenter and `noindex`.
