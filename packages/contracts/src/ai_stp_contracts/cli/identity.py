"""The device key, the platform session and device approval."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.auth import AccountId, DeviceId, OAuthProvider, PublicKey
from ai_stp_contracts.http import Timestamp, open_wire_object
from ai_stp_contracts.model import ContractModel

#: Where a secret actually lives on this installation (`ADR-0058`). Reported
#: rather than assumed: a caller that believes a refresh token is encrypted at
#: rest when it is a file has been told something false, and the difference
#: changes what it is safe to do on a shared machine.
type CredentialStore = Literal["os_keyring", "file"]


#: Local view of one device identity. `revoked` is set locally by an explicit
#: reset and by a server answer once #75 can ask; it stops future cloud work and
#: leaves local reads alone (`SPEC-002` REQ-205).
type LocalDeviceState = Literal["active", "revoked"]


class DeviceIdentity(ContractModel):
    """This installation's device identity, as the CLI can see it offline.

    Created on first run without an account: the key proves which device a
    later sync event or attestation came from, and it exists before any cloud
    login. Only public material is representable — the private key has no field
    here and cannot be printed by construction.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    device_id: DeviceId
    public_key: PublicKey

    #: A short, human-comparable form of the public key, so a person can check
    #: the device list in the web against this machine without reading 43
    #: base64 characters.
    key_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{2}(:[0-9a-f]{2}){15}$")]

    created_at: Timestamp
    state: LocalDeviceState

    #: Where the private key is kept, and why that tier was chosen. Never
    #: silent: `ADR-0058` makes the tier part of the answer.
    credential_store: CredentialStore
    credential_store_detail: Annotated[str, Field(min_length=1)]

    #: Identities this installation has retired, oldest first. Kept and reported
    #: so a retired identifier cannot come back and so the account owner can
    #: match a device row they no longer recognise against this machine.
    retired_device_ids: list[DeviceId]


#: What this installation's relationship with the platform actually is
#: (`SPEC-011`, issue #75). Four values rather than a boolean, because the
#: repairs differ: `expired` is fixed by signing in again, `revoked` needs a new
#: device key as well (`SPEC-002` REQ-207), and `local_only` is not a problem at
#: all — the whole local contour works without an account.
type SessionState = Literal["local_only", "authenticated", "expired", "revoked"]


class AuthStatus(ContractModel):
    """Whether this installation currently holds cloud credentials.

    Distinct from `DeviceIdentity`: a device identity always exists, a session
    may not. Reporting them as one fact would make "no account yet" and "no
    device identity" indistinguishable, and their next actions differ.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1

    #: One field, not a boolean beside it: `signed_in` and a state can disagree,
    #: and then a caller has to decide which to believe.
    state: SessionState

    #: Present only while signed in. Absent is not an error: the whole local
    #: contour works without an account (`offline-capability.md`).
    account_id: AccountId | None

    #: When the stored access credential stops being usable, if one is held.
    expires_at: Timestamp | None

    #: Where a held credential is kept. Absent when none is held — naming a
    #: store for a secret that does not exist would suggest one does.
    credential_store: CredentialStore | None


class DeviceApproval(ContractModel):
    """What a person must approve before a sign-in can complete (issue #75).

    Returned rather than waited on. `#72` fixed that the CLI never blocks for a
    human decision — a command that polled until someone walked to their browser
    would hang in CI and in a container, which is the same reason the sign-in is
    a device-code flow and not a loopback redirect. So this is the first half of
    the answer, and `auth complete --wait` is the second.

    No secret is representable here. The device code the client polls with is
    kept in the credential store, not published: it is the bearer of the
    pending authorization.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    provider: OAuthProvider

    #: Typed by a human from a terminal into a browser.
    user_code: Annotated[str, Field(min_length=1)]

    verification_uri: Annotated[str, Field(min_length=1)]

    #: The same page with the code already filled in. Useless on a machine that
    #: cannot open a browser, which is why the plain pair above stays required.
    verification_uri_complete: Annotated[str, Field(min_length=1)]

    expires_in: Annotated[int, Field(ge=1)]

    #: Whether a browser was actually opened. Not an error when false — that is
    #: the normal case over SSH — but the agent needs to know whether to tell
    #: the user to open the address themselves.
    browser_opened: bool

    device_id: DeviceId
