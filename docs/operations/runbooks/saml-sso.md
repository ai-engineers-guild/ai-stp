---
description: "Operate SAML 2.0 corporate SSO: configuration, certificate rotation, logout, linking, organization restriction, and failure triage."
last_verified: "2026-10-06"
---

# SAML 2.0 SSO (corporate IdP)

Covers the `saml` sign-in provider (ADR-0226): SP-initiated SSO only — login
redirects to the IdP, the IdP POSTs a signed assertion to
`POST /v1/auth/saml/acs`, and the account/session pipeline is identical to the
OIDC providers after that point.

## Configuration

All values are deployment settings (`AI_STP_AUTH_*`); IdP signing certificates
are public material, not secrets.

| Variable | Purpose |
| --- | --- |
| `AI_STP_AUTH_SAML_IDP_METADATA_URL` | IdP EntityDescriptor URL; fetches entity id, SSO endpoint, and signing certificates at startup. One knob for the whole IdP profile. |
| `AI_STP_AUTH_SAML_IDP_SSO_URL` | IdP SSO endpoint when metadata is not published. Requires `SAML_IDP_CERTIFICATES`. |
| `AI_STP_AUTH_SAML_IDP_ENTITY_ID` | Expected `Issuer` in assertions; overrides the metadata value. Strongly recommended with a metadata URL — pins the issuer. |
| `AI_STP_AUTH_SAML_IDP_CERTIFICATES` | IdP signing certificates: inline PEM bundle or a filesystem path to one. Multiple blocks = the rotation overlap. |
| `AI_STP_AUTH_SAML_SP_ENTITY_ID` | Our entity id registered at the IdP. Empty derives `{public_base}/v1/auth/saml/metadata` — the same URL the metadata endpoint serves. |
| `AI_STP_AUTH_SAML_ATTRIBUTE_EMAIL` | Comma-separated assertion attribute names for email; first present wins. Defaults cover AD FS claim URIs, `email`/`mail`, and the LDAP OIDs SimpleSAMLphp emits after `name2oid` (`mail`, pkcs9 `emailAddress`). |
| `AI_STP_AUTH_SAML_ATTRIBUTE_DISPLAY_NAME` | Same for the display name claim. |
| `AI_STP_AUTH_SAML_ORGANIZATION_ID` | Restrict logins to one organization (below). |
| `AI_STP_AUTH_SAML_IDP_ONLY` | `true` makes every other provider unreachable (login, callback, link, device). Refuses to start if the IdP itself is not configured — no total lockout. |

The ACS URL the IdP must register is `{AI_STP_AUTH_OAUTH_REDIRECT_BASE_URL or
PUBLIC_BASE_URL}/v1/auth/saml/acs` (POST binding); the SP EntityDescriptor the
IdP imports is served at `GET /v1/auth/saml/metadata`. Register the ACS URL
byte-identically — `Recipient`/`Destination` matching is exact.

Web side: `AI_STP_AUTH_SSO_PROVIDERS=saml` renders the SSO button
(`corporate_hub` build). For IdP-only mode set `AI_STP_AUTH_PROVIDERS=` (empty)
and `AI_STP_AUTH_SSO_PROVIDERS=saml` alongside `AI_STP_AUTH_SAML_IDP_ONLY=true`,
so the UI matches the API's enforcement.

## Subject mapping, linking, unlinking

Accounts are keyed on `oauth_identity(provider="saml",
provider_subject="{idp_host}:{NameID}")` — the stable IdP subject, never the
email alone. A re-pointed or reinstalled IdP orphans old identities rather
than colliding. An authenticated user links SAML through
`GET /v1/auth/link/saml` (same step-up flow as OAuth providers) and unlinks
through the existing identity endpoint; unlinking the last identity behaves
exactly as it does for OIDC providers.

## Organization restriction

With `AI_STP_AUTH_SAML_ORGANIZATION_ID` set, an assertion is admitted when its
email matches the org's `allowed_email_domains`, or when a
`CorporateProvisionedIdentity` row exists for that email in the org.
Off-domain, unprovisioned logins are rejected before any account is created;
the browser sees the same generic `status=error` as every other failure —
nothing about org membership is disclosed.

## Certificate rotation

Certificates are validated at startup; a deployment that cannot resolve any
usable certificate refuses to boot rather than accept unsigned assertions.

1. Obtain the IdP's **next** signing certificate (IdP admin console or the new
   metadata document).
2. Append it to `AI_STP_AUTH_SAML_IDP_CERTIFICATES` alongside the current one
   (bundle) or place both PEM blocks in the file — restart/redeploy the api.
   Assertions signed by either certificate now verify.
3. Cut the IdP over to the new certificate.
4. Confirm a real login succeeds, then remove the old certificate and
   restart again. The overlap is what makes the rotation zero-downtime.

If the IdP publishes metadata, `AI_STP_AUTH_SAML_IDP_METADATA_URL` re-reads
certificates at each api start; still stage the overlap in the IdP's metadata
before cutting over, the same sequence applies.

## Logout

`POST /v1/auth/logout` revokes the ai-stp session and clears cookies — the
local invariant is unchanged. SAML single logout (SLO) is intentionally not
implemented: terminating the IdP-side session is an IdP operation (or the
IdP's own logout URL, configured IdP-side). Operators who need global logout
should enable the IdP's logout endpoint and document it for users; the local
session still ends at `POST /v1/auth/logout`.

## Failure map

Every ACS rejection redirects to the login page with `status=error` and writes
one `auth.saml_login` audit row carrying a machine `reason` — assertions,
certificates, and tokens never appear in logs or audit payloads.

| Reason (audit `reason`, log `saml_acs_failed`) | Cause |
| --- | --- |
| `relay_state_unknown` | no pending request for the RelayState — response arrived without a login start, or RelayState tampered |
| `request_expired` | pending request older than 10 minutes |
| `request_consumed` | replay: the response was already consumed |
| `response_not_base64` / `response_not_xml` / `response_size` | malformed POST body |
| `response_wrong_root` | XML root is not a SAML `Response` |
| `status_not_success` | IdP reported failure — check the IdP's own log for the auth error |
| `assertion_count` | zero or several assertions (wrapping attempts land here) |
| `signature_invalid` | unsigned, wrong cert, bad signature, or signature covering an unrelated node |
| `issuer_mismatch` | assertion `Issuer` is not the configured entity id |
| `audience_mismatch` | `AudienceRestriction` does not name our SP entity id |
| `recipient_mismatch` | `Recipient` is not our ACS URL |
| `in_response_to_mismatch` | response does not answer the pending request — unsolicited responses land here |
| `assertion_expired` / `assertion_not_yet_valid` / `confirmation_expired` | clock skew beyond 5 minutes, or a stale/replayed response |
| `subject_missing` / `subject_confirmation_missing` | no bearer `SubjectConfirmation` |
| `assertion_missing_field` / `email_attribute_missing` | subject or mapped email claim absent — fix the IdP's claim mapping or `SAML_ATTRIBUTE_EMAIL` |
| `organization_denied` | `SAML_ORGANIZATION_ID` set and the email is neither in-domain nor provisioned |

Boot failures: the api refuses to start when SAML is enabled but the IdP
profile is incomplete (`incomplete SAML IdP configuration`) or
`saml_idp_only` would leave no working provider.

## Deterministic verification

`tests/unit/test_saml.py` signs fixture responses with a throwaway key pair —
no IdP needed — and `tests/api/platform/test_saml_routes.py` runs the full
login → ACS → session chain against a migrated database. For a live check
against a real IdP, configure the profile above and walk the browser flow;
`GET /v1/auth/saml/metadata` returning XML is the cheapest smoke signal.
