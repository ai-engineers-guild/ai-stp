"""Local search: the lanes stay apart, the order never varies, no model is called."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import consent, lifecycle, revisions, search
from ai_stp_cli.local.database import configured_path, open_registry

MOMENT = "2026-08-07T10:00:00.000Z"
OWNER = "account_01J0000000000000000000000A"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _register(
    connection: sqlite3.Connection,
    suffix: str,
    *,
    name: str,
    description: str = "",
    tags: tuple[str, ...] = (),
    state: str | None = None,
    **flags: bool,
) -> search.Candidate:
    stable_id = f"component_01J000000000000000000000{suffix}"
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, MOMENT),
    )
    document: dict[str, object] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": OWNER,
        "created_at": MOMENT,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": {
            "name": {
                "value": name,
                "origin": "observed",
                "confirmation": "none",
                "observed_at": MOMENT,
            }
        },
    }
    if state is not None:
        document["lifecycle_state"] = state
    stored = revisions.commit(connection, document, device_id="device_test")  # pyright: ignore[reportArgumentType]
    return search.Candidate(
        stable_id=stable_id,
        revision_id=stored.revision_id,
        fields={"name": name, "description": description, "tags": list(tags)},
        **flags,
    )


# --- lanes ----------------------------------------------------------------


def test_authoritative_needs_both_axes_and_current_checks() -> None:
    """`ADR-0016`: the two confirmation axes are independent.

    A confirmed author does not confirm a version and a confirmed version does
    not confirm an author, so neither may stand in for the other. A lane that
    accepted one alone would be the silent promotion the decision forbids.
    """
    complete = search.Candidate(
        "component_01J00000000000000000000010",
        "revision_" + "0" * 64,
        {"name": "a"},
        author_verified=True,
        component_verified=True,
        checks_current=True,
    )
    assert search.lane_of(complete)[0] == search.LANE_AUTHORITATIVE

    for missing in ("author_verified", "component_verified", "checks_current"):
        partial = search.Candidate(
            complete.stable_id,
            complete.revision_id,
            complete.fields,
            author_verified=missing != "author_verified",
            component_verified=missing != "component_verified",
            checks_current=missing != "checks_current",
        )
        lane, reason = search.lane_of(partial)
        assert lane == search.LANE_EXPERIMENTAL
        assert reason


def test_an_owned_object_is_local_and_never_asked_for_consent() -> None:
    own = search.Candidate(
        "component_01J00000000000000000000011",
        "revision_" + "0" * 64,
        {"name": "mine"},
        owned_or_pinned=True,
    )
    lane, reason = search.lane_of(own)
    # Ownership is about who it belongs to, not how good it is. Asking a user to
    # consent to their own work would train them to consent to everything.
    assert lane == search.LANE_LOCAL
    assert "your own" in reason

    # And it is still not platform-confirmed, whatever the flags say.
    also_verified = search.Candidate(
        own.stable_id,
        own.revision_id,
        own.fields,
        owned_or_pinned=True,
        author_verified=True,
        component_verified=True,
        checks_current=True,
    )
    assert search.lane_of(also_verified)[0] == search.LANE_LOCAL


def test_the_three_lanes_are_returned_in_separate_sections(
    registry: sqlite3.Connection,
) -> None:
    trusted = _register(
        registry,
        "20",
        name="trusted",
        author_verified=True,
        component_verified=True,
        checks_current=True,
    )
    mine = _register(registry, "21", name="mine", owned_or_pinned=True)
    unproven = _register(registry, "22", name="unproven")

    found = search.search(registry, (trusted, mine, unproven), include_unverified=True)
    # `REQ-603` wants a *separate* section. A flat list of labelled rows has
    # already lost the distinction it asks for.
    assert [hit.stable_id for hit in found.authoritative] == [trusted.stable_id]
    assert [hit.stable_id for hit in found.local] == [mine.stable_id]
    assert [hit.stable_id for hit in found.experimental] == [unproven.stable_id]


def test_an_unverified_candidate_is_absent_without_consent(
    registry: sqlite3.Connection,
) -> None:
    unproven = _register(registry, "23", name="unproven")

    without = search.search(registry, (unproven,))
    assert without.experimental == ()
    # An empty section with no explanation confuses "nothing matched" with
    # "nothing was allowed".
    assert "no consent" in without.experimental_reason

    with_flag = search.search(registry, (unproven,), include_unverified=True)
    assert len(with_flag.experimental) == 1
    assert "for this command only" in with_flag.experimental[0].reason


def test_a_durable_consent_shows_a_candidate_without_the_request_flag(
    registry: sqlite3.Connection,
) -> None:
    unproven = _register(registry, "24", name="unproven")
    consent.grant(
        registry,
        consent_id="request_01J00000000000000000000025",
        scope=consent.SCOPE_PUBLISHER,
        target="publisher/acme",
        fingerprint=consent.fingerprint_of({}),
        decided_by=OWNER,
        origin="registry search",
        at=MOMENT,
    )
    found = search.search(
        registry, (unproven,), publisher_of={unproven.stable_id: "publisher/acme"}
    )
    assert len(found.experimental) == 1
    assert "durable consent" in found.experimental[0].reason


def test_a_consent_that_stopped_covering_hides_the_candidate_even_with_the_flag(
    registry: sqlite3.Connection,
) -> None:
    """A revoking event is not papered over by a request flag.

    The contract requires the exact cause be shown, and a flag answers a
    different question than "does the old fingerprint still cover this".
    """
    grown = _register(registry, "26", name="grown")
    grown = search.Candidate(
        grown.stable_id,
        grown.revision_id,
        {**grown.fields, "network_permissions": ["collect.elsewhere.test"]},
    )
    consent.grant(
        registry,
        consent_id="request_01J00000000000000000000027",
        scope=consent.SCOPE_PUBLISHER,
        target="publisher/acme",
        fingerprint=consent.fingerprint_of({}),
        decided_by=OWNER,
        origin="registry search",
        at=MOMENT,
    )
    found = search.search(
        registry,
        (grown,),
        include_unverified=True,
        publisher_of={grown.stable_id: "publisher/acme"},
    )
    assert found.experimental == ()


# --- filters --------------------------------------------------------------


@pytest.fixture
def corpus(registry: sqlite3.Connection) -> tuple[search.Candidate, ...]:
    return (
        _register(
            registry,
            "30",
            name="review helper",
            description="reviews a diff carefully",
            tags=("review", "python"),
            owned_or_pinned=True,
        ),
        _register(
            registry,
            "31",
            name="reviewer",
            description="another one",
            tags=("review",),
            owned_or_pinned=True,
        ),
        _register(
            registry,
            "32",
            name="deployer",
            description="ships a build",
            tags=("deploy",),
            owned_or_pinned=True,
        ),
    )


def test_a_prefix_matches_the_start_of_a_name_and_nothing_else(
    registry: sqlite3.Connection, corpus: tuple[search.Candidate, ...]
) -> None:
    found = search.search(registry, corpus, prefix="review")
    assert [hit.fields["name"] for hit in found.local] == ["review helper", "reviewer"]
    # A prefix is a prefix: `eview` matches nothing, which is what makes it
    # different from a phrase.
    assert search.search(registry, corpus, prefix="eview").local == ()


def test_a_phrase_matches_inside_the_name_or_the_description(
    registry: sqlite3.Connection, corpus: tuple[search.Candidate, ...]
) -> None:
    assert len(search.search(registry, corpus, phrase="carefully").local) == 1
    assert len(search.search(registry, corpus, phrase="a diff").local) == 1
    assert search.search(registry, corpus, phrase="never written").local == ()


def test_tags_narrow_rather_than_widen(
    registry: sqlite3.Connection, corpus: tuple[search.Candidate, ...]
) -> None:
    assert len(search.search(registry, corpus, tags=("review",)).local) == 2
    # Two tags means both. Asking for more and getting more would make every
    # added tag loosen the query.
    assert len(search.search(registry, corpus, tags=("review", "python")).local) == 1
    assert search.search(registry, corpus, tags=("review", "absent")).local == ()


def test_a_structured_filter_names_a_declared_field(
    registry: sqlite3.Connection, corpus: tuple[search.Candidate, ...]
) -> None:
    assert len(search.search(registry, corpus, field="name", value="reviewer").local) == 1
    with pytest.raises(CliFailure, match="must name one of"):
        search.search(registry, corpus, field="owner_id", value=OWNER)
    with pytest.raises(CliFailure, match="must name one of"):
        search.search(registry, (), field="owner_id", value=OWNER)


def test_filters_combine_with_and(
    registry: sqlite3.Connection, corpus: tuple[search.Candidate, ...]
) -> None:
    both = search.search(registry, corpus, prefix="review", tags=("python",))
    assert [hit.fields["name"] for hit in both.local] == ["review helper"]
    # An empty filter is not a filter.
    assert len(search.search(registry, corpus).local) == 3


def test_matching_folds_case_and_unicode_form(
    registry: sqlite3.Connection,
) -> None:
    composed = _register(registry, "33", name="Café Runner", owned_or_pinned=True)
    decomposed_query = "café "

    # Two spellings of one accented word must not be two search terms, and
    # casefold handles what lowering quietly gets wrong.
    assert len(search.search(registry, (composed,), prefix="CAFÉ").local) == 1
    assert len(search.search(registry, (composed,), prefix=decomposed_query.strip()).local) == 1


# --- exclusions, order and bounds -----------------------------------------


def test_a_draft_and_a_tombstoned_object_never_appear(registry: sqlite3.Connection) -> None:
    drafted = _register(registry, "40", name="unfinished", state="draft", owned_or_pinned=True)
    deleted = _register(registry, "41", name="deleted", owned_or_pinned=True)
    kept = _register(registry, "42", name="kept", owned_or_pinned=True)
    lifecycle.entomb(registry, deleted.stable_id, reason="removed", at=MOMENT)

    found = search.search(registry, (drafted, deleted, kept))
    assert [hit.stable_id for hit in found.local] == [kept.stable_id]


def test_a_candidate_whose_revision_is_gone_is_skipped(registry: sqlite3.Connection) -> None:
    ghost = search.Candidate(
        "component_01J00000000000000000000043",
        "revision_" + "f" * 64,
        {"name": "ghost"},
        owned_or_pinned=True,
    )
    assert search.search(registry, (ghost,)).local == ()


def test_the_order_is_total_and_does_not_depend_on_input_order(
    registry: sqlite3.Connection,
) -> None:
    tied = tuple(
        _register(registry, f"5{n}", name="same name", owned_or_pinned=True) for n in range(4)
    )
    forward = search.search(registry, tied)
    backward = search.search(registry, tuple(reversed(tied)))
    # Every comparison ends in the identifier, so nothing ever ties and the
    # answer cannot depend on the order a caller happened to build the list in.
    assert [hit.stable_id for hit in forward.local] == [hit.stable_id for hit in backward.local]
    assert [hit.stable_id for hit in forward.local] == sorted(item.stable_id for item in tied)


def test_a_result_set_over_the_bound_is_cut_and_says_so(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(search, "MAX_RESULTS", 2)
    many = tuple(
        _register(registry, f"6{n}", name=f"object {n}", owned_or_pinned=True) for n in range(5)
    )
    found = search.search(registry, many)
    assert len(found.local) == 2
    # Silence here would read as "that is all there is".
    assert found.truncated is True


def test_a_query_longer_than_a_query_may_be_is_refused(registry: sqlite3.Connection) -> None:
    with pytest.raises(CliFailure, match="longer than a query"):
        search.search(registry, (), phrase="x" * (search.MAX_QUERY_LENGTH + 1))


# --- command --------------------------------------------------------------


def test_the_find_command_searches_what_was_adopted(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path

    from ai_stp_cli.commands import component as command

    assert isinstance(tmp_path, Path)
    home = tmp_path / "home"
    (home / ".claude" / "skills" / "reviewing").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("# instruction\n", encoding="utf-8")
    (home / ".claude" / "skills" / "reviewing" / "SKILL.md").write_text("# r\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    for path in (home / ".claude" / "CLAUDE.md", home / ".claude" / "skills" / "reviewing"):
        command.adopt({"path": str(path)})

    everything = command.find({}).payload
    # Everything local is `local_owner_or_pinned`: nothing here came from a
    # platform that could have confirmed it, and claiming another lane would be
    # inventing a confirmation.
    assert len(everything.local_owner_or_pinned) == 2
    assert everything.authoritative == []
    assert everything.experimental == []

    narrowed = command.find({"field": "component_type", "value": "skill"}).payload
    assert len(narrowed.local_owner_or_pinned) == 1
    assert narrowed.local_owner_or_pinned[0].fields["component_type"] == "skill"

    by_tag = command.find({"tag": ["absent"]}).payload
    assert by_tag.local_owner_or_pinned == []
    assert by_tag.experimental_reason


def test_the_find_command_accepts_one_tag_or_several(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path

    from ai_stp_cli.commands import component as command

    assert isinstance(tmp_path, Path)
    monkeypatch.setenv("HOME", str(tmp_path / "empty"))
    # A repeatable option arrives as a list from the parser and as a bare string
    # from a caller that passed one. Both mean the same thing.
    assert command.find({"tag": "review"}).payload.local_owner_or_pinned == []
    assert command.find({"tag": ["review", "python"]}).payload.local_owner_or_pinned == []


def test_the_find_command_skips_an_entity_with_no_revision(
    registry: sqlite3.Connection,
) -> None:
    from ai_stp_cli.commands import component as command

    registry.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        ("component_01J00000000000000000000070", MOMENT),
    )
    registry.commit()

    # A registered identifier with nothing written under it yet is not a
    # candidate. Reporting it would put a row in the answer with no facts in it.
    assert command.find({}).payload.local_owner_or_pinned == []
