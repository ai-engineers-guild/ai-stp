---
description: "Runbook: standing up local authentik and Keycloak and verifying corporate OIDC SSO end to end."
last_verified: "2026-09-29"
---

# Local corporate OIDC SSO (authentik + Keycloak)

Verified live on 2026-09-29: full browser login through both providers against the
`compose.dev.yml` stack, landing on the real web account page.

## Topology

| Piece | URL | Notes |
| --- | --- | --- |
| web (dev stack) | `http://localhost:3000` | BFF forwards the session cookie to the API |
| api (dev stack) | `http://localhost:8000` | callback origin |
| Keycloak | `http://localhost:58080` | realm `corp` |
| authentik | `http://localhost:59000` | application slug `stp` |

The browser and the API container must agree on issuer URLs. Browser-side `localhost`
works, but `localhost` inside the api container is the container itself — and
`host.docker.internal` is **not** reachable from the browser on Windows Docker
Desktop (it resolves to a gateway IP, not 127.0.0.1). The working arrangement keeps
issuer strings as `localhost` everywhere and maps `localhost` to the host gateway
inside the api container:

```yaml
# deploy/compose.oidc-local.yml (local-only override)
services:
  api:
    extra_hosts:
      - "localhost:host-gateway"
```

```bash
docker compose -f deploy/compose.dev.yml -f deploy/compose.oidc-local.yml up -d api
```

Reaching a host-published port via `localhost:port` inside the container goes to
the host gateway; the api's own `localhost:8000` healthcheck still resolves to
127.0.0.1 first, so self-checks are unaffected.

## Keycloak

```bash
docker run -d --name stp-e2e-kc \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  -p 58080:8080 \
  quay.io/keycloak/keycloak:26.3 \
  start-dev --hostname=http://localhost:58080
```

Provision realm, confidential client, and user through the admin REST API
(admin console at `http://localhost:58080/admin` works too):

```python
# token: POST /realms/master/protocol/openid-connect/token (admin-cli, admin/admin)
# POST /admin/realms            {"realm": "corp", "enabled": true}
# POST /admin/realms/corp/clients
{
    "clientId": "ai-stp",
    "enabled": true,
    "publicClient": false,
    "secret": "ai-stp-keycloak-secret",
    "redirectUris": ["http://localhost:8000/v1/auth/keycloak/callback"],
    "protocol": "openid-connect",
    "standardFlowEnabled": true,
}
# POST /admin/realms/corp/users
{
    "username": "alice",
    "enabled": true,
    "email": "alice@corp.example",
    "emailVerified": true,
    "credentials": [{"type": "password", "value": "alice-pass", "temporary": false}],
}
```

Issuer: `http://localhost:58080/realms/corp`
(discovery: `.../realms/corp/.well-known/openid-configuration`).

## authentik

authentik needs four services; the official compose bundle is the least-effort
path (run it from a scratch directory, not the repo root):

```bash
mkdir tmp/authentik && cd tmp/authentik
curl -O https://goauthentik.io/docker-compose.yml
cat > .env <<'ENV'
PG_PASS=authentik-e2e-pg-pass
AUTHENTIK_SECRET_KEY=<random 64+ chars>
AUTHENTIK_BOOTSTRAP_PASSWORD=akadmin-e2e-pass
AUTHENTIK_BOOTSTRAP_TOKEN=ak-e2e-bootstrap-token-0123456789
COMPOSE_PORT_HTTP=59000
AUTHENTIK_TAG=2026.8.3
ENV
docker compose up -d   # first boot runs migrations, ~2-3 min
```

Admin UI: `http://localhost:59000/if/admin/` (`akadmin` / bootstrap password).
Provisioning via REST (token auth) requires three non-obvious fields:

1. **`grant_types`** — API-created providers default to `[]` and then authorize
   rejects every request with `invalid_request` ("The request is otherwise
   malformed"; the server log shows `Invalid grant_type for provider`). Set
   `["authorization_code", "refresh_token"]` explicitly.
2. **`invalidation_flow`** — required on create; use the
   `default-provider-invalidation-flow` flow pk.
3. **`email_verified`** — the stock email scope mapping hardcodes
   `email_verified: False`, and this API refuses unverified emails with a generic
   auth failure. Create a custom scope mapping with `scope_name: "email"` and
   expression `return {"email": request.user.email, "email_verified": True}`,
   and pass it instead of the stock `scope-email` mapping.

```python
# POST /api/v3/providers/oauth2/  (Bearer <bootstrap token>)
{
    "name": "stp",
    "client_id": "stp",
    "client_secret": "stp-secret",
    "authorization_flow": "<default-provider-authorization-*-consent pk>",
    "invalidation_flow": "<default-provider-invalidation-flow pk>",
    "redirect_uris": [
        {"matching_mode": "strict", "url": "http://localhost:8000/v1/auth/authentik/callback"}
    ],
    "property_mappings": ["<custom email mapping pk>", "<scope-openid pk>", "<scope-profile pk>"],
    "signing_key": "<authentik Self-signed Certificate pk>",
    "client_type": "confidential",
    "grant_types": ["authorization_code", "refresh_token"],
}
# POST /api/v3/core/applications/  {"name": "STP", "slug": "stp", "provider": <pk>}
# POST /api/v3/core/users/         {"username": "bob", "name": "Bob Corp",
#                                   "email": "bob@corp.example", "is_active": true}
# POST /api/v3/core/users/<pk>/set_password/  {"password": "..."}
```

Issuer: `http://localhost:59000/application/o/stp` — authentik derives it from the
request Host, so it stays consistent whether reached from the browser or from the
api container.

## API wiring

`.env.dev` (used by `compose.dev.yml` `env_file`):

```dotenv
AI_STP_AUTH_AUTHENTIK_ISSUER_URL=http://localhost:59000/application/o/stp
AI_STP_AUTH_AUTHENTIK_CLIENT_ID=stp
AI_STP_AUTH_AUTHENTIK_CLIENT_SECRET=stp-secret
AI_STP_AUTH_KEYCLOAK_ISSUER_URL=http://localhost:58080/realms/corp
AI_STP_AUTH_KEYCLOAK_CLIENT_ID=ai-stp
AI_STP_AUTH_KEYCLOAK_CLIENT_SECRET=ai-stp-keycloak-secret
```

`AI_STP_AUTH_OAUTH_REDIRECT_BASE_URL` already defaults to `http://localhost:8000`
in dev, which is why the IdP-registered redirect URIs use `:8000`. The api image
must be rebuilt when the branch changes:

```bash
docker compose -f deploy/compose.dev.yml -f deploy/compose.oidc-local.yml build api
docker compose -f deploy/compose.dev.yml -f deploy/compose.oidc-local.yml up -d api
```

## Verify

Browser: open `http://localhost:8000/v1/auth/keycloak/login?client=web` (or
`authentik`). Expected chain: provider login form → (authentik: consent screen) →
callback → `http://localhost:3000/ru/corporate/onboarding` for a new account →
after accepting the two documents, `/ru/corporate/account` lists the identity
(`authentik`/`keycloak` with the IdP display name).

Headless check that registration + PKCE are wired:

```bash
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" \
  http://localhost:8000/v1/auth/keycloak/login
# -> 302 http://localhost:58080/realms/corp/protocol/openid-connect/auth?...
```

`oauth_identity` rows should carry `provider_subject` (Keycloak UUID / authentik
hashed sub), not the email.

## Failure map

| Symptom | Cause |
| --- | --- |
| `400 unsupported oauth provider` | api image predates provider support — rebuild |
| `503` on `/v1/auth/{p}/login` | issuer/client_id/secret not all set — provider disabled |
| IdP redirects to `?error=invalid_request` "malformed" (authentik) | `grant_types` empty on the provider |
| `400` "invalid redirect uri" style error at IdP | redirect URI not byte-identical to the registered one |
| callback → `/ru/login?status=error` | token/userinfo call failed: issuer unreachable from the api container, or `email_verified` false |
| `404` on `/ru/...` after callback | `AI_STP_AUTH_PUBLIC_BASE_URL` points at an origin with no web |

## Teardown

```bash
docker rm -f stp-e2e-kc
cd tmp/authentik && docker compose down -v
# remove the env block from .env.dev and recreate api without the override
```
