"""The device identity: one stable ID and one Ed25519 key per installation.

`SPEC-002` REQ-204 gives every device a stable identifier, a public key, and a
revocation state. The key proves which device a sync event or an attestation
came from — not that the device behaved honestly (`ADR-0007`). `ai_stp_assurance`
already fixed the signature format and deferred key handling to exactly here.

The identity is created on first run, offline, before any account exists, which
is why it is not part of the sign-in commands: a machine has an identity whether
or not anyone ever logs in.

Public material lives in a plain file under the data directory; the private key
lives in the credential store chosen by `secrets.py`. The split is the point —
the public half must be readable to be reported, and the private half has no
field on any model in this repository, so it cannot be printed by construction.
"""

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, cast

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import bootstrap_lock, device_file, read_private, write_private
from ai_stp_cli.secrets import (
    SecretStore,
    drop_everywhere,
    load_json,
    open_store,
    promote,
    store_json,
)
from ai_stp_contracts.machine_help import DeviceIdentity, LocalDeviceState
from ai_stp_foundation.ids import is_valid_id, new_id
from ai_stp_foundation.timestamps import format_timestamp

#: The entry name earlier versions used for every installation on a machine.
#: Kept only so an existing key can be adopted once; nothing writes it any more.
LEGACY_KEY_ENTRY: Final[str] = "device-key"


def key_entry(device_id: str) -> str:
    """The entry name holding one installation's private key.

    Named per device, because the identity is per installation and the operating
    system's credential store is per **user**. Under one shared name a second
    installation — another `XDG_DATA_HOME`, a container mount, a smoke lane —
    mints its own identity and overwrites the entry, and the first installation
    is left with a record whose key is gone. That is not hypothetical: this
    repository's own `just check` did it to the developer's keyring.

    Joined with a dot rather than a colon: on the file tier the entry name is a
    file name, and a colon is not a legal one on Windows — whose credential
    store this module already lists as trusted.
    """
    return f"{LEGACY_KEY_ENTRY}.{device_id}"


#: An Ed25519 seed is 32 bytes; the stored document keeps it base64 so the
#: entry is one printable string in every store.
_SEED_FIELD: Final[str] = "seed"


def _moment() -> str:
    """Now, in the one timestamp form the contract accepts."""
    return format_timestamp(datetime.now(UTC))


@dataclass(frozen=True)
class Identity:
    """One device identity and the store its private half came from."""

    device_id: str
    private_key: SigningKey
    created_at: str
    state: LocalDeviceState
    store: SecretStore

    @property
    def public_key(self) -> VerifyKey:
        return self.private_key.verify_key

    def sign(self, payload: bytes) -> bytes:
        return self.private_key.sign(payload).signature

    def report(self) -> DeviceIdentity:
        """The identity as a machine contract, with no private material in it."""
        return DeviceIdentity(
            device_id=self.device_id,
            public_key=encode_public_key(self.public_key),
            key_fingerprint=fingerprint(self.public_key),
            created_at=self.created_at,
            state=self.state,
            credential_store=self.store.tier,
            credential_store_detail=self.store.detail,
            retired_device_ids=[item.device_id for item in retired_identities()],
        )


def encode_public_key(key: VerifyKey) -> str:
    """Base64 of the 32 raw bytes, matching `auth.PUBLIC_KEY_PATTERN`."""
    return base64.b64encode(raw_public_bytes(key)).decode("ascii")


def raw_public_bytes(key: VerifyKey) -> bytes:
    return bytes(key)


def fingerprint(key: VerifyKey) -> str:
    """A short colon-separated form a person can compare by eye.

    The device list in the web shows the same digest, so a user can tell which
    row is the machine in front of them without reading 43 base64 characters.
    """
    digest = hashlib.sha256(raw_public_bytes(key)).digest()[:16]
    return ":".join(f"{byte:02x}" for byte in digest)


def verify(key: VerifyKey, payload: bytes, signature: bytes) -> bool:
    """Whether `signature` was produced for `payload` by the matching key."""
    try:
        key.verify(payload, signature)
    except (BadSignatureError, TypeError, ValueError):
        return False
    return True


@dataclass(frozen=True)
class Retired:
    """An identity this installation has stopped using."""

    device_id: str
    retired_at: str


@dataclass(frozen=True)
class Record:
    """The public half of the device identity, as stored on disk."""

    device_id: str
    created_at: str
    state: LocalDeviceState

    #: Every identity this installation has retired. Kept so a retired
    #: identifier can never come back: `#73` requires that a revoked cloud
    #: device is not silently reused, and not reusing something means
    #: remembering it. Nothing secret is here — a retired public identifier is
    #: exactly what the account owner already sees in their device list.
    retired: tuple[Retired, ...] = ()


def _read_public_record() -> Record | None:
    path = device_file()
    if not path.exists():
        return None
    try:
        parsed: object = json.loads(read_private(path))
    except ValueError as error:
        raise _unreadable(error) from error
    if not isinstance(parsed, dict):
        raise _unreadable(TypeError("device record is not an object"))
    document = cast(dict[str, object], parsed)

    device_id = str(document.get("device_id", ""))
    if not is_valid_id(device_id, "device"):
        raise _unreadable(ValueError("device record carries no valid device id"))
    state = str(document.get("state", "active"))
    if state not in ("active", "revoked"):
        raise _unreadable(ValueError("device record carries an unknown state"))

    entries = document.get("retired", [])
    if not isinstance(entries, list):
        raise _unreadable(TypeError("retired identities are not a list"))
    retired = tuple(
        Retired(str(entry.get("device_id", "")), str(entry.get("retired_at", "")))
        for entry in (cast(dict[str, object], item) for item in cast(list[object], entries))
    )
    return Record(
        device_id=device_id,
        created_at=str(document.get("created_at", "")),
        state=state,
        retired=retired,
    )


def _unreadable(error: BaseException) -> CliFailure:
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "the local device record cannot be read",
        details={"exception": type(error).__name__},
        next_actions=["device reset --confirm --json"],
    )


def _write_public_record(record: Record) -> None:
    document = {
        "device_id": record.device_id,
        "created_at": record.created_at,
        "state": record.state,
        "retired": [
            {"device_id": item.device_id, "retired_at": item.retired_at} for item in record.retired
        ],
    }
    write_private(device_file(), json.dumps(document, sort_keys=True, ensure_ascii=False) + "\n")


def _load_private_key(store: SecretStore, entry: str) -> SigningKey | None:
    # If this machine has gained a real credential store since the key was
    # written, move the file copy into it before reading (`ADR-0058`).
    promote(store, entry)
    document = load_json(store, entry)
    if document is None:
        document = _adopt_legacy_entry(store, entry)
    if document is None:
        return None
    seed = document.get(_SEED_FIELD)
    if seed is None:
        raise _unreadable(ValueError("stored key material has no seed"))
    try:
        return SigningKey(base64.b64decode(seed, validate=True))
    except Exception as error:
        raise _unreadable(error) from error


def _adopt_legacy_entry(store: SecretStore, entry: str) -> dict[str, str] | None:
    """Take over the key an earlier version stored under the shared name.

    Copied and verified before the old entry goes, the same order `promote` uses.
    The old entry is then removed: leaving it would let a second installation
    adopt the same key, which is the collision this naming exists to end. An
    installation that loses the race gets a clear "record but no key" refusal
    rather than a key that silently signs for someone else's device.
    """
    promote(store, LEGACY_KEY_ENTRY)
    document = load_json(store, LEGACY_KEY_ENTRY)
    if document is None:
        return None
    store_json(store, entry, document)
    if load_json(store, entry) != document:
        raise _unreadable(ValueError("the adopted device key could not be read back"))
    drop_everywhere(store, LEGACY_KEY_ENTRY)
    return document


def _mint(store: SecretStore, retired: tuple[Retired, ...] = ()) -> Identity:
    """Create a new identity. Never reuses an identifier or a key."""
    private_key = SigningKey.generate()
    seed = bytes(private_key)
    record = Record(
        device_id=new_id("device"),
        created_at=_moment(),
        state="active",
        retired=retired,
    )
    store_json(
        store, key_entry(record.device_id), {_SEED_FIELD: base64.b64encode(seed).decode("ascii")}
    )
    _write_public_record(record)
    return Identity(record.device_id, private_key, record.created_at, record.state, store)


def current() -> tuple[Identity | None, str | None]:
    """The identity of this installation, or `None` if it has none yet.

    Creates nothing. `SPEC-009` REQ-902 says reading does not bring state into
    existence, and a command declared `read` in the registry is what an agent
    plans around: `device show` used to mint an identity, so observing the
    installation changed it. The absence of an identity is an answer.
    """
    store, warning = open_store()
    record = _read_public_record()
    if record is None:
        return None, warning
    return _identity_from(store, record), warning


def _identity_from(store: SecretStore, record: Record) -> Identity:
    private_key = _load_private_key(store, key_entry(record.device_id))
    if private_key is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the device identity has a record but no key and cannot sign",
            details={"device_id": record.device_id},
            next_actions=["device reset --confirm --json"],
        )
    return Identity(
        device_id=record.device_id,
        private_key=private_key,
        created_at=record.created_at,
        state=record.state,
        store=store,
    )


def load_or_create() -> tuple[Identity, str | None]:
    """The identity of this installation, creating it on first run.

    Idempotent: a second call returns the same identifier and the same key. The
    second element is the fallback warning from the credential store, so the
    caller can put it in the envelope rather than hide it.

    The public record is what asserts an identity exists, and the key is stored
    under that identity's own name. So there is one failure to handle rather than
    two: a **record without its key**. That is broken — a server may already know
    this `device_id`, and nothing here can sign as it any more. Re-minting
    silently would change an identity someone else has on file, so it is refused.

    There is no longer a "key without a record" case to reason about. Keys are
    named per device, so an absent record means nothing to look up, and a key
    belonging to some other installation is not reachable from here. Under the
    old shared name the two halves could disagree in both directions, and
    resolving that by replacing the stored key is precisely how one installation
    destroyed another's identity.
    """
    store, warning = open_store()
    record = _read_public_record()

    if record is None:
        # Creating is the only path that can race, so the lock is taken here
        # rather than around every call, and the record is read again under it:
        # another process may have finished the whole bootstrap while this one
        # waited.
        with bootstrap_lock():
            record = _read_public_record()
            if record is None:
                return _mint(store), warning

    return _identity_from(store, record), warning


def reset() -> tuple[Identity, str | None]:
    """Retire this identity and mint a fresh one.

    `SPEC-002` REQ-207: resuming cloud access needs a new login **and a new
    key**, so nothing is reused — not the identifier, not the key material. The
    previous private key is dropped rather than archived: keeping it would leave
    a credential that can still sign as a device the account may have revoked.

    Local data is untouched (REQ-205). Revocation is forward-acting.

    The key is dropped from **both** tiers. Dropping only the current one would
    leave a file copy of the retired key beside a freshly minted store entry, and
    `promote` refuses that disagreement rather than guess — which would strand
    the installation on the next command.
    """
    store, warning = open_store()
    previous = _read_public_record()
    retired = previous.retired if previous else ()
    if previous is not None:
        retired = (*retired, Retired(previous.device_id, _moment()))
        drop_everywhere(store, key_entry(previous.device_id))
    return _mint(store, retired), warning


def retired_identities() -> tuple[Retired, ...]:
    """Identities this installation has stopped using, oldest first."""
    record = _read_public_record()
    return record.retired if record else ()
