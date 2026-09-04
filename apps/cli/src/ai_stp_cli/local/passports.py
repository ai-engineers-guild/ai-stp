"""Developer and device passports in the local registry.

`ADR-0025` splits context into three owners, and the split is enforced here
rather than trusted: `SPEC-003` REQ-304 says the developer passport must not
carry observed operating system, architecture or installed harness versions, and
`SPEC-002` REQ-213 says those belong to the device. A field matching both would
be a modelling error, so writing one is refused.

Ownership before sign-in follows `ADR-0060`: a local `account_…` is minted on
first use and `#75` transfers ownership to the server's account as an ordinary
revision.
"""

import json
import platform
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import harnesses, journal, revisions
from ai_stp_cli.paths import (
    bootstrap_lock,
    data_dir,
    read_private,
    redact_any_home,
    write_private,
)
from ai_stp_cli.runtime import cli_version
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import is_valid_id, new_id
from ai_stp_foundation.timestamps import format_timestamp

#: Facts the developer passport declares. Closed on purpose: `SPEC-003` REQ-304
#: lists what it holds, and "arbitrary metadata" is what REQ-310 forbids for the
#: neighbouring object for the same reason.
DEVELOPER_FIELDS: Final[tuple[str, ...]] = (
    "role",
    "typical_tasks",
    "priorities",
    "preferred_languages",
    "preferred_harnesses",
    "autonomy",
)

#: Never in the developer passport. These are environment observations and they
#: belong to the device (`ADR-0025`); accepting one here would create a second
#: owner for the same fact and make a re-scan on another machine look like a
#: change of preference.
ENVIRONMENT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "operating_system",
        "architecture",
        "installed_harnesses",
        "harness_versions",
        "tool_versions",
    }
)


def moment() -> str:
    return format_timestamp(datetime.now(UTC))


@dataclass(frozen=True)
class LocalOwner:
    """Who owns the passports on this installation."""

    account_id: str


def owner() -> LocalOwner:
    """The local owner identity, minted on first use (`ADR-0060`).

    Not sent anywhere: it is not an account, and presenting it as one to a
    server would be a lie. `#75` replaces it with the account the server issues,
    as a revision rather than an edit in place.
    """
    path = data_dir() / "owner.json"
    current = known_owner()
    if current is not None:
        return current

    # Two first runs must not mint two owners: every passport carries the
    # owner in its content, so a split here splits the whole local history.
    with bootstrap_lock():
        current = known_owner()
        if current is not None:
            return current
        minted = new_id("account")
        write_private(path, json.dumps({"account_id": minted}, sort_keys=True) + "\n")
    return LocalOwner(minted)


def known_owner() -> LocalOwner | None:
    """Return the local owner if one was already established, writing nothing."""
    path = data_dir() / "owner.json"
    if not path.exists():
        return None
    try:
        parsed: object = json.loads(read_private(path))
    except ValueError as error:
        raise _unreadable_owner(error) from error
    if not isinstance(parsed, dict):
        raise _unreadable_owner(TypeError("owner record is not an object"))
    account_id = str(cast(dict[str, object], parsed).get("account_id", ""))
    if not is_valid_id(account_id, "account"):
        raise _unreadable_owner(ValueError("owner record carries no valid account id"))
    return LocalOwner(account_id)


def adopt(account_id: str) -> None:
    """Make the account the server issued the canonical owner (`ADR-0060`).

    Written before any passport is moved, and that order is the whole design.
    The owner record is what every later revision reads its `owner_id` from, so
    while it still named the local identity the handover undid itself: the first
    environment change refreshed the device passport, took the local owner from
    here, and committed a revision that owned the object back again.

    Recording the owner first cannot leave that state. A failure between this and
    the passport revisions leaves objects owned by the previous identity, which
    `reconcile_owner` finishes on the next passport operation — it compares each
    head against this record, so it is idempotent and needs no marker of its own.
    """
    write_private(
        data_dir() / "owner.json",
        json.dumps({"account_id": account_id}, sort_keys=True) + "\n",
    )


def reconcile_owner(connection: sqlite3.Connection, *, device_id: str) -> tuple[str, ...]:
    """Bring every passport onto the canonical owner, and say which moved.

    A revision, not an edit: `owner_id` is content, so changing it produces a new
    revision with the previous one as its parent, and the handover is visible in
    the graph rather than a value that quietly changed.

    Idempotent, and that is what makes it a resumption point rather than a step:
    a passport already owned by this account produces nothing, because the
    content would be identical and content addressing refuses to store it twice.
    """
    account_id = owner().account_id
    moved: list[str] = []
    for stable_id in (developer_stable_id(connection), device_stable_id(connection)):
        if stable_id is None:
            continue
        current = revisions.head(connection, stable_id)
        if current is None or current.envelope.owner_id == account_id:
            continue
        content = cast(dict[str, JsonValue], current.envelope.model_dump(mode="json"))
        content["owner_id"] = account_id
        content["parent_revision_ids"] = [current.revision_id]
        content.pop("revision_id", None)
        revisions.commit(connection, content, device_id=device_id)
        moved.append(stable_id)
    return tuple(moved)


def _unreadable_owner(error: BaseException) -> CliFailure:
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "the local owner record cannot be read",
        details={"exception": type(error).__name__},
    )


def _fact(value: JsonValue, origin: str, at: str) -> dict[str, JsonValue]:
    return {"value": value, "origin": origin, "confirmation": "none", "observed_at": at}


#: What creates each passport, by kind. One owner because two callers need it
#: and they must never name different commands for the same missing thing:
#: `select propose` refuses without one and says how to get it, and `doctor`
#: reports the same requirement before anybody hits the refusal.
CREATES_PASSPORT: Final[dict[str, str]] = {
    "developer": "passport developer init --json",
    "device": "passport device refresh --json",
    "project": "project passport --root <directory> --json",
}

#: The two a composition anchors to that belong to the installation rather than
#: to one project. `project` is per-project and cannot be answered installation-wide.
COMPOSITION_PASSPORT_KINDS: Final[tuple[str, ...]] = ("developer", "device")


def developer_stable_id(connection: sqlite3.Connection) -> str | None:
    """The developer passport of this installation, if one exists."""
    row = connection.execute(
        "SELECT stable_id FROM entity WHERE kind = 'developer' ORDER BY created_at LIMIT 1"
    ).fetchone()
    return None if row is None else str(row["stable_id"])


def device_stable_id(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        "SELECT stable_id FROM entity WHERE kind = 'device' ORDER BY created_at LIMIT 1"
    ).fetchone()
    return None if row is None else str(row["stable_id"])


def _content(kind: str, stable_id: str, owner_id: str, at: str) -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "kind": kind,
        "stable_id": stable_id,
        "owner_id": owner_id,
        "created_at": at,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {},
    }


def init_developer(connection: sqlite3.Connection, *, device_id: str) -> revisions.StoredRevision:
    """Create the developer passport, or return the one already there.

    Idempotent: running it twice does not create a second passport and does not
    add a revision, because the content is unchanged and content addressing
    refuses to duplicate it.
    """
    existing = developer_stable_id(connection)
    if existing is not None:
        current = revisions.head(connection, existing)
        if current is not None:
            return current

    at = moment()
    operation_id = journal.begin(connection, "passport.developer.init", at)
    try:
        stored = revisions.commit(
            connection,
            _content("developer", new_id("developer"), owner().account_id, at),
            device_id=device_id,
            operation_id=operation_id,
        )
    except BaseException as error:
        journal.settle(connection, operation_id, "failed", moment(), type(error).__name__)
        raise
    journal.settle(connection, operation_id, "verified", moment())
    return stored


def update_developer(
    connection: sqlite3.Connection,
    values: dict[str, JsonValue],
    *,
    device_id: str,
) -> revisions.StoredRevision:
    """Declare developer facts, producing one revision on top of the current head."""
    unknown = sorted(set(values) - set(DEVELOPER_FIELDS))
    if unknown:
        forbidden = sorted(set(values) & ENVIRONMENT_FIELDS)
        if forbidden:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "an environment observation belongs to the device passport, not the developer",
                details={"field": forbidden[0], "owner": "device"},
                next_actions=["passport device show --json"],
            )
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "unknown developer passport field",
            details={"field": unknown[0], "allowed": ", ".join(DEVELOPER_FIELDS)},
        )

    stable_id = developer_stable_id(connection)
    if stable_id is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "there is no developer passport yet",
            next_actions=["passport developer init --json"],
        )
    current = revisions.head(connection, stable_id)
    if current is None:  # pragma: no cover - an entity always has a head here
        raise CliFailure("AI_STP_INTERNAL", "the developer passport has no head")

    at = moment()
    content = cast(dict[str, JsonValue], current.envelope.model_dump(mode="json"))
    facts = dict(cast(dict[str, JsonValue], content["facts"]))
    # Declared, not observed: these are the user's own statements about
    # themselves (`SPEC-003` REQ-304).
    facts.update({name: _fact(value, "declared", at) for name, value in values.items()})
    content["facts"] = facts
    content["parent_revision_ids"] = [current.revision_id]
    content.pop("revision_id", None)

    operation_id = journal.begin(connection, "passport.developer.update", at)
    try:
        stored = revisions.commit(
            connection, content, device_id=device_id, operation_id=operation_id
        )
    except BaseException as error:
        journal.settle(connection, operation_id, "failed", moment(), type(error).__name__)
        raise
    journal.settle(connection, operation_id, "verified", moment())
    return stored


def observed_environment(at: str) -> dict[str, JsonValue]:
    """The environment facts this build can observe safely.

    `SPEC-014` REQ-1418 puts the harness survey here and nowhere else: this is
    the *device* passport, and `ADR-0025` keeps installed harnesses and their
    versions out of the developer passport, which describes a person rather than
    a machine. `DEVELOPER_FIELDS` and `ENVIRONMENT_FIELDS` enforce that split
    above, so writing one of these into a developer passport is refused rather
    than merely discouraged.

    Detection runs subprocesses, which is why it belongs to a refresh a caller
    asked for and not to a read. A harness that will not answer contributes
    `unknown` — never a guessed version, because a passport is what later
    decisions are made from.
    """
    system = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}.get(
        platform.system(), "unknown"
    )
    machine = {"x86_64": "x86_64", "AMD64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine(), "unknown"
    )
    found = harnesses.detect_all()
    # The survey command and this refresh share `detect_all`. Installed vs
    # merely supported is the same cut: `available` stays out of the passport.
    present_found = harnesses.present_installations(found)
    # Built as list comprehensions with the element type declared: `sorted`
    # answers `list[str]`, and a list is invariant, so the narrower list is not
    # a value of the wider one however obviously its elements fit.
    present: list[JsonValue] = [item.harness_id for item in present_found]
    versions: list[JsonValue] = [
        f"{item.harness_id}={item.installations[0].version}"
        for item in present_found
        if item.installations
    ]
    # Every installation, structurally, because the flat line above keeps only
    # the first: a machine with two codex installs answered which version it
    # had by hiding one of them. Paths travel `~`-relative — a device passport
    # syncs, and an absolute path is this machine's identity.
    installations: list[JsonValue] = [
        {
            "harness_id": item.harness_id,
            "installations": [
                {
                    # `redact_any_home`, not `redact_home`: under a synthetic HOME the
                    # binary is discovered in the real account's home, and the
                    # precise fold would keep the account name (measured live).
                    "path": redact_any_home(Path(held.path)),
                    "version": held.version,
                    "normalized_version": held.normalized_version,
                    "version_source": held.version_source,
                    "surface": held.surface,
                    "selected": index == 0,
                }
                for index, held in enumerate(item.installations)
            ],
        }
        for item in present_found
        if item.installations
    ]
    return {
        "operating_system": _fact(system, "observed", at),
        "architecture": _fact(machine, "observed", at),
        "installed_harnesses": _fact(present, "observed", at),
        "harness_versions": _fact(versions, "observed", at),
        "harness_installations": _fact(installations, "observed", at),
        "tool_versions": _fact([f"ai-stp-cli={cli_version()}"], "observed", at),
    }


def carry_unchanged(
    fresh: dict[str, JsonValue], previous: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    """Keep the earlier observation when the value did not change.

    Without this, `observed_at` alone would differ on every run, the content
    would differ, and a re-scan that found nothing new would produce a revision
    saying something changed. `SPEC-003` REQ-312 is explicit that re-scanning
    must not manufacture history, and `SPEC-009` REQ-902 that a read changes
    nothing.
    """
    carried: dict[str, JsonValue] = {}
    for name, observation in fresh.items():
        earlier = previous.get(name)
        unchanged = (
            isinstance(earlier, dict)
            and isinstance(observation, dict)
            and earlier.get("value") == observation.get("value")
        )
        carried[name] = earlier if unchanged else observation  # pyright: ignore[reportArgumentType]
    return carried


def ensure_device(connection: sqlite3.Connection, *, device_id: str) -> revisions.StoredRevision:
    """Create or refresh the device passport for this installation.

    Refreshing is content-addressed, so an unchanged environment produces no new
    revision — a re-scan that changed nothing must not look like a change.

    Creation is serialised across processes; refreshing is not. Only the first
    one races, and holding a lock on every `passport device show` would make
    concurrent agent calls queue behind each other for nothing.
    """
    if device_stable_id(connection) is None:
        with bootstrap_lock():
            if device_stable_id(connection) is None:
                return _create_device(connection, device_id=device_id)
    return _create_device(connection, device_id=device_id)


def _create_device(connection: sqlite3.Connection, *, device_id: str) -> revisions.StoredRevision:
    # Finish any handover that was interrupted before writing anything new,
    # otherwise this refresh is exactly what used to revert it.
    reconcile_owner(connection, device_id=device_id)
    at = moment()
    stable_id = device_stable_id(connection)
    parents: list[JsonValue] = []
    previous_facts: dict[str, JsonValue] = {}
    created_at = at
    current: revisions.StoredRevision | None = None
    if stable_id is not None:
        current = revisions.head(connection, stable_id)
        if current is not None:
            parents = [current.revision_id]
            created_at = current.envelope.created_at
            previous_facts = cast(
                dict[str, JsonValue],
                cast(dict[str, JsonValue], current.envelope.model_dump(mode="json"))["facts"],
            )
    else:
        stable_id = new_id("device")

    facts = carry_unchanged(observed_environment(at), previous_facts)
    if current is not None and facts == previous_facts:
        # Nothing was observed that the passport does not already say. Carrying
        # the facts forward is not enough on its own: the parent list differs
        # between a first revision and a second, so committing anyway would
        # still write history for a rescan that found nothing.
        return current

    content = _content("device", stable_id, owner().account_id, created_at)
    content["facts"] = facts
    content["parent_revision_ids"] = parents

    operation_id = journal.begin(connection, "passport.device.refresh", at)
    try:
        stored = revisions.commit(
            connection, content, device_id=device_id, operation_id=operation_id
        )
    except BaseException as error:
        journal.settle(connection, operation_id, "failed", moment(), type(error).__name__)
        raise
    journal.settle(connection, operation_id, "verified", moment())
    return stored
