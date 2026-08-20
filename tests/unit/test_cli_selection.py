"""The recommendation session: showing creates nothing, confirming creates once."""

import sqlite3
from collections.abc import Generator, Iterator
from contextlib import closing, contextmanager
from typing import cast

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, content, lifecycle, revisions, selection, versions
from ai_stp_cli.local.database import configured_path, open_registry, transaction
from ai_stp_foundation.canonical import JsonValue, from_json_bytes
from ai_stp_passports import SetupVersionPassport

AT = "2026-08-08T10:00:00.000Z"
SOON = "2026-08-08T11:00:00.000Z"
LATE = "2026-08-08T12:00:00.000Z"
OWNER = "account_01J0000000000000000000000A"
PROJECT = "project_01J0000000000000000000000B"
DEVICE = "device_test"
DEVELOPER_ID = "developer_01J0000000000000000000000D"
DEVICE_ID = "device_01J0000000000000000000000E"

#: Every table a registry record lives in. `REQ-622` says a proposal creates
#: none of them, and naming them here is what makes that assertable rather than
#: asserted about whichever one somebody remembered.
REGISTRY_TABLES = (
    "revision",
    "head",
    "content",
    "object_version",
    "recommendation_trace",
    "selected_version",
)


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        for stable_id, kind in (
            (DEVELOPER_ID, "developer"),
            (DEVICE_ID, "device"),
            (PROJECT, "project"),
        ):
            connection.execute(
                "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, ?, ?)",
                (stable_id, kind, AT),
            )
            revisions.commit(
                connection,
                {
                    "schema_version": 1,
                    "kind": kind,
                    "stable_id": stable_id,
                    "owner_id": OWNER,
                    "created_at": AT,
                    "visibility": "private",
                    "parent_revision_ids": [],
                    "facts": {},
                },  # pyright: ignore[reportArgumentType]
                device_id=DEVICE,
            )
        yield connection


def _context(connection: sqlite3.Connection, **overrides: str) -> selection.Context:
    developer = revisions.head(connection, DEVELOPER_ID)
    device = revisions.head(connection, DEVICE_ID)
    project = revisions.head(connection, PROJECT)
    assert developer is not None and device is not None and project is not None
    facts: dict[str, str] = {
        "project_id": PROJECT,
        "harness_id": "claude-code",
        "developer_revision": developer.revision_id,
        "device_revision": device.revision_id,
        "project_revision": project.revision_id,
        "policy_version": "selection-policy/1;result_limit=20",
    }
    facts.update(overrides)
    return selection.Context(**facts)


def _component(connection: sqlite3.Connection, suffix: str, *, version: str = "1.0") -> str:
    """One registered component with one released version, as a member needs."""
    stable_id = f"component_01J000000000000000000000{suffix}0"
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, AT),
    )
    stored = revisions.commit(
        connection,
        {  # pyright: ignore[reportArgumentType]
            "schema_version": 1,
            "kind": "component",
            "stable_id": stable_id,
            "owner_id": OWNER,
            "created_at": AT,
            "visibility": "private",
            "parent_revision_ids": [],
            "facts": {
                "harness_id": {
                    "value": "claude-code",
                    "origin": "observed",
                    "confirmation": "none",
                    "observed_at": AT,
                }
            },
        },
        device_id=DEVICE,
    )
    versions.record(
        connection,
        stable_id=stable_id,
        version=version,
        # The catalogue's digest, as `version_release` records it. A revision id
        # is a hash of the same bytes in another domain and would be refused.
        passport_digest=cache.digest_of(stored.envelope.model_dump(mode="json")),
        revision_id=stored.revision_id,
        at=AT,
    )
    return stable_id


def _full_component(connection: sqlite3.Connection, suffix: str) -> str:
    """One formal ComponentVersionPassport for aggregate setup metadata."""
    stable_id = f"component_01J000000000000000000000{suffix}0"
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, AT),
    )
    stored = revisions.commit(
        connection,
        {
            "schema_version": 1,
            "kind": "component",
            "stable_id": stable_id,
            "owner_id": OWNER,
            "created_at": AT,
            "visibility": "private",
            "parent_revision_ids": [],
            "facts": {},
            "name": "formal-component",
            "description": "A complete component passport.",
            "version": "1.0",
            "tags": ["tests"],
            "source": None,
            "artifact": {"digest": "sha256:" + "8" * 64, "size_bytes": 8},
            "harness_id": "claude-code",
            "required_env": [{"name": "EXAMPLE_TOKEN", "purpose": "Provider test"}],
            "requires_credentials": True,
            "requires_authorization": "user_account",
            "permissions": {
                "filesystem": [".claude/settings.json"],
                "network": ["https://example.test"],
                "process": ["claude"],
            },
            "external_endpoints": ["https://example.test"],
            "license": {"spdx_id": "MIT", "redistribution_allowed": True},
            "compatibility_evidence_refs": [],
            "component_type": "skill",
            "projection_kind": "native_files",
            "variant_id": None,
            "provides_capabilities": [],
            "requires_components": [],
            "requires_capabilities": [],
            "conflicts": {},
            "managed_paths": [".claude/settings.json"],
            "native_ids": [],
        },  # pyright: ignore[reportArgumentType]
        device_id=DEVICE,
    )
    versions.record(
        connection,
        stable_id=stable_id,
        version="1.0",
        passport_digest=cache.digest_of(stored.envelope.model_dump(mode="json")),
        revision_id=stored.revision_id,
        at=AT,
    )
    return stable_id


def _member(
    stable_id: str, connection: sqlite3.Connection, *, version: str = "1.0"
) -> selection.Member:
    recorded = versions.held(connection, stable_id, version)
    assert recorded is not None
    return selection.Member(
        stable_id=stable_id,
        version=version,
        passport_digest=recorded.passport_digest,
        lane="local_owner_or_pinned",
        lane_reason="your own or exactly pinned",
    )


def _counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        name: int(connection.execute(f"SELECT count(*) AS held FROM {name}").fetchone()["held"])
        for name in REGISTRY_TABLES
    }


# REQ-622: showing a composition must stay distinguishable from creating one.
def test_proposing_creates_no_version_no_target_and_no_registry_record(
    registry: sqlite3.Connection,
) -> None:
    member = _member(_component(registry, "A"), registry)
    before = _counts(registry)

    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )

    assert proposal.state(AT) == selection.STATE_OPEN
    after = _counts(registry)
    assert after["object_version"] == before["object_version"]
    assert after["selected_version"] == before["selected_version"] == 0
    assert after["recommendation_trace"] == before["recommendation_trace"] == 0
    assert after["revision"] == before["revision"], "no revision, so no object came into existence"


def test_a_proposal_is_not_an_entity(registry: sqlite3.Connection) -> None:
    member = _member(_component(registry, "B"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    found = registry.execute(
        "SELECT count(*) AS held FROM entity WHERE stable_id = ?", (proposal.proposal_id,)
    ).fetchone()
    assert found["held"] == 0


def test_several_proposals_may_be_open_for_one_pair(registry: sqlite3.Connection) -> None:
    """`ADR-0027`: how many to show is the agent's decision, not the product's."""
    first = _member(_component(registry, "C"), registry)
    second = _member(_component(registry, "D"), registry)
    selection.propose(
        registry, context=_context(registry), members=(first,), at=AT, expires_at=SOON
    )
    selection.propose(
        registry, context=_context(registry), members=(second,), at=AT, expires_at=SOON
    )
    assert (
        len(
            selection.open_proposals(registry, project_id=PROJECT, harness_id="claude-code", now=AT)
        )
        == 2
    )


def test_a_composition_of_nothing_is_refused(registry: sqlite3.Connection) -> None:
    with pytest.raises(CliFailure) as raised:
        selection.propose(registry, context=_context(registry), members=(), at=AT, expires_at=SOON)
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_one_object_twice_in_a_composition_is_refused(registry: sqlite3.Connection) -> None:
    member = _member(_component(registry, "E"), registry)
    with pytest.raises(CliFailure) as raised:
        selection.propose(
            registry, context=_context(registry), members=(member, member), at=AT, expires_at=SOON
        )
    assert raised.value.code == "AI_STP_CONFLICT"


# REQ-624: the snapshot is what staleness is decided from, so it must depend on
# every input and on nothing else.
def test_the_snapshot_does_not_depend_on_the_order_members_were_listed(
    registry: sqlite3.Connection,
) -> None:
    first = _member(_component(registry, "F"), registry)
    second = _member(_component(registry, "G"), registry)
    context = _context(registry)
    assert context.snapshot((first, second)) == context.snapshot((second, first))


@pytest.mark.parametrize(
    "changed",
    ["harness_id", "developer_revision", "device_revision", "project_revision", "policy_version"],
)
def test_every_part_of_the_context_changes_the_snapshot(
    registry: sqlite3.Connection, changed: str
) -> None:
    member = _member(_component(registry, "H"), registry)
    base = _context(registry)
    moved = _context(registry, **{changed: "something-else"})
    assert base.snapshot((member,)) != moved.snapshot((member,))


def test_a_changed_member_digest_changes_the_snapshot(registry: sqlite3.Connection) -> None:
    member = _member(_component(registry, "J"), registry)
    other = selection.Member(
        stable_id=member.stable_id,
        version=member.version,
        passport_digest="sha256:" + "9" * 64,
        lane=member.lane,
        lane_reason=member.lane_reason,
    )
    assert _context(registry).snapshot((member,)) != _context(registry).snapshot((other,))


def test_the_lane_reason_does_not_change_the_snapshot(registry: sqlite3.Connection) -> None:
    """Staleness is about what is composed, not about how it was worded."""
    member = _member(_component(registry, "K"), registry)
    reworded = selection.Member(
        stable_id=member.stable_id,
        version=member.version,
        passport_digest=member.passport_digest,
        lane=member.lane,
        lane_reason="a different sentence entirely",
    )
    assert _context(registry).snapshot((member,)) == _context(registry).snapshot((reworded,))


# REQ-623: three writes or none.
def test_confirming_freezes_one_private_version_its_trace_and_its_pin(
    registry: sqlite3.Connection,
) -> None:
    member = _member(_component(registry, "5"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )

    confirmed = selection.confirm(
        registry,
        proposal.proposal_id,
        context=_context(registry),
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )

    assert confirmed.created
    assert confirmed.version == versions.FIRST_VERSION
    assert confirmed.state == selection.PENDING_INSTALL
    assert selection.selected(registry, project_id=PROJECT, harness_id="claude-code") == (
        confirmed.stable_id,
        confirmed.version,
        selection.PENDING_INSTALL,
    )
    trace = selection.trace_of(registry, confirmed.stable_id, confirmed.version)
    assert trace["policy_version"] == _context(registry).policy_version
    assert trace["candidates"]


def test_the_frozen_version_is_private(registry: sqlite3.Connection) -> None:
    member = _member(_component(registry, "M"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    confirmed = selection.confirm(
        registry,
        proposal.proposal_id,
        context=_context(registry),
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )
    stored = revisions.head(registry, confirmed.stable_id)
    assert stored is not None
    assert stored.envelope.visibility == "private"


def test_confirmation_stores_a_full_setup_passport_and_independent_definition(
    registry: sqlite3.Connection,
) -> None:
    member = _member(_component(registry, "Q"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    confirmed = selection.confirm(
        registry,
        proposal.proposal_id,
        context=_context(registry),
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )

    stored = revisions.head(registry, confirmed.stable_id)
    assert stored is not None
    passport = SetupVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
    assert passport.version == confirmed.version
    assert passport.harness_id == "claude-code"
    assert passport.components[0].stable_id == member.stable_id
    assert passport.model_extra is not None
    assert passport.model_extra["artifact_format"] == "ai-stp-setup-definition/1"
    assert passport.model_extra["member_metadata_complete"] is False
    assert passport.license.redistribution_allowed is False

    raw = content.get(registry, passport.artifact.digest)
    assert len(raw) == passport.artifact.size_bytes
    definition = from_json_bytes(raw)
    assert isinstance(definition, dict)
    assert definition["stable_id"] == confirmed.stable_id
    assert definition["input_digest"] == proposal.snapshot
    members = definition["components"]
    assert isinstance(members, list)
    assert cast(dict[str, JsonValue], members[0])["passport_digest"] == member.passport_digest


def test_setup_passport_aggregates_complete_component_metadata(
    registry: sqlite3.Connection,
) -> None:
    member = _member(_full_component(registry, "R"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    confirmed = selection.confirm(
        registry,
        proposal.proposal_id,
        context=_context(registry),
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )

    stored = revisions.head(registry, confirmed.stable_id)
    assert stored is not None
    passport = SetupVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
    assert passport.model_extra is not None
    assert passport.model_extra["member_metadata_complete"] is True
    assert [(item.name, item.purpose) for item in passport.required_env] == [
        ("EXAMPLE_TOKEN", "Provider test")
    ]
    assert passport.requires_credentials is True
    assert passport.requires_authorization == "user_account"
    assert passport.permissions.filesystem == [".claude/settings.json"]
    assert passport.external_endpoints == ["https://example.test"]
    assert passport.license.spdx_id == "MIT"
    assert passport.license.redistribution_allowed is True


# REQ-624: a repeat is a success that returns the same version.
def test_confirming_twice_returns_one_version_and_makes_no_second_object(
    registry: sqlite3.Connection,
) -> None:
    member = _member(_component(registry, "N"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )

    first = selection.confirm(
        registry,
        proposal.proposal_id,
        context=_context(registry),
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )
    second = selection.confirm(
        registry,
        proposal.proposal_id,
        context=_context(registry),
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )

    assert (second.stable_id, second.version) == (first.stable_id, first.version)
    assert first.created and not second.created
    setups = registry.execute("SELECT count(*) AS held FROM entity WHERE kind = 'setup'").fetchone()
    assert setups["held"] == 1
    traces = registry.execute("SELECT count(*) AS held FROM recommendation_trace").fetchone()
    assert traces["held"] == 1


def test_an_already_confirmed_proposal_replays_even_when_the_context_moved(
    registry: sqlite3.Connection,
) -> None:
    """A version that exists cannot become an error because the world moved on."""
    member = _member(_component(registry, "P"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    first = selection.confirm(
        registry,
        proposal.proposal_id,
        context=_context(registry),
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )
    replay = selection.confirm(
        registry,
        proposal.proposal_id,
        context=_context(registry, policy_version="selection-policy/1;result_limit=5"),
        owner_id=OWNER,
        device_id=DEVICE,
        at=LATE,
    )
    assert replay.stable_id == first.stable_id
    assert not replay.created


# The five confirmation errors of `selection-proposal.md`, each distinguishable.
def test_a_changed_context_makes_confirmation_stale(registry: sqlite3.Connection) -> None:
    member = _member(_component(registry, "Q"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    with pytest.raises(CliFailure) as raised:
        selection.confirm(
            registry,
            proposal.proposal_id,
            context=_context(registry, project_revision="revision_" + "d" * 64),
            owner_id=OWNER,
            device_id=DEVICE,
            at=AT,
        )
    assert raised.value.code == "AI_STP_PLAN_STALE"
    assert _counts(registry)["object_version"] == 1, "only the member's own version exists"


def test_an_expired_proposal_is_stale_rather_than_unknown(registry: sqlite3.Connection) -> None:
    member = _member(_component(registry, "R"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    with pytest.raises(CliFailure) as raised:
        selection.confirm(
            registry,
            proposal.proposal_id,
            context=_context(registry),
            owner_id=OWNER,
            device_id=DEVICE,
            at=LATE,
        )
    assert raised.value.code == "AI_STP_PLAN_STALE"


def test_an_unknown_proposal_is_not_found(registry: sqlite3.Connection) -> None:
    with pytest.raises(CliFailure) as raised:
        selection.confirm(
            registry,
            "proposal_01J0000000000000000000000Z",
            context=_context(registry),
            owner_id=OWNER,
            device_id=DEVICE,
            at=AT,
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_a_cancelled_proposal_cannot_be_confirmed(registry: sqlite3.Connection) -> None:
    member = _member(_component(registry, "S"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    selection.cancel(registry, proposal.proposal_id, at=AT)
    with pytest.raises(CliFailure) as raised:
        selection.confirm(
            registry,
            proposal.proposal_id,
            context=_context(registry),
            owner_id=OWNER,
            device_id=DEVICE,
            at=AT,
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_a_member_deleted_after_proposing_is_its_own_refusal(
    registry: sqlite3.Connection,
) -> None:
    """Not staleness: the inputs the snapshot covers did not move, the object did."""
    stable_id = _component(registry, "T")
    proposal = selection.propose(
        registry,
        context=_context(registry),
        members=(_member(stable_id, registry),),
        at=AT,
        expires_at=SOON,
    )
    lifecycle.entomb(registry, stable_id, reason="removed by the owner", at=AT)

    with pytest.raises(CliFailure) as raised:
        selection.confirm(
            registry,
            proposal.proposal_id,
            context=_context(registry),
            owner_id=OWNER,
            device_id=DEVICE,
            at=AT,
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_a_member_whose_version_is_gone_is_refused(registry: sqlite3.Connection) -> None:
    stable_id = _component(registry, "6")
    proposal = selection.propose(
        registry,
        context=_context(registry),
        members=(_member(stable_id, registry),),
        at=AT,
        expires_at=SOON,
    )
    registry.execute("DELETE FROM object_version WHERE stable_id = ?", (stable_id,))
    with pytest.raises(CliFailure) as raised:
        selection.confirm(
            registry,
            proposal.proposal_id,
            context=_context(registry),
            owner_id=OWNER,
            device_id=DEVICE,
            at=AT,
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_a_member_changed_between_preflight_and_write_lock_is_refused_atomically(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    stable_id = _component(registry, "7")
    proposal = selection.propose(
        registry,
        context=_context(registry),
        members=(_member(stable_id, registry),),
        at=AT,
        expires_at=SOON,
    )
    before = _counts(registry)

    @contextmanager
    def concurrent_change(connection: sqlite3.Connection) -> Generator[sqlite3.Connection]:
        with transaction(connection):
            connection.execute("DELETE FROM object_version WHERE stable_id = ?", (stable_id,))
            yield connection

    monkeypatch.setattr(selection, "transaction", concurrent_change)
    with pytest.raises(CliFailure) as raised:
        selection.confirm(
            registry,
            proposal.proposal_id,
            context=_context(registry),
            owner_id=OWNER,
            device_id=DEVICE,
            at=AT,
        )

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert _counts(registry) == before, "the locked recheck and concurrent change did not roll back"


def test_a_context_head_changed_before_the_write_lock_makes_the_plan_stale(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _member(_component(registry, "8"), registry)
    context = _context(registry)
    proposal = selection.propose(
        registry, context=context, members=(member,), at=AT, expires_at=SOON
    )
    original = revisions.get(registry, context.developer_revision)
    assert original is not None

    @contextmanager
    def concurrent_context_change(
        connection: sqlite3.Connection,
    ) -> Generator[sqlite3.Connection]:
        with transaction(connection):
            document = cast(
                dict[str, JsonValue],
                original.envelope.model_dump(mode="json", exclude={"revision_id"}),
            )
            document["parent_revision_ids"] = [original.revision_id]
            document["facts"] = {
                "changed": {
                    "value": True,
                    "origin": "observed",
                    "confirmation": "none",
                    "observed_at": AT,
                }
            }
            revisions.commit(connection, document, device_id=DEVICE)
            yield connection

    monkeypatch.setattr(selection, "transaction", concurrent_context_change)
    with pytest.raises(CliFailure) as raised:
        selection.confirm(
            registry,
            proposal.proposal_id,
            context=context,
            owner_id=OWNER,
            device_id=DEVICE,
            at=AT,
        )

    assert raised.value.code == "AI_STP_PLAN_STALE"
    restored = revisions.head(registry, DEVELOPER_ID)
    assert restored is not None and restored.revision_id == original.revision_id


# REQ-623 again, from the other side: a failure part-way leaves none of the three.
def test_a_failure_while_freezing_leaves_no_version_no_trace_and_no_pin(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _member(_component(registry, "V"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    before = _counts(registry)

    def refuse(*_: object, **__: object) -> versions.Recorded:
        raise RuntimeError("injected failure after the entity and revision were written")

    monkeypatch.setattr(versions, "record", refuse)
    with pytest.raises(RuntimeError):
        selection.confirm(
            registry,
            proposal.proposal_id,
            context=_context(registry),
            owner_id=OWNER,
            device_id=DEVICE,
            at=AT,
        )

    assert _counts(registry) == before, "the whole freeze rolled back, including the revision"
    setups = registry.execute("SELECT count(*) AS held FROM entity WHERE kind = 'setup'").fetchone()
    assert setups["held"] == 0
    held = selection.held(registry, proposal.proposal_id)
    assert held is not None and held.confirmed_version is None


def test_the_journal_records_a_failed_freeze(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The attempt is a fact even when its result is not."""
    member = _member(_component(registry, "W"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )

    def refuse(*_: object, **__: object) -> versions.Recorded:
        raise RuntimeError("injected failure")

    monkeypatch.setattr(versions, "record", refuse)
    with pytest.raises(RuntimeError):
        selection.confirm(
            registry,
            proposal.proposal_id,
            context=_context(registry),
            owner_id=OWNER,
            device_id=DEVICE,
            at=AT,
        )
    row = registry.execute(
        "SELECT state FROM operation WHERE kind = 'selection.confirm'"
    ).fetchone()
    assert row is not None and row["state"] == "failed"


def test_cancelling_is_idempotent_and_creates_nothing(registry: sqlite3.Connection) -> None:
    member = _member(_component(registry, "X"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    before = _counts(registry)
    first = selection.cancel(registry, proposal.proposal_id, at=AT)
    second = selection.cancel(registry, proposal.proposal_id, at=LATE)
    assert first.cancelled_at == second.cancelled_at == AT
    assert _counts(registry) == before


def test_a_confirmed_proposal_cannot_be_cancelled(registry: sqlite3.Connection) -> None:
    member = _member(_component(registry, "Y"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    selection.confirm(
        registry,
        proposal.proposal_id,
        context=_context(registry),
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )
    with pytest.raises(CliFailure) as raised:
        selection.cancel(registry, proposal.proposal_id, at=LATE)
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


@pytest.mark.parametrize(
    ("now", "expected"),
    [(AT, selection.STATE_OPEN), (SOON, selection.STATE_EXPIRED), (LATE, selection.STATE_EXPIRED)],
)
def test_expiry_is_decided_at_a_named_moment(
    registry: sqlite3.Connection, now: str, expected: str
) -> None:
    member = _member(_component(registry, "Z"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    assert proposal.state(now) == expected


def test_only_open_proposals_are_listed(registry: sqlite3.Connection) -> None:
    kept = _member(_component(registry, "1"), registry)
    dropped = _member(_component(registry, "2"), registry)
    open_one = selection.propose(
        registry, context=_context(registry), members=(kept,), at=AT, expires_at=SOON
    )
    cancelled = selection.propose(
        registry, context=_context(registry), members=(dropped,), at=AT, expires_at=SOON
    )
    selection.cancel(registry, cancelled.proposal_id, at=AT)

    listed = selection.open_proposals(
        registry, project_id=PROJECT, harness_id="claude-code", now=AT
    )
    assert [item.proposal_id for item in listed] == [open_one.proposal_id]


def test_every_declared_state_is_reachable(registry: sqlite3.Connection) -> None:
    """A state nothing can produce is a state nobody has to handle."""
    member = _member(_component(registry, "3"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    seen = {proposal.state(AT), proposal.state(LATE)}
    selection.confirm(
        registry,
        proposal.proposal_id,
        context=_context(registry),
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )
    confirmed = selection.held(registry, proposal.proposal_id)
    assert confirmed is not None
    seen.add(confirmed.state(AT))

    other = selection.propose(
        registry,
        context=_context(registry),
        members=(_member(_component(registry, "4"), registry),),
        at=AT,
        expires_at=SOON,
    )
    seen.add(selection.cancel(registry, other.proposal_id, at=AT).state(AT))
    assert seen == selection.STATES


def test_the_frozen_version_carries_the_catalogue_digest_not_a_revision_id(
    registry: sqlite3.Connection,
) -> None:
    """One way of hashing a passport, or verification against a server fails.

    A revision id is a hash in a different domain and is right there to be
    reached for. Using it would make every check of this version against a
    conforming catalogue fail, and fail looking like a corrupted download.
    """
    member = _member(_component(registry, "7"), registry)
    proposal = selection.propose(
        registry, context=_context(registry), members=(member,), at=AT, expires_at=SOON
    )
    confirmed = selection.confirm(
        registry,
        proposal.proposal_id,
        context=_context(registry),
        owner_id=OWNER,
        device_id=DEVICE,
        at=AT,
    )

    recorded = versions.held(registry, confirmed.stable_id, confirmed.version)
    stored = revisions.head(registry, confirmed.stable_id)
    assert recorded is not None and stored is not None
    assert recorded.passport_digest == cache.digest_of(stored.envelope.model_dump(mode="json"))
    assert recorded.passport_digest != recorded.revision_id
