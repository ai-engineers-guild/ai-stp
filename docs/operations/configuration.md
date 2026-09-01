---
description: "Configuration of the local CLI and server environment."
last_verified: "2026-09-01"
---

# Configuration

## Rules

- required values are validated at startup;
- secrets have no unsafe default values;
- an unknown key causes an error in internal configurations;
- secrets are not printed;
- CLI and server have separate settings models;
- local paths are absolute and owned by the user;
- provider/runtime paths are not resolved through an untrusted ambient `PATH`.

## Groups

User CLI settings live in a single global configuration. The field list, default values, and source precedence belong to `docs/contracts/cli-config.md` and are not repeated here.

| Group                 | Contents                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CLI                   | data/state/cache directories, catalog and its address, synchronization, search, discovery roots, timeout, output mode                                                                                                                                                                                                                                                                                                                                                                                         |
| API                   | database URL, object storage, OAuth, session keys, CORS, catalog usage counters (`docs/contracts/catalog-usage-metrics.md`)                                                                                                                                                                                                                                                                                                                                                                                   |
| Worker                | database, concurrency, timeout, retry ceilings. Official GitHub and package upstream enqueue is `python -m ai_stp_platform.official_upstream.enqueue`; source upsert is `python -m ai_stp_platform.official_upstream`. Optional `AI_STP_WORKER_GITHUB_TOKEN` is sent only to `api.github.com` (runbook `official-upstream-components.md`) |
| Worker safety         | `AI_STP_SAFETY_EXTERNAL_CLI`, `AI_STP_SAFETY_SANDBOX`, `AI_STP_OSV_OFFLINE_DIR`, `AI_STP_OSV_MAX_AGE_HOURS`, `AI_STP_OSV_REQUIRE_FRESH` (runbook `safety-scan.md`)                                                                                                                                                                                                                                                                                                                                            |
| Worker SEO enrichment | `AI_STP_SEO_ENRICHMENT_ENABLED`, `AI_STP_SEO_ENRICHMENT_URL`, `AI_STP_SEO_ENRICHMENT_CREDENTIAL`, `AI_STP_SEO_ENRICHMENT_MODEL_ALIAS`, `AI_STP_SEO_ENRICHMENT_TIMEOUT_SECONDS` per `SPEC-053`. CLIPROXY `AI_STP_CLIPROXY_URL` (default `http://cliproxy:8317/v1`), `AI_STP_CLIPROXY_API_KEY`, and `AI_STP_CLIPROXY_MODEL` belong to the LiteLLM container of the `seo_enrichment` profile and are not passed to the worker. The session is JSON in `deploy/cliproxy/auths/`; see runbook `seo-publication.md` |
| Content import        | scoped bearer `AI_STP_CONTENT_IMPORT_TOKEN` for `POST /v1/content/repository/import`; an empty value disables import while allowing the API to start. The one-shot importer retries GET state / POST snapshot on `URLError` and HTTP 502/503/504: `AI_STP_CONTENT_IMPORT_ATTEMPTS` (default 8) and `AI_STP_CONTENT_IMPORT_RETRY_SECONDS` (default 1); 4xx is not retried                                                                                                                                      |
| RustFS/S3             | endpoint, bucket, credentials, region                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Resend                | API key, sender, callback URLs                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| GitHub/Google         | OAuth client IDs/secrets and redirect URIs                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

Dev and prod configuration is provided through separate env files: only secret-free samples are committed, while actual `.env.dev` and `.env.prod` files are excluded from the index per `SPEC-019`. A complete `.env.example` is added together with the first executable server code. Until then, the documentation does not present nonexistent variables.

## Browser device metadata

The browser device cookie outlives the login session and is refreshed after every
successful OAuth callback. Its lifetime is set by `AI_STP_AUTH_DEVICE_COOKIE_TTL_SECONDS`;
the default is 400 days, the maximum lifetime supported by modern browsers.

Approximate location is read from the `x-vercel-ip-city` and `x-vercel-ip-country`
request headers when a CDN in front of the deployment supplies them, and is otherwise
unknown; login works either way. The application stores only city and country, not the
source IP or precise coordinates.

`SPEC-023` `REQ-2314` describes a different mechanism — a local City Lite MMDB looked
up from a client-address header the edge proxy sets. That mechanism is not built: no
database, env variable, mount or lookup code exists. The requirement stands as intent;
this page describes what currently runs.
