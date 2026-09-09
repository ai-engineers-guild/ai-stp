---
description: "Operator runbook for the single GitHub App used by source access and repository actions."
last_verified: "2026-09-09"
---

# GitHub Connector operations

This runbook configures one GitHub App for issues 181–186. It is not a GitHub
Actions workflow. A personal account and connected organizations may grant the App
access to their repositories. The connector keeps each installation separate so the
account owner and repository count remain visible in the product.
The product still treats source reading and repository administration as separate
consent records and requires a new durable confirmation plan for every mutation.

## App registration

Create one GitHub App owned by the deployment account or organization. Configure:

- repository permission `Metadata: Read-only`;
- repository permission `Contents: Read-only`;
- repository permission `Administration: Read and write`;
- user authorization uses the explicit OAuth web flow after installation;
- **Request user authorization (OAuth) during installation** disabled;
- personal and organization installations may use either repository selection mode; the
  connector displays each installation separately;
- setup URL `<public-base>/v1/connectors/github/callback` so the installation can
  hand off to the explicit OAuth flow;
- callback URL exactly `<public-base>/v1/connectors/github/callback`.

The browser sign-in provider is separate from this GitHub App. Its OAuth
application must also register `<public-base>/v1/auth/github/callback`; add the
local callback to that OAuth application as well when testing locally.

The broader administration permission is visible during installation. It does not
authorize an automatic mutation: ai-stp only mutates after the user connects the
administration capability and confirms an exact plan. GitHub's permission and
installation model is described in [Choosing permissions for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app)
and [Installing a GitHub App from a third party](https://docs.github.com/en/apps/using-github-apps/installing-a-github-app-from-a-third-party).

## Deployment settings

Set these secrets in the API environment; never commit or print filled values:

```text
AI_STP_GITHUB_CONNECTOR_CLIENT_ID
AI_STP_GITHUB_CONNECTOR_CLIENT_SECRET
AI_STP_GITHUB_CONNECTOR_APP_SLUG
AI_STP_GITHUB_CONNECTOR_ENCRYPTION_KEY   # URL-safe base64 encoding of 32 random bytes
AI_STP_AUTH_OAUTH_REDIRECT_BASE_URL      # only when callback origin differs from public_base_url
```

The old `administration_*` settings are obsolete. A deployment is unavailable until
the four Connector settings are present. The encryption key is deployment-wide:
rotate it with a planned migration that re-encrypts live tokens, then revoke the old
key. Do not silently replace it, because existing ciphertext must fail closed if it
cannot be decrypted.

## Local Docker setup

Use one GitHub App per deployment environment. A GitHub App has one Setup URL,
so sharing the production App with localhost would send local installations to
production. In GitHub, open **Settings → Developer settings → GitHub Apps → New
GitHub App** and use:

- homepage URL `http://localhost:3000`;
- callback URL `http://localhost:8000/v1/connectors/github/callback`, with wildcard
  matching disabled;
- **Request user authorization (OAuth) during installation** disabled;
- setup URL `http://localhost:8000/v1/connectors/github/callback`;
- expiring user authorization tokens enabled;
- webhooks disabled; this connector does not consume webhook events;
- repository permissions `Metadata: Read-only`, `Contents: Read-only`, and
  `Administration: Read and write`;
- **Any account** for the public ai-stp service, so any GitHub user or organization
  can install the App. The local connector displays every active installation returned
  for the authorized GitHub identity.

For the separate GitHub OAuth application used to link a sign-in identity, register
`http://localhost:8000/v1/auth/github/callback` in addition to its production
callback. Do not copy the connector App's client secret into the OAuth application.

Create a client secret. Add the following names and private values to the local
`.env.dev` file; do not commit that file:

```dotenv
AI_STP_GITHUB_CONNECTOR_CLIENT_ID=<Client ID shown by GitHub>
AI_STP_GITHUB_CONNECTOR_CLIENT_SECRET=<generated client secret>
AI_STP_GITHUB_CONNECTOR_APP_SLUG=<slug from the App URL>
AI_STP_GITHUB_CONNECTOR_ENCRYPTION_KEY=<generated key below>
AI_STP_AUTH_PUBLIC_BASE_URL=http://localhost:3000
AI_STP_AUTH_OAUTH_REDIRECT_BASE_URL=http://localhost:8000
```

The production App uses the same permissions and flow with its production
homepage, callback, setup URL, slug and credentials. Pass that App's Client ID,
Client Secret and slug to the production API; use a separate encryption key per
deployment and never copy local secrets into production.

## Production App and delivery pipeline

Create a second App for production, for example `ai-stp`, and configure it with:

- homepage URL `https://ai-stp.aiguild.space`;
- callback URL `https://ai-stp.aiguild.space/v1/connectors/github/callback`;
- setup URL `https://ai-stp.aiguild.space/v1/connectors/github/callback`;
- **Request user authorization (OAuth) during installation** disabled;
- the same `Metadata`, `Contents`, and `Administration` permissions as the local App;
- **Any account**, unless the production product intentionally restricts who may install it.

The repository already has the two-part production delivery path: `check.yml`
validates `main`, then `deploy.yml` advances `deploy/prod`; the production host
pulls that ref and runs the deployment locally. This path deliberately does not
read GitHub App secrets from GitHub Actions. Put the connector credentials in the
host's gitignored `.env.prod`:

```dotenv
AI_STP_GITHUB_CONNECTOR_CLIENT_ID=<production App Client ID>
AI_STP_GITHUB_CONNECTOR_CLIENT_SECRET=<production App client secret>
AI_STP_GITHUB_CONNECTOR_APP_SLUG=ai-stp
AI_STP_GITHUB_CONNECTOR_ENCRYPTION_KEY=<production-only key>
AI_STP_AUTH_PUBLIC_BASE_URL=https://ai-stp.aiguild.space
```

For the existing `deploy.yml`, configure the GitHub repository variable
`AI_STP_PUBLIC_ORIGIN=https://ai-stp.aiguild.space` for `verify-public`. Do not
put the four connector values in that Actions environment: the workflow never
needs them and the host is the only process that reads `.env.prod`.

The separate GitHub sign-in OAuth application still uses
`AI_STP_AUTH_GITHUB_CLIENT_ID` and `AI_STP_AUTH_GITHUB_CLIENT_SECRET`; do not
substitute the connector App's Client ID or secret. There are no additional
connector secrets to add to a GitHub Actions Environment for the current
pull-based pipeline. After writing `.env.prod` on the host, validate and deploy:

```sh
docker compose -f docker-compose.prod.yml --env-file .env.prod config
docker compose -f docker-compose.prod.yml --env-file .env.prod build
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
curl -fsS https://ai-stp.aiguild.space/v1/health/live
```

The required placeholder names are present in both `.env.dev.example` and
`.env.prod.example`. Keep the local and production Client Secrets and encryption
keys different. Rotating the encryption key requires re-encrypting stored tokens;
do not replace it as a routine redeploy.

Generate the encryption key once in PowerShell and paste only its output into the
local file:

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
[Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
```

Restart only the services that consume these settings:

```powershell
docker compose -f docker-compose.dev.yml up -d migrate api web
```

Then open `http://localhost:3000/en/account/github`, link the GitHub identity if it
is not already a sign-in method, install the App on the personal account with
**All repositories**, and select **Authorize installed App**. Organization installs
must use **Only select repositories**. This last step
uses an explicit `redirect_uri`, so the same registration can keep both production
and localhost callback URLs. The same App is used if **Repository administration**
is connected later; that second button is a separate ai-stp consent, not a second
GitHub App. Use only a disposable repository for the make-public evidence test.

## User flow and support

1. The account first links its GitHub sign-in identity.
2. **Source access** starts the App installation and authorization as separate steps.
   The user selects repositories, then explicitly authorizes the installed App using
   the configured callback. GitHub's OAuth-during-installation option stays disabled,
   because GitHub otherwise chooses the App's first callback URL. The web UI keeps
   the flow in a separate window and refreshes the originating account page.
   Organization approval produces `pending_approval`, not success.
3. **Repository administration** is a separate in-product connection using the same
   App. It does not invite anyone or change visibility by itself.
4. Every invitation or make-public action displays a plan. Make-public requires the
   exact `owner/name` and a separate affirmative confirmation.
5. Disconnect removes local token ciphertext and blocks new source or action calls.
   The user may also revoke the App in GitHub; the next status/read call then reports
   reauthorization required.

Never ask users to paste a personal access token. Never put a token, private
repository URL, or raw archive coordinate in a browser URL, passport, audit event,
log, support screenshot, or error response.

## Disable and rollback

To disable new operations, remove the four Connector settings or set the deployment
feature off at the API boundary. Keep connector/source-binding/action tables and all
published artifact bytes. Existing ai-stp grants remain readable according to their
normal rules; only new GitHub reads and mutations fail closed. Restore the previous
application release and settings to roll back code. Do not delete tokens or rows as a
rollback shortcut.

## Evidence

Local PostgreSQL tests prove persistence, idempotency, refusal paths and that no real
GitHub repository is mutated. Before release, record a separate live-evidence entry
with the deployed commit, App slug, installation account, selected disposable
repository IDs, callback result, organization-approval result and one reversible
make-public test. Redact tokens, client secrets and private coordinates. A live test
must use a disposable repository whose history may safely become public.
