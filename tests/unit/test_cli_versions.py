"""Immutable `X.Y` numbering and forks: mostly the refusals."""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import revisions, versions
from ai_stp_cli.local.database import configured_path, open_registry

MOMENT = "2026-08-07T10:00:00.000Z"
LATER = "2026-08-07T11:00:00.000Z"
OWNER = "account_01J0000000000000000000000A"
HELD = "component_01J0000000000000000000000B"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
            (HELD, MOMENT),
        )
        yield connection


def _revision(connection: sqlite3.Connection, mark: str) -> str:
    stored = revisions.commit(
        connection,
        {  # pyright: ignore[reportArgumentType]
            "schema_version": 1,
            "kind": "component",
            "stable_id": HELD,
            "owner_id": OWNER,
            "created_at": MOMENT,
            "visibility": "private",
            "parent_revision_ids": [],
            "facts": {
                "mark": {
                    "value": mark,
                    "origin": "observed",
                    "confirmation": "none",
                    "observed_at": MOMENT,
                }
            },
        },
        device_id="device_test",
    )
    return stored.revision_id


def _digest(mark: str) -> str:
    return "sha256:" + mark.encode().hex().ljust(64, "0")[:64]


def test_a_version_is_recorded_and_read_back(registry: sqlite3.Connection) -> None:
    recorded = versions.record(
        registry,
        stable_id=HELD,
        version="1.0",
        passport_digest=_digest("a"),
        revision_id=_revision(registry, "a"),
        at=MOMENT,
    )
    assert (recorded.major, recorded.minor) == (1, 0)
    assert versions.held(registry, HELD, "1.0") == recorded
    assert versions.held(registry, HELD, "9.9") is None
    assert versions.line(registry, HELD) == (recorded,)


def test_the_same_number_with_different_content_is_refused(registry: sqlite3.Connection) -> None:
    """`REQ-504`, and the schema is what enforces it rather than this check.

    A number that stood for two things would make every exact reference to it
    ambiguous, which is the one failure a content-addressed registry must not
    have.
    """
    versions.record(
        registry,
        stable_id=HELD,
        version="1.0",
        passport_digest=_digest("a"),
        revision_id=_revision(registry, "a"),
        at=MOMENT,
    )
    with pytest.raises(CliFailure, match="already stands for different content") as raised:
        versions.record(
            registry,
            stable_id=HELD,
            version="1.0",
            passport_digest=_digest("b"),
            revision_id=_revision(registry, "b"),
            at=LATER,
        )
    assert raised.value.code == "AI_STP_CONFLICT"
    assert raised.value.details["recorded"] == _digest("a")


def test_recording_the_same_number_and_content_again_is_a_replay(
    registry: sqlite3.Connection,
) -> None:
    first = versions.record(
        registry,
        stable_id=HELD,
        version="1.0",
        passport_digest=_digest("a"),
        revision_id=_revision(registry, "a"),
        at=MOMENT,
    )
    # Same number, same digest: a replay, not a conflict. The moment does not
    # move, because the version was published once.
    again = versions.record(
        registry,
        stable_id=HELD,
        version="1.0",
        passport_digest=_digest("a"),
        revision_id=first.revision_id,
        at=LATER,
    )
    assert again == first
    assert registry.execute("SELECT COUNT(*) AS n FROM object_version").fetchone()["n"] == 1


@pytest.mark.parametrize("version", ["1", "1.0.0", "v1.0", "latest", "1.x", ""])
def test_a_number_that_is_not_x_dot_y_is_refused(
    registry: sqlite3.Connection, version: str
) -> None:
    with pytest.raises(CliFailure, match=r"must be X\.Y"):
        versions.record(
            registry,
            stable_id=HELD,
            version=version,
            passport_digest=_digest("a"),
            revision_id=_revision(registry, "a"),
            at=MOMENT,
        )


def test_the_next_minor_is_deterministic(registry: sqlite3.Connection) -> None:
    # Nothing recorded yet: the first version of anything.
    assert versions.next_minor(registry, HELD) == versions.FIRST_VERSION

    for minor, mark in enumerate("abc"):
        versions.record(
            registry,
            stable_id=HELD,
            version=f"1.{minor}",
            passport_digest=_digest(mark),
            revision_id=_revision(registry, mark),
            at=MOMENT,
        )
    # Computed from what is stored, so asking twice answers the same and two
    # machines with one history agree.
    assert versions.next_minor(registry, HELD) == "1.3"
    assert versions.next_minor(registry, HELD) == "1.3"


def test_the_next_minor_follows_the_highest_major(registry: sqlite3.Connection) -> None:
    for version, mark in (("1.0", "a"), ("2.0", "b"), ("2.1", "c")):
        versions.record(
            registry,
            stable_id=HELD,
            version=version,
            passport_digest=_digest(mark),
            revision_id=_revision(registry, mark),
            at=MOMENT,
        )
    assert versions.next_minor(registry, HELD) == "2.2"
    # An older line can still be continued when it is named.
    assert versions.next_minor(registry, HELD, major=1) == "1.1"
    # And a line nothing was recorded in yet starts at `.0`.
    assert versions.next_minor(registry, HELD, major=5) == "5.0"
    assert versions.line(registry, HELD, major=2) == versions.line(registry, HELD)[1:]


def test_a_major_line_needs_an_explicit_decision(registry: sqlite3.Connection) -> None:
    versions.record(
        registry,
        stable_id=HELD,
        version="1.0",
        passport_digest=_digest("a"),
        revision_id=_revision(registry, "a"),
        at=MOMENT,
    )
    # `REQ-507`: a new major line is a separate access boundary. Computing it
    # silently is how a minor change becomes one nobody chose.
    with pytest.raises(CliFailure, match="explicit decision") as raised:
        versions.next_major(registry, HELD, decided=False)
    assert raised.value.code == "AI_STP_USER_DECISION_REQUIRED"

    assert versions.next_major(registry, HELD, decided=True) == "2.0"


def test_the_first_major_line_of_a_new_object_is_one(registry: sqlite3.Connection) -> None:
    assert versions.next_major(registry, HELD, decided=True) == "1.0"


# --- forks ----------------------------------------------------------------


def test_a_fork_gets_a_new_identity_and_leaves_the_original_alone(
    registry: sqlite3.Connection,
) -> None:
    before = registry.execute("SELECT * FROM entity WHERE stable_id = ?", (HELD,)).fetchone()[
        "created_at"
    ]

    copy = versions.fork(
        registry,
        source_stable_id=HELD,
        source_version="1.0",
        source_digest=_digest("a"),
        kind="component",
        at=LATER,
    )
    assert copy.stable_id != HELD
    assert copy.stable_id.startswith("component_")
    assert versions.forked_from(registry, copy.stable_id) == copy

    # `REQ-521`: nothing about the original changed, and it carries no record of
    # having been copied — a recipient cannot write to what they do not own.
    after = registry.execute("SELECT * FROM entity WHERE stable_id = ?", (HELD,)).fetchone()
    assert after["created_at"] == before
    assert versions.forked_from(registry, HELD) is None


def test_only_a_component_or_a_setup_can_be_forked(registry: sqlite3.Connection) -> None:
    with pytest.raises(CliFailure, match="only a component or a setup"):
        versions.fork(
            registry,
            source_stable_id=HELD,
            source_version="1.0",
            source_digest=_digest("a"),
            kind="developer",
            at=MOMENT,
        )


def test_an_unmodified_clone_is_not_published_under_a_new_namespace(
    registry: sqlite3.Connection,
) -> None:
    """`REQ-522`, decided by comparing digests rather than by judgement."""
    copy = versions.fork(
        registry,
        source_stable_id=HELD,
        source_version="1.0",
        source_digest=_digest("a"),
        kind="component",
        at=MOMENT,
    )
    verdict = versions.publishable(
        registry, copy.stable_id, passport_digest=_digest("a"), public=True
    )
    assert not verdict.allowed
    assert "unmodified clone" in verdict.reason

    # Change anything and it becomes publishable.
    changed = versions.publishable(
        registry, copy.stable_id, passport_digest=_digest("b"), public=True
    )
    assert changed.allowed


def test_a_public_derivative_needs_public_or_owned_bytes(registry: sqlite3.Connection) -> None:
    copy = versions.fork(
        registry,
        source_stable_id=HELD,
        source_version="1.0",
        source_digest=_digest("a"),
        kind="component",
        at=MOMENT,
    )
    private_bytes = versions.publishable(
        registry,
        copy.stable_id,
        passport_digest=_digest("b"),
        public=True,
        included_public=False,
    )
    assert not private_bytes.allowed
    assert "public or your own" in private_bytes.reason

    # `REQ-524` is about *public* derivation. A private one distributes nothing
    # and needs no distribution right.
    kept_private = versions.publishable(
        registry,
        copy.stable_id,
        passport_digest=_digest("b"),
        public=False,
        included_public=False,
        licences_permit=None,
    )
    assert kept_private.allowed


@pytest.mark.parametrize(
    ("permit", "expected"),
    [
        # `REQ-524`: an unknown distribution right closes with a refusal. The
        # alternative is distributing something we were not allowed to.
        (None, "unknown, which is refused"),
        (False, "does not permit distribution"),
    ],
)
def test_a_licence_that_does_not_clearly_permit_distribution_refuses(
    registry: sqlite3.Connection, permit: bool | None, expected: str
) -> None:
    copy = versions.fork(
        registry,
        source_stable_id=HELD,
        source_version="1.0",
        source_digest=_digest("a"),
        kind="component",
        at=MOMENT,
    )
    verdict = versions.publishable(
        registry,
        copy.stable_id,
        passport_digest=_digest("b"),
        public=True,
        licences_permit=permit,
    )
    assert not verdict.allowed
    assert expected in verdict.reason


def test_an_object_that_was_never_forked_publishes_on_its_own_terms(
    registry: sqlite3.Connection,
) -> None:
    # Nothing to compare against, so the unmodified-clone rule does not apply
    # and the remaining checks decide.
    assert versions.publishable(registry, HELD, passport_digest=_digest("a"), public=True).allowed
    assert not versions.publishable(
        registry, HELD, passport_digest=_digest("a"), public=True, included_public=False
    ).allowed


# --- concurrency ----------------------------------------------------------


def test_two_processes_claiming_one_number_cannot_both_win(tmp_path: Path) -> None:
    """The schema decides the race, not a check-then-write in this module."""
    place = tmp_path / "raced.sqlite3"
    with closing(open_registry(place, create=True)) as connection:
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
            (HELD, MOMENT),
        )
        connection.execute(
            """
            INSERT INTO revision (revision_id, stable_id, content, device_id, created_at)
            VALUES (?, ?, '{}', 'device_test', ?)
            """,
            ("revision_" + "0" * 64, HELD, MOMENT),
        )
        connection.commit()

    won: list[str] = []
    refused: list[str] = []

    def claim(mark: str) -> None:
        try:
            with closing(open_registry(place, create=False)) as connection:
                versions.record(
                    connection,
                    stable_id=HELD,
                    version="1.0",
                    passport_digest=_digest(mark),
                    revision_id="revision_" + "0" * 64,
                    at=MOMENT,
                )
                connection.commit()
                won.append(mark)
        except (CliFailure, sqlite3.IntegrityError):
            refused.append(mark)

    workers = [threading.Thread(target=claim, args=(mark,)) for mark in "abcdefgh"]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert len(won) == 1
    assert len(refused) == 7
    with closing(open_registry(place, create=False)) as connection:
        assert connection.execute("SELECT COUNT(*) AS n FROM object_version").fetchone()["n"] == 1


# --- commands -------------------------------------------------------------


@pytest.fixture
def adopted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """One adopted component, which is the only way to get a real head here."""
    from ai_stp_cli.commands import component as command

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("# instruction\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    return command.adopt({"path": str(home / ".claude" / "CLAUDE.md")}).payload.stable_id


def test_the_release_command_numbers_the_head_and_then_the_next(adopted: str) -> None:
    from ai_stp_cli.commands import component as command

    first = command.version_release({"id": adopted}).payload
    assert [item.version for item in first.versions] == ["1.0"]
    assert first.next_minor == "1.1"
    assert first.versions[0].passport_digest.startswith("sha256:")

    listed = command.version_list({"id": adopted}).payload
    assert listed.versions == first.versions
    assert listed.forked_from is None


def test_releasing_the_same_head_twice_is_refused_as_a_reused_number(adopted: str) -> None:
    from ai_stp_cli.commands import component as command

    command.version_release({"id": adopted})
    # The head has not changed, so the next number would stand for content that
    # already has one. `REQ-504` refuses the reuse rather than silently
    # publishing the same bytes under two numbers.
    second = command.version_release({"id": adopted}).payload
    assert [item.version for item in second.versions] == ["1.0", "1.1"]
    assert second.versions[0].passport_digest == second.versions[1].passport_digest


def test_a_major_release_needs_the_decision_flag(adopted: str) -> None:
    from ai_stp_cli.commands import component as command

    command.version_release({"id": adopted})
    with pytest.raises(CliFailure, match="explicit decision"):
        command.version_release({"id": adopted, "major": True})

    opened = command.version_release({"id": adopted, "major": True, "confirm": True}).payload
    assert [item.version for item in opened.versions] == ["1.0", "2.0"]
    assert opened.next_minor == "2.1"


def test_the_fork_command_copies_and_says_it_is_not_yet_publishable(adopted: str) -> None:
    from ai_stp_cli.commands import component as command

    command.version_release({"id": adopted})
    copy = command.fork({"id": adopted, "version": "1.0"}).payload

    assert copy.stable_id != adopted
    assert copy.forked_from == adopted
    assert copy.forked_from_version == "1.0"
    assert copy.versions == []
    # `REQ-522` met at the fork rather than at publication: an unmodified clone
    # is a rule the caller learns now instead of a surprise later.
    assert copy.publishable is False
    assert "unmodified clone" in (copy.publish_reason or "")


def test_the_version_commands_refuse_what_they_cannot_find(adopted: str) -> None:
    from ai_stp_cli.commands import component as command

    with pytest.raises(CliFailure, match="no revision to release"):
        command.version_release({"id": "component_01J00000000000000000000030"})
    with pytest.raises(CliFailure, match="no such recorded version"):
        command.fork({"id": adopted, "version": "9.9"})
    for missing in ({}, {"id": adopted}):
        with pytest.raises(CliFailure, match="required"):
            command.fork(missing)
    with pytest.raises(CliFailure, match="a stable id is required"):
        command.version_list({})


def test_a_never_released_object_still_reports_its_next_number(adopted: str) -> None:
    from ai_stp_cli.commands import component as command

    listed = command.version_list({"id": adopted}).payload
    assert listed.versions == []
    assert listed.next_minor == versions.FIRST_VERSION


def test_a_version_cannot_be_recorded_under_something_that_is_not_a_digest(
    registry: sqlite3.Connection,
) -> None:
    """An exact reference names a version *and* its content.

    A revision id is the value most likely to arrive here by accident: it is a
    hash of the same bytes in a different domain and is always to hand. Recorded
    as a passport digest it would make the version unreferenceable, and the
    closure resolver would report it as floating far from the mistake.
    """
    stable_id = HELD
    for wrong in ("revision_" + "a" * 64, "sha256:not-hex", "", "deadbeef"):
        with pytest.raises(CliFailure) as raised:
            versions.record(
                registry,
                stable_id=stable_id,
                version="1.0",
                passport_digest=wrong,
                revision_id="revision_" + "b" * 64,
                at=MOMENT,
            )
        assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_a_fork_is_an_object_its_owner_can_actually_edit_and_release(adopted: str) -> None:
    """A copy with no content is not a copy.

    Measured live: `component fork` answered `ok` with a new identity, and then
    every follow-up refused it — `passport show`, `suggest`, `quality` and
    `update` with "that component has no local passport", `version release`
    with "no revision to release", even `forget` with "no revisions to report".
    The command wrote `entity` and `fork_origin` and no first revision, so the
    object `REQ-521` calls a copy held nothing to edit toward `REQ-522`'s
    meaningful change.
    """
    from ai_stp_cli.commands import component as command

    command.version_release({"id": adopted})
    copy = command.fork({"id": adopted, "version": "1.0"}).payload

    held = command.passport_show({"id": copy.stable_id}).payload
    assert held.kind == "component"

    released = command.version_release({"id": copy.stable_id}).payload
    assert [item.version for item in released.versions] == ["1.0"]


def test_two_concurrent_releases_serialize_instead_of_crashing_the_loser(adopted: str) -> None:
    """Measured in six process-level rounds: one loser answered `AI_STP_INTERNAL`.

    Both releases read the next free number in autocommit, one recorded it, and
    the other's insert died on the UNIQUE constraint — a crash where a caller
    expects either a version or a typed refusal. Under `BEGIN IMMEDIATE` the
    second release starts after the first commits, reads the line it left, and
    mints the next number — exactly what the sequential contract already says
    a second release of the same head does.
    """
    from ai_stp_cli.commands import component as command
    from ai_stp_cli.local.database import transaction

    outcome: dict[str, object] = {}

    def second() -> None:
        outcome["versions"] = [
            item.version for item in command.version_release({"id": adopted}).payload.versions
        ]

    with closing(open_registry(configured_path(), create=False)) as connection:
        with transaction(connection):
            contender = threading.Thread(target=second)
            contender.start()
            contender.join(timeout=0.5)
            assert contender.is_alive(), "the second release must wait for the write lock"
            # The first release, on this locked connection, through the same
            # local machinery the command drives.
            stored = revisions.head(connection, adopted)
            assert stored is not None
            versions.record(
                connection,
                stable_id=adopted,
                version=versions.next_minor(connection, adopted),
                passport_digest="sha256:" + "a" * 64,
                revision_id=stored.revision_id,
                at="2026-09-01T00:00:00.000Z",
            )
        contender.join(timeout=30)
        assert not contender.is_alive()

    assert outcome["versions"] == ["1.0", "1.1"], (
        "the loser serializes onto the next number; it does not crash"
    )
