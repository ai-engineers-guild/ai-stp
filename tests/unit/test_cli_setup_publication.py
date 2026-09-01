# pyright: reportPrivateUsage=false, reportPrivateImportUsage=false
"""Publishing a setup together with the components it pins (`SPEC-038`).

`REQ-3810`-`REQ-3812` and `ADR-0114` own the behaviour. What is observed here is
the whole of what makes it one decision rather than thirty: which members get a
plan, what the digest covers, and what a refusal part-way through leaves behind.

Nothing here reaches a network. The platform is replaced at the two functions
the command calls, which is also where the interesting cases live — a component
that is public already, and one the platform refuses.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Collection, Iterator
from contextlib import closing
from typing import Any

import pytest

from ai_stp_cli.commands import setup_publication
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, publication_sets, revisions, setup_versions, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import PublicationSetMemberView
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.ids import new_id

pytestmark = pytest.mark.cli

AT = "2026-01-01T00:00:00.000Z"

#: One released setup, built locally by the fixture below.
SETUP = "setup_01KZWSHE3VWEF0NT2XVRH45AJ9"
SETUP_VERSION = "1.0"

#: Three pinned components: small enough to state the whole expected set in a
#: test, large enough for the order to be observable and for a refusal to have
#: something before it and something after it.
PIN_COUNT = 3


class _Platform:
    """A stand-in for the platform that records what it was asked to do."""

    def __init__(self, *, public: Collection[str] = (), refuse: str = "") -> None:
        self.public = set(public)
        self.refuse = refuse
        self.created: list[tuple[str, str, str]] = []
        self.confirmed: list[str] = []
        self.bound: list[str] = []

    def version_detail(self, _where: object, _kind: str, stable_id: str, version: str) -> Any:
        del version
        if stable_id not in self.public:
            raise CliFailure("AI_STP_NOT_FOUND", "version not found")
        return _Detail("public")

    def status(self, _where: object, _token: str, plan_id: str) -> Any:
        return _Plan(plan_id, "published" if plan_id in self.confirmed else "ready")

    def create(self, _where: object, _token: str, request: Any) -> Any:
        self.created.append((request.object_kind, request.stable_id, request.version))
        return _Plan(f"plan_{request.stable_id}", "draft")

    def bind(self, _where: object, _token: str, plan_id: str, _payload: bytes, **_k: object) -> Any:
        self.bound.append(plan_id)
        return _Plan(plan_id, "ready")

    def confirm(self, _where: object, _token: str, plan_id: str, _request: Any) -> Any:
        if self.refuse and plan_id == f"plan_{self.refuse}":
            return _Plan(plan_id, "failed")
        self.confirmed.append(plan_id)
        return _Plan(plan_id, "published")


class _Detail:
    def __init__(self, visibility: str) -> None:
        self.visibility = visibility


class _Plan:
    def __init__(self, plan_id: str, state: str) -> None:
        self.plan_id = plan_id
        self.plan_hash = f"hash_{plan_id}"
        self.state = state


class _Session:
    # Real identifier shapes: the request models validate them, and a stand-in
    # that could not be sent would test the model rather than the command.
    account_id = "account_01KZET6ZKJN7S72T5H4WDV62T0"
    device_id = "device_01M0K11E2MHAAJ0X8W7NB7QKW1"
    access_token = "token"


def _install(monkeypatch: pytest.MonkeyPatch, fake: _Platform) -> None:
    monkeypatch.setattr(setup_publication, "_session", _Session)
    monkeypatch.setattr(setup_publication, "endpoint", object)
    monkeypatch.setattr(setup_publication.catalog, "version", fake.version_detail)
    monkeypatch.setattr(setup_publication.publication, "create", fake.create)
    monkeypatch.setattr(setup_publication.publication, "status", fake.status)
    monkeypatch.setattr(setup_publication.publication, "bind", fake.bind)
    monkeypatch.setattr(setup_publication.publication, "confirm", fake.confirm)
    monkeypatch.setattr(setup_publication, "_POLL_SECONDS", 0.0)


@pytest.fixture
def platform(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Platform]:
    fake = _Platform()
    _install(monkeypatch, fake)
    yield fake


def _fact(value: JsonValue) -> JsonValue:
    return {"value": value, "origin": "observed", "confirmation": "none", "observed_at": AT}


def _release_component(connection: sqlite3.Connection, index: int, owner: str) -> str:
    """One released component version, in the shape publication reads.

    Built through the local path rather than lifted from the first-party corpus:
    `version_passport` rebuilds a public passport from the released draft's
    facts, so a fixture holding a finished passport would exercise a shape the
    command never sees.
    """
    payload = f"# component {index}\n".encode()
    content.put(connection, payload, at=AT)
    stable_id = new_id("component")
    facts: dict[str, JsonValue] = {
        "component_type": _fact("skill"),
        "harness_id": _fact("codex"),
        "scope": _fact("project"),
        "name": _fact(f"skill-{index}"),
        "description": _fact("A skill that does one thing."),
        "license": _fact({"spdx_id": "MIT", "redistribution_allowed": True}),
        "projection_kind": _fact("native_files"),
        "tags": _fact(["security"]),
        "source_path": _fact(f"skills/component-{index}"),
        "source_repository": _fact("https://github.com/org/repo"),
        "source_revision": _fact("a" * 40),
        "source_subpath": _fact(f"skills/component-{index}"),
        "source_name": _fact(f"component-{index}"),
        "content_format": _fact("ai-stp-component-file/1"),
        "content_digest": _fact(digest_bytes("ai-stp:artifact:v1", payload)),
        "byte_length": _fact(len(payload)),
    }
    draft: dict[str, JsonValue] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": owner,
        "created_at": AT,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": facts,
    }
    stored = revisions.commit(connection, draft, device_id="device_test")
    versions.record(
        connection,
        stable_id=stable_id,
        version="1.0",
        passport_digest=digest_canonical("ai-stp:passport:v1", {"id": stable_id}),
        revision_id=stored.revision_id,
        at=AT,
    )
    return stable_id


def _materialize() -> tuple[str, ...]:
    """A released setup pinning released components, all built locally."""
    owner = new_id("account")
    with closing(open_registry(configured_path(), create=True)) as connection:
        pins = tuple(_release_component(connection, index, owner) for index in range(PIN_COUNT))
        members = tuple(
            setup_versions.MemberRef(
                stable_id=stable_id,
                version="1.0",
                passport_digest=digest_canonical("ai-stp:passport:v1", {"id": stable_id}),
            )
            for stable_id in pins
        )
        document = setup_versions.passport_content(
            connection,
            stable_id=SETUP,
            version=SETUP_VERSION,
            owner_id=owner,
            project_id="project_test",
            harness_id="codex",
            snapshot=digest_canonical("ai-stp:selection-snapshot:v1", {"members": len(members)}),
            members=members,
            at=AT,
        )
        stored = revisions.commit(connection, dict(document), device_id="device_test")
        versions.record(
            connection,
            stable_id=SETUP,
            version=SETUP_VERSION,
            passport_digest=digest_canonical("ai-stp:passport:v1", {"id": SETUP}),
            revision_id=stored.revision_id,
            at=AT,
        )
        connection.commit()
    # `passport_content` orders members by (stable_id, version), and the plan
    # follows the passport, so the expected order is that one rather than the
    # order they were created in.
    return tuple(sorted(pins))


def _plan() -> Any:
    return setup_publication.plan({"id": SETUP, "version": SETUP_VERSION}).payload


def _member(role: str, stable_id: str, plan_hash: str = "h") -> PublicationSetMemberView:
    return PublicationSetMemberView(
        role=role,  # pyright: ignore[reportArgumentType]
        object_kind="component" if role == "pinned_component" else "setup",
        stable_id=stable_id,
        version="1.0",
        plan_id=f"plan_{stable_id}",
        plan_hash=plan_hash,
    )


# --------------------------------------------------------------------------
# REQ-3810 — which members get a plan, and who decides what is public
# --------------------------------------------------------------------------


def test_planning_a_setup_plans_every_pin_and_the_setup_last(platform: _Platform) -> None:
    """The order is the confirmation order, and it is not alphabetical.

    A setup confirmed before its pins is refused by the platform's own pin
    aggregate, for a reason that reads like a defect in the setup.
    """
    pins = _materialize()

    view = _plan()

    assert [member.role for member in view.members] == [
        *["pinned_component"] * len(pins),
        "setup",
    ]
    assert view.members[-1].stable_id == SETUP
    assert {member.stable_id for member in view.members[:-1]} == set(pins)
    assert [kind for kind, _, _ in platform.created] == [
        *["component"] * len(pins),
        "setup",
    ]


def test_a_component_that_is_public_already_is_listed_and_not_replanned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leaving it out would describe less than the graph being published.

    Replanning it would ask the platform to publish what is already public.
    """
    pins = _materialize()
    fake = _Platform(public={pins[0]})
    _install(monkeypatch, fake)

    view = _plan()

    already = [member for member in view.members if member.already_published]
    assert [member.stable_id for member in already] == [pins[0]]
    assert already[0].plan_id == ""
    assert pins[0] not in {stable_id for _, stable_id, _ in fake.created}
    assert len(fake.created) == len(pins)  # the other pins, and the setup


def test_what_is_public_is_a_fact_about_the_platform_not_this_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local visibility says what this machine believes.

    Every first-party passport here is `visibility: public` locally, and none
    of them is on the platform. Reading the local value would plan nothing at
    all and report a setup as published that nobody had published.
    """
    _materialize()
    fake = _Platform(public=set())
    _install(monkeypatch, fake)

    view = _plan()

    assert all(not member.already_published for member in view.members)
    assert fake.created


def test_planning_something_that_is_not_a_setup_says_which_command_to_use(
    platform: _Platform,
) -> None:
    pins = _materialize()

    with pytest.raises(CliFailure) as raised:
        setup_publication.plan({"id": pins[0], "version": "1.0"})

    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert any("publication plan" in action for action in raised.value.next_actions)


def test_planning_a_version_this_machine_does_not_hold_is_not_found(
    platform: _Platform,
) -> None:
    _materialize()

    with pytest.raises(CliFailure) as raised:
        setup_publication.plan({"id": SETUP, "version": "9.9"})

    assert raised.value.code == "AI_STP_NOT_FOUND"


# --------------------------------------------------------------------------
# REQ-3811 — what the digest covers, and what replanning does
# --------------------------------------------------------------------------


def test_the_digest_covers_the_order_and_the_membership() -> None:
    """Any difference in what is published is a different decision."""
    first = _member("pinned_component", "component_a")
    second = _member("pinned_component", "component_b")
    setup = _member("setup", SETUP)

    base = publication_sets.set_digest([first, second, setup])

    assert publication_sets.set_digest([second, first, setup]) != base
    assert publication_sets.set_digest([first, setup]) != base
    assert (
        publication_sets.set_digest(
            [first, _member("pinned_component", "component_b", "other"), setup]
        )
        != base
    )
    assert publication_sets.set_digest([first, second, setup]) == base


def test_a_plan_moving_from_draft_to_ready_is_not_a_different_decision() -> None:
    """A digest that changed while somebody read it would make confirming
    impossible rather than safe."""
    member = _member("pinned_component", "component_a")

    assert publication_sets.set_digest([member]) == publication_sets.set_digest(
        [member.model_copy(update={"state": "ready"})]
    )


def test_planning_twice_without_a_change_is_the_same_set(platform: _Platform) -> None:
    _materialize()

    first = _plan()
    created = len(platform.created)
    second = _plan()

    assert second.set_digest == first.set_digest
    # The second plan asked the platform again, and stored one set rather than
    # two: replanning is idempotent by digest.
    assert len(platform.created) == created * 2
    with closing(open_registry(configured_path(), create=True)) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM setup_publication_set").fetchone()
    assert rows[0] == 1


def test_replanning_after_a_change_replaces_the_open_set(
    platform: _Platform, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two open sets for one setup version differ only in which is stale.

    Nothing on the wire says which, so the newer one replaces the older rather
    than standing beside it.
    """
    pins = _materialize()
    first = _plan()

    _install(monkeypatch, _Platform(public={pins[0]}))
    second = _plan()

    assert second.set_digest != first.set_digest
    with closing(open_registry(configured_path(), create=True)) as connection:
        held = connection.execute("SELECT set_digest FROM setup_publication_set").fetchall()
    assert [row[0] for row in held] == [second.set_digest]


# --------------------------------------------------------------------------
# REQ-3812 — confirmation: explicit, ordered, and resumable
# --------------------------------------------------------------------------


def test_confirming_without_the_flag_is_refused(platform: _Platform) -> None:
    _materialize()
    view = _plan()

    with pytest.raises(CliFailure) as raised:
        setup_publication.confirm({"set-digest": view.set_digest})

    assert raised.value.code == "AI_STP_USER_DECISION_REQUIRED"
    assert platform.confirmed == []


def test_confirming_publishes_every_member_in_order(platform: _Platform) -> None:
    pins = _materialize()
    view = _plan()

    settled = setup_publication.confirm({"set-digest": view.set_digest, "confirm": True}).payload

    assert settled.state == "published"
    assert platform.confirmed == [f"plan_{stable_id}" for stable_id in (*pins, SETUP)]
    assert all(member.state == "published" for member in settled.members)


def test_a_refused_component_stops_the_setup_and_leaves_the_rest_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Continuing would publish a setup pinning something the platform declined.

    What already published stays published — that is what makes the set
    resumable rather than an all-or-nothing that loses work on any refusal.
    """
    pins = _materialize()
    fake = _Platform(refuse=pins[1])
    _install(monkeypatch, fake)
    view = _plan()

    settled = setup_publication.confirm({"set-digest": view.set_digest, "confirm": True}).payload

    assert settled.state == "partial"
    assert fake.confirmed == [f"plan_{pins[0]}"]
    by_id = {member.stable_id: member for member in settled.members}
    assert by_id[pins[0]].state == "published"
    assert by_id[pins[1]].state == "failed"
    assert by_id[SETUP].state not in {"published"}


def test_a_set_from_another_account_or_device_is_refused(
    platform: _Platform, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stored set names who reviewed it, and only they may confirm it."""
    _materialize()
    view = _plan()

    class _Other(_Session):
        account_id = "account_someone_else"

    monkeypatch.setattr(setup_publication, "_session", lambda: _Other())

    with pytest.raises(CliFailure) as raised:
        setup_publication.confirm({"set-digest": view.set_digest, "confirm": True})

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert platform.confirmed == []


def test_a_digest_this_machine_never_reviewed_is_not_found(platform: _Platform) -> None:
    _materialize()

    with pytest.raises(CliFailure) as raised:
        setup_publication.confirm({"set-digest": "sha256:" + "0" * 64, "confirm": True})

    assert raised.value.code == "AI_STP_NOT_FOUND"
    assert platform.confirmed == []


def test_a_member_already_public_is_not_confirmed_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pins = _materialize()
    fake = _Platform(public={pins[0]})
    _install(monkeypatch, fake)
    view = _plan()

    setup_publication.confirm({"set-digest": view.set_digest, "confirm": True})

    assert f"plan_{pins[0]}" not in fake.confirmed
    assert f"plan_{pins[0]}" not in fake.bound
