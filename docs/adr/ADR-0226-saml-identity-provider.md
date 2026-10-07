---
description: "A SAML 2.0 IdP is a sixth named sign-in provider feeding validated assertions into the shared identity pipeline; verification is pinned to configured certificates."
last_verified: "2026-10-06"
---

# ADR-0226: SAML sign-in is a named provider with certificate-pinned assertion validation

Status: accepted. Implemented in `ai_stp_api.slices.auth.saml`,
`slices.auth.router` (`/v1/auth/saml/login`, `/v1/auth/saml/acs`,
`/v1/auth/saml/metadata`), `AuthSettings` (`AI_STP_AUTH_SAML_*`), and the
`saml_sso_request` table.

## Context

Enterprise deployments (#220) must sign in through a corporate identity
provider that cannot serve OIDC — ADFS, older Shibboleth, some PingFederate
installations are SAML-only. ADR-0218 deliberately left SAML out of the OIDC
provider stack: there is no discovery document, no PKCE, no token endpoint —
the IdP answers with a signed XML assertion posted by the browser instead.

The load-bearing requirements from the issue:

- subject mapping must not use email as the sole identity key;
- assertions must be cryptographically verified against the configured IdP
  certificate set, not any certificate carried inside the response (that
  shape is the signature-wrapping attack);
- flow state must survive a cross-site form POST where SameSite=Lax keeps
  the session cookie at home;
- configuration (entity id, metadata, certificates, ACS, claim mapping)
  must be deployable through the existing `AI_STP_AUTH_*` settings without
  new secrets — IdP signing certificates are public material;
- the SAML path must not weaken session, CSRF, linking, or audit
  invariants.

## Options

- Extend the Authlib OIDC machinery to speak SAML. Rejected: SAML has no
  `authorize_access_token`; faking one inside the OIDC provider contract
  would blur the protocol boundary ADR-0218 drew.
- `python3-saml` / `pysaml2`. Rejected for this codebase: both depend on the
  native `libxmlsec1` toolchain, which is not part of the deploy or dev
  images, and they own the whole login flow rather than feeding our
  identity pipeline.
- A dedicated SAML adapter — `signxml` (pure-Python XMLDSig over `lxml` and
  `cryptography`, both already depended on) for verification only — that
  normalizes assertions into `ProviderProfile` and reuses
  `resolve_login_identity`, step-up link, session issuance, and audit
  unchanged.

## Decision

`saml` is a sixth named provider in the contract `OAuthProvider` literal
and `SUPPORTED_PROVIDERS`. It is enabled by
`AI_STP_AUTH_SAML_IDP_METADATA_URL` alone, or by
`AI_STP_AUTH_SAML_IDP_SSO_URL` plus `AI_STP_AUTH_SAML_IDP_CERTIFICATES`;
explicit fields override what fetched metadata says. One IdP per
deployment.

Flow. `GET /v1/auth/saml/login` persists a `saml_sso_request` row and
redirects the browser to the IdP SSO URL with a DEFLATE+base64
`AuthnRequest` (HTTP-Redirect binding) and a random `RelayState`. The IdP
POSTs `SAMLResponse` + `RelayState` to `POST /v1/auth/saml/acs`; the row
carries flow (`login`/`link`), client hint, `return_to`, the link target
account, and the remembered web device — everything the cross-site POST
cannot read from a SameSite=Lax session cookie. `GET
/v1/auth/saml/metadata` serves the SP EntityDescriptor for IdP-side
registration.

Validation (any failure is a uniform `authentication failed` to the
browser, with a log-safe machine `reason` for audit): bounded size, strict
base64, hardened XML parse, `Response` root, `StatusCode = Success`,
exactly one assertion, then signature verification that additionally
requires the signature's `Reference/@URI` to name the Response or
Assertion element's ID and that ID to occur once in the document — the
"see what is signed" check that defeats grafted/wrapped signatures.
Issuer, audience (SP entity id), `Recipient`/`Destination` (ACS URL),
`InResponseTo` (the pending request id), bearer subject confirmation, and
`NotBefore`/`NotOnOrAfter` with five minutes of skew are all enforced.
Replay is closed twice: `InResponseTo` must match a live pending request,
and the row's `assertion_id` is written exactly once under a conditional
update.

Identity. The stored `provider_subject` is `{idp_host}:{NameID}` — the
same subject-qualification pattern ADR-0223 applied to per-instance GitLab
ids, so a re-pointed IdP orphans rather than collides. Email comes from
the configured claim mapping (`saml_attribute_email`,
`saml_attribute_display_name`; AD FS claim URIs by default) and is marked
verified because the corporate IdP's signed assertion is the verification
source. From `ProviderProfile` onward the pipeline is identical to OIDC:
same `oauth_identity` row, same account resolution, same step-up link,
same opaque `AccountSession` cookies.

Restriction. `AI_STP_AUTH_SAML_ORGANIZATION_ID` binds the deployment to
one organization: a login is admitted when the assertion email matches the
org's `allowed_email_domains` or a `CorporateProvisionedIdentity` row
exists for it; failure denies before any account is created.
`AI_STP_AUTH_SAML_IDP_ONLY=true` makes `provider_enabled` answer `False`
for every other provider — one gate covers login, callback, step-up link,
and device authorization — and refuses to start if it would lock out
every provider.

Audit. Success and failure emit `auth.saml_login` on the request row with
only `provider`, `flow`, and a machine `reason`. Assertions, certificates,
and tokens never enter payloads or logs — the payload keys would survive
the redaction list, so they are simply never passed.

## Consequences

- The contract literal gains `saml`; the web SSO surface picks it up
  through `AI_STP_AUTH_SSO_PROVIDERS` (rendered only in the
  `corporate_hub` build). New linked identities carry `provider="saml"`,
  and unlink works unchanged because it is provider-agnostic.
- SAML has no OIDC-style logout URL contract here: `POST /v1/auth/logout`
  revokes the local session exactly as before; IdP-side session
  termination is the operator's IdP configuration and is documented in the
  runbook rather than implemented as SLO (single logout requires a second
  signed-request profile we do not need).
- Certificate rotation is an operator procedure, not a code path:
  `saml_idp_certificates` accepts a PEM bundle, so the overlap window is
  "add the new certificate alongside the old, cut the IdP over, remove the
  old" — covered in `docs/operations/runbooks/saml-sso.md`.
- `signxml` + `lxml` join the API dependency set; verification is pinned
  to configured certificates (`ExtensionPolicy.permit_all` — corporate
  signing certs regularly carry no KeyUsage) and to the expected signed
  node, so neither "any valid signature" nor a response-embedded KeyInfo
  certificate is ever trusted.
- Encrypted assertions (`EncryptedAssertion`) and unsolicited
  (IdP-initiated) responses are deliberately unsupported: both fail
  `assertion_count` or `in_response_to` validation. SP-initiated POST
  binding is the whole surface.

## Revisit conditions

- A deployment needs more than one SAML IdP — then provider naming moves
  to operator-defined names per ADR-0218's revisit clause, and the
  IdP-qualified subject format already separates their namespaces.
- SCIM directory sync or employee lifecycle management lands — explicitly
  out of scope for #220; it would build on the same `CorporateProvisionedIdentity`
  seam this ADR reuses.
- IdP-initiated SSO or SLO become requirements — both need additional
  protocol surface (no `InResponseTo` correlation for the former, signed
  logout requests for the latter) and must re-open this decision.
