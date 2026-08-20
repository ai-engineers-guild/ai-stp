"""Sign-in payloads (issue #71, SPEC-002, SPEC-011 REQ-1108).

The CLI signs in through a **device-code flow brokered by our own platform**,
not a loopback redirect: the agent commonly runs over SSH and inside containers,
where a local listener has nowhere to bind. The platform is the party that talks
to Google and GitHub; the CLI only asks for a code, opens a browser at our
verification URI and polls.

Two consequences are load-bearing:

- The CLI never sees a password or a provider token (SPEC-011 REQ-1108). It
  receives our own credentials, and only after a human approved the request in
  a browser.
- The device's Ed25519 public key binds at **exchange**, not at start. Before a
  human approves there is no account to bind it to, and accepting a key earlier
  would let an unauthenticated caller park keys against pending codes.

Token fields carry `repr=False`. They are secrets: they belong in the OS
credential store and must never reach a log, a `--json` envelope, a fixture or
an agent's context (SPEC-002 security section). Excluding them from `repr` stops
the most common accident — an object interpolated into a log line.
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.http import (
    IdempotencyKey,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_foundation.ids import stable_id_pattern

#: The two identity providers of the MVP (SPEC-002 REQ-1002). A third one is a
#: new enum value and therefore a schema change, not a configuration flag.
type OAuthProvider = Literal["google", "github"]

#: Opaque to the CLI, which echoes it back verbatim while polling. Bounded so it
#: cannot become an unbounded key on either side.
DEVICE_CODE_PATTERN: Final[str] = r"^[A-Za-z0-9_-]{32,256}$"

#: Typed by a human from a terminal into a browser, so the alphabet excludes
#: `I`, `L`, `O` and `U` — the same Crockford set the ULID suffix uses. The
#: grouping is cosmetic but part of the contract: a client must not normalise
#: the separator away and then compare.
USER_CODE_PATTERN: Final[str] = r"^[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$"

#: An Ed25519 public key is exactly 32 bytes: 43 base64 characters plus one pad,
#: matching the signature convention in `ai_stp_assurance.attestation`.
PUBLIC_KEY_PATTERN: Final[str] = r"^[A-Za-z0-9+/]{43}=$"

type DeviceCode = Annotated[str, Field(pattern=DEVICE_CODE_PATTERN)]
type UserCode = Annotated[str, Field(pattern=USER_CODE_PATTERN)]
type PublicKey = Annotated[str, Field(pattern=PUBLIC_KEY_PATTERN)]
type AccountId = Annotated[str, Field(pattern=stable_id_pattern("account"))]
type DeviceId = Annotated[str, Field(pattern=stable_id_pattern("device"))]
type DisplayName = Annotated[str, Field(min_length=1, max_length=100)]


class DeviceAuthorizationRequest(BaseModel):
    """Start a sign-in. Carries the provider and the key that makes it repeatable.

    Deliberately not the device identity: at this point no human has approved
    anything, so there is nothing to bind a key to and no reason to accept one.

    `idempotency_key` is here because this route creates. `http-api.md` has always
    required one for creates, and `DeviceRevokeRequest` has always carried one —
    this request simply did not, so a client whose response was lost had no way
    to retry without asking for a second authorization. The value is chosen by
    the client and opaque to the server, which is what lets one logical start
    survive any number of transport attempts.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    provider: OAuthProvider
    idempotency_key: IdempotencyKey


class DeviceAuthorizationResponse(BaseModel):
    """What the CLI shows the user and then polls with."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    device_code: Annotated[DeviceCode, Field(repr=False)]
    user_code: UserCode

    #: Where the CLI sends the browser. Ours, never the provider's: the platform
    #: brokers the provider exchange, so the CLI never handles a provider token.
    #: ``http://localhost`` is allowed for local development; production must use HTTPS.
    verification_uri: Annotated[
        str, Field(pattern=r"^(https://[^\s]+|http://localhost(:[0-9]+)?(/[^\s]*)?)$")
    ]

    #: The same page with the code already filled in, so the usual path needs no
    #: typing. The plain `verification_uri` and `user_code` stay required, since
    #: this one is useless on a machine that cannot open a browser.
    verification_uri_complete: Annotated[
        str, Field(pattern=r"^(https://[^\s]+|http://localhost(:[0-9]+)?(/[^\s]*)?)$")
    ]

    #: Seconds. Bounded so a server cannot hand out an effectively immortal code
    #: or one that expires before a human can act.
    expires_in: Annotated[int, Field(ge=60, le=1800)]

    #: Minimum seconds between polls. The CLI must honour it; the server answers
    #: `AI_STP_RATE_LIMITED` if it does not.
    interval: Annotated[int, Field(ge=1, le=60)]


class DeviceTokenRequest(BaseModel):
    """Poll for the result and, on success, bind this device.

    The key travels here rather than at start, so a device identity only ever
    reaches the account a human actually approved.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    device_code: Annotated[DeviceCode, Field(repr=False)]
    device_id: DeviceId
    public_key: PublicKey
    display_name: DisplayName


class DeviceTokenResponse(BaseModel):
    """Credentials for one approved device.

    A pending, expired or declined poll is **not** this payload: it is a typed
    error (`AI_STP_AUTHORIZATION_PENDING`, `_EXPIRED`, `_DECLINED`), so a client
    can never mistake "not yet" for "no credentials issued".
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    access_token: Annotated[str, Field(min_length=1, repr=False)]
    refresh_token: Annotated[str, Field(min_length=1, repr=False)]
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: Annotated[int, Field(ge=60, le=86400)]
    account_id: AccountId
    device_id: DeviceId


class OAuthCallbackResult(BaseModel):
    """The outcome of the browser half, as the web surface reads it.

    `conflict` is a first-class outcome rather than an error: SPEC-002 REQ-202
    forbids silently merging two populated accounts, so the user has to be told
    and asked rather than have a merge happen behind them.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    provider: OAuthProvider
    status: Literal["linked", "pending", "conflict"]

    #: Absent while `pending` and on `conflict`: naming the account a conflicting
    #: address already belongs to would disclose that it exists.
    account_id: AccountId | None
    completed_at: Timestamp


class AuthMeResponse(BaseModel):
    """GET /v1/auth/me resource body."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    account_id: AccountId
    device_id: DeviceId | None = None


class AuthLogoutResponse(BaseModel):
    """POST /v1/auth/logout resource body."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    revoked: bool


class SystemVersionResponse(BaseModel):
    """GET /v1/system/version resource body (safe diagnostics only)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    version: Annotated[str, Field(min_length=1, max_length=64)]
    environment: Annotated[str, Field(min_length=1, max_length=32)]
    git_commit: str | None = None
    schema_revision: str | None = None


class DeviceChallengeRequest(BaseModel):
    """POST /v1/devices/challenge body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    public_key: PublicKey


class DeviceChallengeResponse(BaseModel):
    """POST /v1/devices/challenge resource body."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    nonce: Annotated[str, Field(min_length=16, max_length=2048)]
    expires_in: Annotated[int, Field(ge=30, le=3600)]
