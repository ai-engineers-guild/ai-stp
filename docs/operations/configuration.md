---
description: "Configuration of the local CLI and server environment."
last_verified: "2026-08-29"
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
| Worker                | database, concurrency, timeout, retry ceilings                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
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

Approximate location does not depend on an external service. Caddy overwrites
`X-AI-STP-Client-IP` with the computed client address, and the API looks up the city
and country in a local City Lite MMDB at `AI_STP_AUTH_GEOIP_CITY_DB_PATH`. The
production compose mounts `deploy/geoip` read-only; the database file and its update
policy belong to the operator and are not committed to Git. `deploy/geoip/city.mmdb`
contains the monthly DB-IP City Lite database under CC BY 4.0; the UI attributes DB-IP
where it displays a resolved location. If the database is missing or corrupt, login
continues to work and the location remains unknown. The application stores only city
and country, not the source IP or precise coordinates.
