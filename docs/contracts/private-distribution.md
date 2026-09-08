---
description: "Private upload, exact access reads and owner visibility plans shared with the platform owner."
last_verified: "2026-09-08"
---

# Private distribution

SPEC-071 owns the agent journey; ADR-0169 separates distribution visibility from
immutable passport bytes. This document defines the required API boundary. Client
transport tests exercise it; server deployment is a separate acceptance step.

The CLI always sends `PublicationPlanCreateRequest.visibility`, choosing `private`
when the option is omitted. `PublicationPlanResponse.visibility` must echo that
choice and contribute to `plan_hash`. A legacy response decoded as public cannot
satisfy a private request. Creating a plan grants no public access. Artifact binding,
validation and confirmation retain the existing publication lifecycle. Private
distribution needs no public publisher profile. Publication must not implicitly
change distribution visibility of an already stored version.

Authenticated `GET /v1/catalog/{components|setups}/{stable_id}/versions/{X.Y}/private`
returns the catalog `PrivateVersionResponse`; `CliPrivateVersionResponse` is an
import alias of that model, not a second wire shape. Exact kind, stable ID and
version are read from the verified passport and compared with the requested
coordinates. The response's catalog verification axes stay independent; the CLI
assigns `local_owner_or_pinned` only to its authorized local acquisition view.
Historical passport visibility may be public or private; the private endpoint
asserts the current private distribution after owner/grant authorization.
Exact artifact bytes are `GET /v1/catalog/.../artifact` with the same session.
Anonymous public version/artifact 404 is what permits the authenticated retry;
the CLI does not invent a second private prefix. Visibility plans remain the
`/v1/access/visibility/plans` boundary below and are not the live version route.

`registry version`, `fetch` and `acquire` accept explicit private access. Anonymous
lookup sends no token; only public 404 permits authenticated lookup. Private cache
keys include normalized endpoint and account. Online denial cannot become cached
success. Explicit offline acquisition uses already acquired bytes: revocation
restricts future reads.

`setup compose` creates a private local SetupVersion. Exact catalog pins use the
same anonymous-then-authorized lookup, preserving each component digest. Composition
grants no access and changes no source component's visibility.

The owner visibility boundary is:

| Request | Body / result |
|---|---|
| `POST /v1/access/visibility/plans` | `VisibilityPlanCreateRequest` / `VisibilityPlanResponse` |
| `GET /v1/access/visibility/plans/{plan_id}` | `VisibilityPlanResponse` |
| `POST /v1/access/visibility/plans/{plan_id}/confirm` | `PublicationConfirmRequest` / `VisibilityPlanResponse` |

Visibility models belong to `ai_stp_contracts.private_access`. Server plans are
stored in `visibility_plan` and expire after 30 minutes. Creating the same
actor/idempotency key with different coordinates returns conflict; confirmation
rechecks current ownership and device. A stale visibility or passport returns
`refused`, expiry returns `expired`, and neither changes the version. The plan binds exact object,
version and passport digest, previous and requested visibility, actor, device,
expiry and effects. States are `planned`, `applied`, `expired`, `refused`. Confirm
rechecks owner authority, hash, device, expiry and prior visibility under a
transactional lock. Repeating an applied plan returns the same result. Opening a
setup refuses while a required pin is private. A recipient grant cannot create
or confirm a visibility plan.

Agents use `publication visibility plan`, `status`, `confirm`. Visibility is always
explicit. Confirmation requires an explicit flag and exact hash. The CLI neither
rewrites local versions nor substitutes ordinary public publication for a missing
endpoint.

A public version response may carry a historically private passport only with
explicit `distribution_visibility=public`. Passport bytes and digest stay unchanged.
A private passport without that assertion is refused; legacy public passports stay
readable. Search, object and version projections reflect current server visibility.

Server acceptance covers private storage and binding, owner and recipient reads,
stranger denial before storage access, invitation acceptance, revocation, opening
private to public with unchanged passport and artifact digests, and closing public
to private for future reads. A mock or a successful plan request does not prove
that these server effects are deployed.
