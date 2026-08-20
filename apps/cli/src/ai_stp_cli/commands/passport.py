"""`ai-stp passport` — the local developer and device passports (issue #74).

Everything here works without an account and without a network
(`offline-capability.md`). Ownership before sign-in is a locally minted
identifier by `ADR-0060`; `#75` transfers it to the account the server issues,
as a revision rather than an edit in place.
"""

import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from typing import cast

from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports, revisions
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_contracts.machine_help import PassportView
from ai_stp_foundation.canonical import JsonValue


def _view(stored: revisions.StoredRevision) -> PassportView:
    document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
    return PassportView(
        kind=stored.envelope.kind,  # pyright: ignore[reportArgumentType]
        stable_id=stored.stable_id,
        revision_id=stored.revision_id,
        parent_revision_ids=list(stored.parents),
        created_at=stored.envelope.created_at,
        owner_id=stored.envelope.owner_id,
        facts=cast(dict[str, JsonValue], document["facts"]),
    )


def _with_registry[T](work: Callable[[sqlite3.Connection], T], *, create: bool) -> T:
    with closing(open_registry(configured_path(), create=create)) as connection:
        return work(connection)


def _with_readonly_registry[T](work: Callable[[sqlite3.Connection], T]) -> T:
    with closing(open_readonly(configured_path())) as connection:
        return work(connection)


def developer_init(_parameters: Mapping[str, object]) -> Answer[PassportView]:
    """Create the developer passport, or return the one already there."""
    current, _warning = identity.load_or_create()

    def work(connection: sqlite3.Connection) -> PassportView:
        return _view(passports.init_developer(connection, device_id=current.device_id))

    return Answer(_with_registry(work, create=True))


def developer_show(_parameters: Mapping[str, object]) -> Answer[PassportView]:
    """Show the developer passport at its current head, creating nothing.

    `SPEC-009` REQ-902: reading does not bring state into existence, so a
    missing registry or a missing passport is a typed answer rather than an
    initialisation.
    """

    def work(connection: sqlite3.Connection) -> PassportView:
        stable_id = passports.developer_stable_id(connection)
        if stable_id is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "there is no developer passport yet",
                next_actions=["passport developer init --json"],
            )
        head = revisions.head(connection, stable_id)
        if head is None:  # pragma: no cover - an entity always has a head here
            raise CliFailure("AI_STP_INTERNAL", "the developer passport has no head")
        return _view(head)

    return Answer(_with_readonly_registry(work))


def developer_update(parameters: Mapping[str, object]) -> Answer[PassportView]:
    """Declare developer facts, producing one revision on the current head."""
    current, _warning = identity.load_or_create()
    values = _declarations(parameters.get("set"))
    if not values:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "nothing was declared",
            next_actions=["passport developer show --json"],
        )

    def work(connection: sqlite3.Connection) -> PassportView:
        return _view(passports.update_developer(connection, values, device_id=current.device_id))

    return Answer(_with_registry(work, create=False))


def device_refresh(_parameters: Mapping[str, object]) -> Answer[PassportView]:
    """Create the device passport, or bring it up to what is observable now.

    One command rather than an `init` and an `update` pair, because the device
    passport declares nothing: every fact in it is observed, so creating it and
    refreshing it are the same act. `passport developer` has both because its
    facts are declared by a person.

    Content-addressed and carrying unchanged observations forward, so a run that
    finds nothing new writes nothing at all.
    """
    current, _warning = identity.load_or_create()

    def work(connection: sqlite3.Connection) -> PassportView:
        return _view(passports.ensure_device(connection, device_id=current.device_id))

    return Answer(_with_registry(work, create=True))


def device_show(_parameters: Mapping[str, object]) -> Answer[PassportView]:
    """Show the device passport at its current head, creating nothing.

    This used to observe the environment and write a revision, under a name that
    says the opposite. It was at least declared `apply`, so the machine contract
    was not lying — but `show` is what an agent reads, and a command that writes
    history has no business being called one.
    """

    def work(connection: sqlite3.Connection) -> PassportView:
        stable_id = passports.device_stable_id(connection)
        if stable_id is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "there is no device passport yet",
                next_actions=["passport device refresh --json"],
            )
        head = revisions.head(connection, stable_id)
        if head is None:  # pragma: no cover - an entity always has a head here
            raise CliFailure("AI_STP_INTERNAL", "the device passport has no head")
        return _view(head)

    return Answer(_with_readonly_registry(work))


def _declarations(raw: object) -> dict[str, JsonValue]:
    """Parse repeated `field=value` arguments into declared facts."""
    if raw is None:
        return {}
    supplied: tuple[object, ...] = (
        tuple(cast(tuple[object, ...], raw)) if isinstance(raw, tuple | list) else (raw,)
    )
    values: dict[str, JsonValue] = {}
    for item in supplied:
        text = str(item)
        name, separator, value = text.partition("=")
        if not separator or not name.strip():
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a declaration must be written as field=value",
                details={"given": text},
                next_actions=["passport developer show --json"],
            )
        # A comma-separated value becomes a list: several passport fields are
        # naturally plural, and quoting a JSON array on a command line is worse
        # for both a human and an agent.
        parts: list[JsonValue] = [part.strip() for part in value.split(",") if part.strip()]
        values[name.strip()] = parts if len(parts) > 1 else value
    return values
