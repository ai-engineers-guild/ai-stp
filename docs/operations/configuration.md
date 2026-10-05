---
description: "Configuration of the local CLI and server environment."
last_verified: "2026-09-20"
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
| API                   | database URL, object storage, OAuth, session keys, OAuth callback origin allowlist (`AI_STP_AUTH_OAUTH_CALLBACK_ORIGINS`), catalog usage counters (`docs/contracts/catalog-usage-metrics.md`)                                                                                                                                                                                                                                                                                                                  |
| Worker                | database, concurrency, timeout, retry ceilings. Official GitHub and package upstream enqueue is `python -m ai_stp_platform.official_upstream.enqueue` (`--force` for a same-day audited retry); the Git manifest is the only production source inventory and is reconciled through the Official runbook/status commands. `AI_STP_WORKER_GITHUB_TOKEN` is sent only to `api.github.com`; without it GitHub's 60 unauthenticated requests/hour are not enough for a many-source Official sync (runbook `official-upstream-components.md`) |
| Worker safety         | `AI_STP_SAFETY_EXTERNAL_CLI`, `AI_STP_SAFETY_SANDBOX`, `AI_STP_SAFETY_CACHE_TTL_SECONDS`, `AI_STP_SAFETY_ASSESSMENT_GENERATION`, `AI_STP_OSV_OFFLINE_DIR`, `AI_STP_OSV_MAX_AGE_HOURS`, `AI_STP_OSV_REQUIRE_FRESH` (runbook `safety-scan.md`)                                                                                                                                                                                                                                                                                                                                            |
| Worker SEO enrichment | `AI_STP_SEO_ENRICHMENT_ENABLED`, `AI_STP_SEO_ENRICHMENT_URL`, `AI_STP_SEO_ENRICHMENT_CREDENTIAL`, `AI_STP_SEO_ENRICHMENT_MODEL_ALIAS`, `AI_STP_SEO_ENRICHMENT_TIMEOUT_SECONDS` per `SPEC-053`. CLIPROXY `AI_STP_CLIPROXY_URL` (default `http://cliproxy:8317/v1`), `AI_STP_CLIPROXY_API_KEY`, and `AI_STP_CLIPROXY_MODEL` belong to the LiteLLM container of the `seo_enrichment` profile and are not passed to the worker. The session is JSON in `deploy/cliproxy/auths/`; see runbook `seo-publication.md` |
| Content import        | scoped bearer `AI_STP_CONTENT_IMPORT_TOKEN` for `POST /v1/content/repository/import`; an empty value disables import while allowing the API to start. The one-shot importer retries GET state / POST snapshot on `URLError` and HTTP 502/503/504: `AI_STP_CONTENT_IMPORT_ATTEMPTS` (default 8) and `AI_STP_CONTENT_IMPORT_RETRY_SECONDS` (default 1); 4xx is not retried                                                                                                                                      |
| RustFS/S3             | endpoint, credentials, region, `AI_STP_STORAGE_ARTIFACT_BUCKET`, `AI_STP_STORAGE_ASSET_BUCKET`. `AI_STP_STORAGE_BUCKET` is the upgrade alias so objects already on the host stay reachable. `just infra-env-check` rehearses `require_deploy_env` in `deploy/lib.sh` without starting containers |
| Resend                | API key, sender, callback URLs                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| GitHub/Google         | OAuth client IDs/secrets and redirect URIs. Corporate OIDC sign-in (ADR-0218) adds `AI_STP_AUTH_AUTHENTIK_ISSUER_URL`/`CLIENT_ID`/`CLIENT_SECRET` and `AI_STP_AUTH_KEYCLOAK_ISSUER_URL`/`CLIENT_ID`/`CLIENT_SECRET`; the issuer is the IdP application or realm base used for `/.well-known/openid-configuration` discovery, and an empty issuer disables the provider. Self-managed GitLab sign-in (ADR-0223) uses the same triple — `AI_STP_AUTH_GITLAB_ISSUER_URL`/`CLIENT_ID`/`CLIENT_SECRET` — where the issuer is the GitLab instance base URL                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

Dev and prod configuration is provided through separate env files: only secret-free samples are committed (`.env.dev.example`, `.env.prod.example`), while actual `.env.dev` and `.env.prod` files are excluded from the index per `SPEC-019`. Names in those samples are the contract; values stay on the host. `just infra-env-check` rehearses `require_deploy_env` against a local `.env.prod` without starting containers.

## Browser device metadata

The browser device cookie marks the remembered device row and is refreshed after every
successful OAuth callback. Its lifetime follows `AI_STP_AUTH_SESSION_TTL_SECONDS`
(default 1,209,600 seconds — 14 days), the same knob as the session and CSRF cookies;
there is no separate device-cookie TTL setting.

Approximate location does not depend on an external service. The host's nginx sets
`X-AI-STP-Client-IP` to the connecting address, replacing whatever the client sent,
and the API resolves city and country against a local City Lite MMDB at
`AI_STP_AUTH_GEOIP_CITY_DB_PATH`. The production compose mounts `deploy/geoip`
read-only; the database file and its update policy belong to the operator and are not
committed to Git. A private or loopback address resolves to nothing, as does a missing
or unreadable database, and login continues to work in either case.

When the lookup yields nothing, `x-vercel-ip-city`, `x-vercel-ip-country` and
`cf-ipcountry` are read as a fallback for a deployment behind a CDN that supplies
them. No CDN sits in front of this one, so those headers reach the API only if a
visitor sends them: the fallback can therefore mislabel the visitor's own device row
and nothing else. The application stores only city and country, never the address it
resolved them from or precise coordinates.
