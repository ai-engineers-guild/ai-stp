"""Where a secret is kept, and the honest name of that place (`ADR-0058`).

Two tiers. The operating system's credential store when this machine really has
one, and an owner-only file otherwise. Which tier is in use is part of every
answer that depends on it — `device show` names it, `doctor` checks it, and a
fallback rides in the envelope's `warnings`. A silent fallback is the defect
`cli/cli#10108` and `openai/codex#14704` are both about.

**`keyring.get_keyring()` is not evidence that a secure store exists.** Measured:
with the `keyrings.alt` package installed, `PlaintextKeyring` wins backend
selection, `set_password` succeeds, and the secret lands on disk base64-encoded
while the library reports success. Trusting the library's own choice would make
this module report "operating system credential store" about a plain file. So
the selected backend is accepted only when it is one of the few that really are
backed by an OS facility, matched by module and class name.

Priority is deliberately not consulted: it is assigned by whichever package
defines the backend, and reading it can raise outright — `keyring.backends.
Windows.WinVaultKeyring.priority` throws `RuntimeError` on Linux.

`keyring` is imported inside the functions that need it. Measured: importing it
costs about 100 ms, three times what Click costs, and most invocations never
touch a secret. `ai-stp version` should not pay for a store it does not open.
"""

import hmac
import json
from pathlib import Path
from typing import Final, Protocol, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import read_private, secrets_dir, write_private
from ai_stp_contracts.machine_help import CredentialStore

#: Backends actually backed by an operating-system facility. Anything absent —
#: `chainer`, `fail`, `null` and everything in `keyrings.alt` — is treated as
#: **no store**, not as a store. Adding an entry is a security decision.
TRUSTED_BACKENDS: Final[frozenset[str]] = frozenset(
    {
        "keyring.backends.SecretService.Keyring",
        "keyring.backends.libsecret.Keyring",
        "keyring.backends.kwallet.DBusKeyring",
        "keyring.backends.kwallet.DBusKeyringKWallet4",
        "keyring.backends.macOS.Keyring",
        "keyring.backends.Windows.WinVaultKeyring",
    }
)

#: The service name under which entries appear in the OS store.
SERVICE_NAME: Final[str] = "ai-stp"


class SecretStore(Protocol):
    """One place secrets are read from and written to."""

    @property
    def tier(self) -> CredentialStore: ...

    @property
    def detail(self) -> str: ...

    def get(self, name: str) -> str | None: ...

    def put(self, name: str, value: str) -> None: ...

    def drop(self, name: str) -> None: ...


class FileStore:
    """Owner-only files, the tier that works everywhere.

    The same protection an SSH private key gets, which is the level the device
    key needs: it proves which device an event came from, not that the device
    behaved honestly (`ADR-0007`).
    """

    def __init__(self, directory: Path | None = None, detail: str = "") -> None:
        self._directory = directory or secrets_dir()
        self._detail = detail or "owner-only file"

    @property
    def tier(self) -> CredentialStore:
        return "file"

    @property
    def detail(self) -> str:
        return self._detail

    def _path(self, name: str) -> Path:
        return self._directory / f"{name}.secret"

    def get(self, name: str) -> str | None:
        path = self._path(name)
        if not path.exists():
            return None
        return read_private(path)

    def put(self, name: str, value: str) -> None:
        write_private(self._path(name), value)

    def drop(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)


class KeyringStore:
    """The operating system's own credential store."""

    def __init__(self, backend_name: str) -> None:
        self._backend_name = backend_name

    @property
    def tier(self) -> CredentialStore:
        return "os_keyring"

    @property
    def detail(self) -> str:
        return self._backend_name.rpartition(".")[0].removeprefix("keyring.backends.")

    def get(self, name: str) -> str | None:
        import keyring

        try:
            return keyring.get_password(SERVICE_NAME, name)
        except Exception as error:  # pragma: no cover - depends on the OS store
            raise _store_unavailable(error) from error

    def put(self, name: str, value: str) -> None:
        import keyring

        try:
            keyring.set_password(SERVICE_NAME, name, value)
        except Exception as error:  # pragma: no cover - depends on the OS store
            raise _store_unavailable(error) from error

    def drop(self, name: str) -> None:
        import keyring
        import keyring.errors

        try:
            keyring.delete_password(SERVICE_NAME, name)
        except keyring.errors.PasswordDeleteError:
            # Deleting what is not there is the state the caller asked for.
            return
        except Exception as error:  # pragma: no cover - depends on the OS store
            raise _store_unavailable(error) from error


def _store_unavailable(error: BaseException) -> CliFailure:
    """The OS store answered, and the answer was a failure.

    The exception text is not published: `SPEC-011` REQ-1108 keeps environment
    and path material out of output, and a keyring error message routinely
    carries a bus address.
    """
    return CliFailure(
        "AI_STP_DEPENDENCY_UNAVAILABLE",
        "the operating system credential store could not be used",
        retryable=True,
        details={"exception": type(error).__name__},
        next_actions=["doctor --json"],
    )


def selected_backend() -> str | None:
    """The trusted backend this machine offers, or `None` when it offers none.

    Returns the dotted name so the caller can report *which* store it used
    rather than only that there was one.
    """
    try:
        import keyring
    except ImportError:  # pragma: no cover - keyring is a declared dependency
        return None
    try:
        backend = keyring.get_keyring()
    except Exception:  # pragma: no cover - backend discovery is environmental
        return None
    name = f"{type(backend).__module__}.{type(backend).__name__}"
    # An untrusted backend is a refusal, not a missing value: the library found
    # something and this module declines to call it a credential store.
    return name if name in TRUSTED_BACKENDS else None


#: Read once to find out whether the selected backend actually answers. The name
#: is never written; a store that has no such entry returns `None`, which is the
#: successful outcome.
_PROBE_ENTRY: Final[str] = "availability-probe"


def open_store() -> tuple[SecretStore, str | None]:
    """The store to use, and the reason a fallback happened when one did.

    The second element is `None` on the preferred tier and a sentence otherwise.
    It is a warning for the envelope, not a log line: the caller has to be able
    to see that its secret is in a file.

    `AI_STP_FORCE_FILE_CREDENTIAL_STORE=1` pins the file tier even when a trusted
    OS backend exists. Process-level tests and locked-down containers use it so
    secrets stay under the XDG data tree and never open the host locker.

    Selection is not availability. `keyring` picks a backend from what is
    *installed*, and on a headless machine `SecretService` is routinely installed
    with no daemon behind it — an SSH session, a container, a CI runner. Treating
    that as a hard failure made every command refuse on exactly the setup
    `ADR-0058` calls a primary one, so the store is asked one question before it
    is trusted with anything.

    Falling back is not the defect `ADR-0058` guards against; falling back
    *silently* is. This one is named, like the other.
    """
    import os

    if os.environ.get("AI_STP_FORCE_FILE_CREDENTIAL_STORE") == "1":
        return (
            FileStore(detail="owner-only file; forced by AI_STP_FORCE_FILE_CREDENTIAL_STORE"),
            "file credential store forced by AI_STP_FORCE_FILE_CREDENTIAL_STORE",
        )
    backend = selected_backend()
    if backend is not None:
        store = KeyringStore(backend)
        try:
            store.get(_PROBE_ENTRY)
        except CliFailure:
            return (
                FileStore(detail="owner-only file; the credential store did not answer"),
                "the operating system credential store was found but did not answer; "
                "secrets are kept in an owner-only file",
            )
        return store, None
    return (
        FileStore(detail="owner-only file; no operating system credential store is available"),
        "no operating system credential store is available; secrets are kept in an owner-only file",
    )


def promote(store: SecretStore, name: str) -> None:
    """Move a file-tier copy into the OS store, and only then remove it.

    Copy, read back, compare, delete — in that order, and any failure leaves the
    file where it is. The order is the whole point: an earlier version deleted
    the file without ever writing the value, so a machine that gained a
    credential store between two runs lost the secret outright. For the device
    key that meant an identity that could no longer sign and a `device reset` as
    the only way forward — throwing away an identifier the account already
    trusted. `openai/codex#14704` is the same shape from the other side: it
    swallowed the deletion failure and left the secret readable on disk.

    Two values that differ is not a case this can decide. The file might be the
    live one and the store might be stale, or the reverse, and guessing destroys
    a credential either way. Both are kept and the caller is told.
    """
    if store.tier != "os_keyring":
        return
    leftover = FileStore()
    kept = leftover.get(name)
    if kept is None:
        return

    held = store.get(name)
    if held is None:
        store.put(name, kept)
        # Read back rather than trust the write: this is the step that makes the
        # deletion below safe to perform.
        held = store.get(name)
    if held is None or not hmac.compare_digest(held.encode("utf-8"), kept.encode("utf-8")):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "a secret exists in both the credential store and a file, and they do not agree",
            details={"name": name},
            next_actions=["doctor --json"],
        )

    try:
        leftover.drop(name)
    except OSError as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "a secret remains in a file after the credential store took it over",
            details={"exception": type(error).__name__},
            next_actions=["doctor --json"],
        ) from error


def drop_everywhere(store: SecretStore, name: str) -> None:
    """Remove an entry from the current store and from the file tier.

    Dropping only the current tier leaves a copy that `promote` would later find
    disagreeing with a freshly minted value, which fails closed and would strand
    the installation. Anything that retires a secret has to retire both halves.
    """
    store.drop(name)
    if store.tier != "file":
        FileStore().drop(name)


def load_json(store: SecretStore, name: str) -> dict[str, str] | None:
    """Read a stored JSON document, refusing anything that is not one."""
    raw = store.get(name)
    if raw is None:
        return None
    try:
        parsed: object = json.loads(raw)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "stored credential material is not valid JSON",
            details={"name": name},
            next_actions=["device reset --confirm --json"],
        ) from error
    if not isinstance(parsed, dict):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "stored credential material is not an object",
            details={"name": name},
            next_actions=["device reset --confirm --json"],
        )
    document = cast(dict[object, object], parsed)
    return {str(key): str(value) for key, value in document.items()}


def store_json(store: SecretStore, name: str, document: dict[str, str]) -> None:
    """Write a JSON document, sorted so a rewrite of equal content is equal."""
    store.put(name, json.dumps(document, sort_keys=True, ensure_ascii=False))
