---
description: "Operator runbook for the single GitHub App used by source access and repository actions."
last_verified: "2026-09-08"
---

# GitHub Connector operations

This runbook configures one GitHub App for issues 181–186. It is not a GitHub
Actions workflow. The App is installed only on repositories selected by the account
owner. The product still treats source reading and repository administration as
separate consent records and requires a new durable confirmation plan for every
mutation.

## App registration

Create one GitHub App owned by the deployment account or organization. Configure:

- repository permission `Metadata: Read-only`;
- repository permission `Contents: Read-only`;
- repository permission `Administration: Read and write`;
- user authorization enabled, so the platform receives a short-lived user token;
- installation repository selection set to `Only select repositories`;
- callback URL exactly `<public-base>/v1/connectors/github/callback`.

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

Use one GitHub App, not two. In GitHub, open **Settings → Developer settings →
GitHub Apps → New GitHub App** and use:

- homepage URL `http://localhost:3000`;
- callback URL `http://localhost:8000/v1/connectors/github/callback`, with wildcard
  matching disabled;
- **Request user authorization (OAuth) during installation** enabled;
- expiring user authorization tokens enabled;
- webhooks disabled; this connector does not consume webhook events;
- repository permissions `Metadata: Read-only`, `Contents: Read-only`, and
  `Administration: Read and write`;
- **Any account** for the public ai-stp service, so any GitHub user or organization
  can install the App. Keep repository selection limited during local testing.

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

Then sign in to the local site with GitHub, open
`http://localhost:3000/en/account/github`, select **Source access**, and install the
App on one disposable repository using **Only select repositories**. The same App
is used if **Repository administration** is connected later; that second button is
a separate ai-stp consent, not a second GitHub App. Use only a disposable repository
for the make-public evidence test.

## User flow and support

1. The account first links its GitHub sign-in identity.
2. **Source access** starts the App installation/authorization flow. The user selects
   repositories. Organization approval produces `pending_approval`, not success.
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
