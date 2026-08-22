"""Publish one setup and the components it pins, as a single decision.

A setup cannot become public before its exact pins are: the platform's own pin
aggregate refuses a setup whose components have no passing scan. Publication
offered one plan per object, so a person with a setup of twenty-nine components
faced thirty plans and thirty confirmations — and no way to publish the setup at
all, because `publication plan` only ever spoke about components.

Locally the two are already one act. `setup import register` commits the
component artifacts, the component passports and the setup graph together or not
at all. This carries that rule across the publication boundary (`ADR-0114`,
`SPEC-038` `REQ-3810`-`REQ-3812`).

What does not change is the guarantee. Publication still takes an explicit
confirmation of an exact hash; the hash now covers the whole graph, in the order
it will be confirmed, so confirming it is confirming all of it and nothing else.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from typing import Final, Literal, cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import login, publication, session
from ai_stp_cli.cloud import owner as owner_reads
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, publication_sets, revisions, versions
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_cli.local.passports import moment
from ai_stp_contracts.machine_help import PublicationSetMemberView, PublicationSetView
from ai_stp_contracts.publication import ObjectKind as PublicationObjectKind
from ai_stp_contracts.publication import (
    PublicationConfirmRequest,
    PublicationPlanCreateRequest,
    PublicationPlanResponse,
)
from ai_stp_passports import SetupVersionPassport

#: Terminal, and not published. Confirming further members after one of these
#: would publish a graph the refused member is part of.
_TERMINAL_FAILURES: Final[frozenset[str]] = frozenset({"failed", "rejected", "expired"})
_PUBLISHED: Final[str] = "published"

#: How many times a member's state is re-read before the set is reported as
#: `partial`. Validation is asynchronous, and a set that gave up after one look
#: would call every slow scan a failure.
_MAX_POLLS: Final[int] = 60
_POLL_SECONDS: Final[float] = 2.0

#: What a member is in the set. Stated rather than derived from `object_kind`:
#: a set holds exactly one setup, and a reader should not have to count.
type MemberRole = Literal["setup", "pinned_component"]

#: The store keeps its states as text; the view's vocabulary is closed. One
#: mapping so the two cannot drift into disagreeing about the same word.
_SET_STATES: Final[dict[str, Literal["planned", "published", "partial"]]] = {
    publication_sets.STATE_PLANNED: "planned",
    publication_sets.STATE_PARTIAL: "partial",
    publication_sets.STATE_PUBLISHED: "published",
}


def plan(parameters: Mapping[str, object]) -> Answer[PublicationSetView]:
    """Create every plan this setup's publication needs, and nothing else.

    A member that is already public is listed and not replanned. Leaving it out
    would make the set describe less than the graph it publishes; replanning it
    would ask the platform to publish something that is already published.
    """
    stable_id = _required(parameters, "id")
    version = _required(parameters, "version")
    held = _session()
    where = endpoint()

    with closing(open_readonly(configured_path())) as connection:
        setup = _setup_passport(connection, stable_id, version)
        pins = _pins(setup)
        artifacts = {
            item[0]: _artifact(connection, item[1]) for item in _digests(connection, setup, pins)
        }

    members: list[PublicationSetMemberView] = []
    for pin_id, pin_version in pins:
        members.append(
            _member(
                where,
                held,
                role="pinned_component",
                object_kind="component",
                stable_id=pin_id,
                version=pin_version,
                passport=_passport_document(pin_id, pin_version),
                artifact_digest=artifacts[pin_id][0],
            )
        )
    members.append(
        _member(
            where,
            held,
            role="setup",
            object_kind="setup",
            stable_id=stable_id,
            version=version,
            passport=cast(dict[str, object], setup.model_dump(mode="json")),
            artifact_digest=setup.artifact.digest,
        )
    )

    with closing(open_registry(configured_path(), create=True)) as connection:
        stored = publication_sets.record(
            connection,
            setup_stable_id=stable_id,
            setup_version=version,
            account_id=held.account_id,
            device_id=held.device_id,
            members=members,
            at=moment(),
        )
    return Answer(_view(stored))


def confirm(parameters: Mapping[str, object]) -> Answer[PublicationSetView]:
    """Confirm one exact reviewed set, components before the setup.

    Order is not a convenience. A setup confirmed before its pins is refused by
    the platform for a reason that reads like a defect in the setup, so the
    ordering is the client's job and it is the reason the set exists.
    """
    digest = _required(parameters, "set-digest")
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "publishing a setup and its components requires confirming the exact set digest",
            details={"set_digest": digest},
            next_actions=[f"setup publish confirm --set-digest {digest} --confirm --json"],
        )
    held = _session()
    where = endpoint()

    with closing(open_registry(configured_path(), create=True)) as connection:
        stored = publication_sets.get(connection, digest)
        if stored is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no reviewed publication set with that digest is held on this machine",
                next_actions=["setup publish plan --id <setup> --version <X.Y> --json"],
            )
        if stored.account_id != held.account_id or stored.device_id != held.device_id:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the reviewed set belongs to another account or device",
            )
        artifacts = _stored_artifacts(connection, stored.members)

    settled = _confirm_members(where, held, stored.members, artifacts)
    state = _set_state(settled)
    with closing(open_registry(configured_path(), create=True)) as connection:
        stored = publication_sets.settle(connection, digest, members=settled, state=state)
    return Answer(_view(stored))


def _confirm_members(
    where: Endpoint,
    held: session.Session,
    members: Sequence[PublicationSetMemberView],
    artifacts: Mapping[str, bytes],
    *,
    pause: Callable[[float], None] = time.sleep,
) -> tuple[PublicationSetMemberView, ...]:
    """Bind and confirm each member in order, stopping at the first refusal.

    Stopping is deliberate. The members already published stay published — that
    is what makes the set resumable — but continuing past a refused component
    would publish a setup pinning something the platform declined.
    """
    settled: list[PublicationSetMemberView] = []
    stop = False
    for member in members:
        if stop or member.already_published or not member.plan_id:
            settled.append(member)
            continue
        try:
            final = _confirm_one(where, held, member, artifacts.get(member.stable_id, b""), pause)
        except CliFailure:
            settled.append(member.model_copy(update={"state": "blocked"}))
            stop = True
            continue
        settled.append(member.model_copy(update={"state": final.state}))
        if final.state != _PUBLISHED:
            stop = True
    return tuple(settled)


def _confirm_one(
    where: Endpoint,
    held: session.Session,
    member: PublicationSetMemberView,
    artifact: bytes,
    pause: Callable[[float], None],
) -> PublicationPlanResponse:
    current = publication.status(where, held.access_token, member.plan_id)
    if current.state == _PUBLISHED or current.state in _TERMINAL_FAILURES:
        return current
    if current.state in {"ready", "draft"}:
        publication.bind(where, held.access_token, member.plan_id, artifact, pause=pause)
        current = publication.confirm(
            where,
            held.access_token,
            member.plan_id,
            PublicationConfirmRequest(
                plan_hash=member.plan_hash,
                confirmed=True,
                idempotency_key=login.new_idempotency_key(),
            ),
        )
    return _wait_terminal(where, held, current, pause)


def _wait_terminal(
    where: Endpoint,
    held: session.Session,
    current: PublicationPlanResponse,
    pause: Callable[[float], None],
) -> PublicationPlanResponse:
    """Read until the platform has decided, or until waiting stops being useful."""
    for _ in range(_MAX_POLLS):
        if current.state == _PUBLISHED or current.state in _TERMINAL_FAILURES:
            return current
        pause(_POLL_SECONDS)
        current = publication.status(where, held.access_token, current.plan_id)
    return current


def _member(
    where: Endpoint,
    held: session.Session,
    *,
    role: MemberRole,
    object_kind: PublicationObjectKind,
    stable_id: str,
    version: str,
    passport: Mapping[str, object],
    artifact_digest: str,
) -> PublicationSetMemberView:
    """One member: already public, or a fresh plan for making it public."""
    if _already_public(where, held, object_kind, stable_id, version):
        return PublicationSetMemberView(
            role=role,
            object_kind=object_kind,
            stable_id=stable_id,
            version=version,
            already_published=True,
            state=_PUBLISHED,
        )
    created = publication.create(
        where,
        held.access_token,
        PublicationPlanCreateRequest(
            object_kind=object_kind,
            stable_id=stable_id,
            version=version,
            content_digest=artifact_digest,
            passport=dict(passport),
            attestations=[],
            idempotency_key=login.new_idempotency_key(),
            device_id=held.device_id,
        ),
    )
    return PublicationSetMemberView(
        role=role,
        object_kind=object_kind,
        stable_id=stable_id,
        version=version,
        plan_id=created.plan_id,
        plan_hash=created.plan_hash,
        state=created.state,
    )


def _already_public(
    where: Endpoint,
    held: session.Session,
    object_kind: PublicationObjectKind,
    stable_id: str,
    version: str,
) -> bool:
    """Whether this exact version is public already, asked of the platform.

    Local visibility cannot answer it: a passport says what this machine
    believes, and what is public is a fact about the platform. Absent is not
    public — an object this account has never pushed reads as a 404, which is
    exactly the case a plan exists for.
    """
    try:
        detail = owner_reads.version_detail(
            where, held.access_token, object_kind, stable_id, version
        )
    except CliFailure as failure:
        if failure.code == "AI_STP_NOT_FOUND":
            return False
        raise
    return detail.visibility == "public"


def _view(stored: publication_sets.StoredSet) -> PublicationSetView:
    return PublicationSetView(
        set_digest=stored.set_digest,
        setup_stable_id=stored.setup_stable_id,
        setup_version=stored.setup_version,
        members=list(stored.members),
        state=_SET_STATES[stored.state],
    )


def _set_state(members: Sequence[PublicationSetMemberView]) -> str:
    if all(member.already_published or member.state == _PUBLISHED for member in members):
        return publication_sets.STATE_PUBLISHED
    if any(member.state == _PUBLISHED or member.already_published for member in members):
        return publication_sets.STATE_PARTIAL
    return publication_sets.STATE_PLANNED


def _setup_passport(
    connection: sqlite3.Connection, stable_id: str, version: str
) -> SetupVersionPassport:
    recorded = versions.held(connection, stable_id, version)
    if recorded is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that setup has no such released local version",
            details={"id": stable_id, "version": version},
        )
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None or stored.envelope.kind != "setup":
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the released revision at that version is not a setup",
            details={"id": stable_id, "version": version},
            next_actions=[f"publication plan --id {stable_id} --version {version} --json"],
        )
    return SetupVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))


def _pins(setup: SetupVersionPassport) -> tuple[tuple[str, str], ...]:
    """The exact component versions this setup pins, in passport order."""
    return tuple((ref.stable_id, ref.version) for ref in setup.components)


def _digests(
    connection: sqlite3.Connection,
    setup: SetupVersionPassport,
    pins: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    found: list[tuple[str, str]] = [(setup.stable_id, setup.artifact.digest)]
    for stable_id, version in pins:
        found.append((stable_id, _component_digest(connection, stable_id, version)))
    return tuple(found)


def _component_digest(connection: sqlite3.Connection, stable_id: str, version: str) -> str:
    from ai_stp_cli.local import component_passports

    return component_passports.version_passport(connection, stable_id, version).artifact.digest


def _passport_document(stable_id: str, version: str) -> dict[str, object]:
    from ai_stp_cli.local import component_passports

    with closing(open_readonly(configured_path())) as connection:
        passport = component_passports.version_passport(connection, stable_id, version)
    return cast(dict[str, object], passport.model_dump(mode="json"))


def _artifact(connection: sqlite3.Connection, digest: str) -> tuple[str, bytes]:
    return digest, content.get(connection, digest)


def _stored_artifacts(
    connection: sqlite3.Connection, members: Sequence[PublicationSetMemberView]
) -> dict[str, bytes]:
    """The exact bytes each member will bind, read once under one open registry."""
    found: dict[str, bytes] = {}
    for member in members:
        if member.already_published or not member.plan_id:
            continue
        if member.object_kind == "setup":
            setup = _setup_passport(connection, member.stable_id, member.version)
            found[member.stable_id] = content.get(connection, setup.artifact.digest)
        else:
            found[member.stable_id] = content.get(
                connection, _component_digest(connection, member.stable_id, member.version)
            )
    return found


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = parameters.get(name)
    if value is None or not str(value):
        raise CliFailure("AI_STP_VALIDATION_ERROR", f"--{name} is required")
    return str(value)


def _session() -> session.Session:
    return cloud_auth.required("publication")
