"""The exact closure: deterministic, or refused with a reason for each cause."""

import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.local import cache, graph, lifecycle, revisions, versions
from ai_stp_cli.local.database import configured_path, open_registry

CONTRACT = Path("docs/contracts/setup-graph.md")
AT = "2026-08-08T10:00:00.000Z"
OWNER = "account_01J0000000000000000000000A"
DEVICE = "device_test"

#: Crockford base32 excludes I, L, O and U, so the suffixes here stay inside
#: what a ULID may hold. A test id that is not a valid id fails validation long
#: before it reaches the thing under test.
NAMES = "ABCDEFGHJKMNPQRSTVWXYZ23456789"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def _id(suffix: str) -> str:
    """A valid component id ending in `suffix`, whatever its length.

    A ULID is exactly twenty-six characters, so the padding shrinks as the
    suffix grows. Building the string by concatenation instead would produce a
    twenty-seven character id for a two-letter name, and the failure would
    surface as a passport validation error far from the test that caused it.
    """
    body = "01J" + "0" * 23
    return f"component_{body[: 26 - len(suffix)]}{suffix}"


def _release(
    connection: sqlite3.Connection,
    suffix: str,
    *,
    version: str = "1.0",
    requires: tuple[tuple[str, str, str], ...] = (),
    state: str | None = None,
) -> tuple[str, str]:
    """One released version, optionally declaring exact dependencies."""
    stable_id = _id(suffix)
    connection.execute(
        "INSERT OR IGNORE INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, AT),
    )
    document: dict[str, object] = {
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
            },
            "requires_components": {
                "value": [
                    {"stable_id": item, "version": number, "passport_digest": digest}
                    for item, number, digest in requires
                ],
                "origin": "declared",
                "confirmation": "none",
                "observed_at": AT,
            },
        },
    }
    if state is not None:
        document["lifecycle_state"] = state
    stored = revisions.commit(connection, document, device_id=DEVICE)  # pyright: ignore[reportArgumentType]
    digest = cache.digest_of(stored.envelope.model_dump(mode="json"))
    versions.record(
        connection,
        stable_id=stable_id,
        version=version,
        passport_digest=digest,
        revision_id=stored.revision_id,
        at=AT,
    )
    return stable_id, digest


def _root(pair: tuple[str, str], *, version: str = "1.0") -> graph.Reference:
    return graph.Reference(stable_id=pair[0], version=version, passport_digest=pair[1])


def _codes(closure: graph.Closure) -> tuple[str, ...]:
    return tuple(item.code for item in closure.refusals)


def test_a_lone_object_with_no_dependencies_resolves(registry: sqlite3.Connection) -> None:
    only = _release(registry, "A")
    closure = graph.resolve(registry, (_root(only),))
    assert closure.resolved
    assert [item.stable_id for item in closure.nodes] == [only[0]]
    assert closure.nodes[0].depth == 0


def test_a_dependency_comes_before_whatever_requires_it(registry: sqlite3.Connection) -> None:
    leaf = _release(registry, "B")
    middle = _release(registry, "C", requires=((leaf[0], "1.0", leaf[1]),))
    top = _release(registry, "D", requires=((middle[0], "1.0", middle[1]),))

    closure = graph.resolve(registry, (_root(top),))
    assert closure.resolved
    assert closure.order == (f"{leaf[0]}@1.0", f"{middle[0]}@1.0", f"{top[0]}@1.0")
    assert [item.depth for item in closure.nodes] == [2, 1, 0]


def test_a_shared_dependency_appears_once(registry: sqlite3.Connection) -> None:
    shared = _release(registry, "E")
    left = _release(registry, "F", requires=((shared[0], "1.0", shared[1]),))
    right = _release(registry, "G", requires=((shared[0], "1.0", shared[1]),))

    closure = graph.resolve(registry, (_root(left), _root(right)))
    assert closure.resolved
    assert [item.stable_id for item in closure.nodes].count(shared[0]) == 1
    assert closure.order[0] == f"{shared[0]}@1.0"


# REQ-607: one canonical input, one answer — including when the caller shuffles
# the roots.
def test_the_order_does_not_depend_on_how_the_roots_were_listed(
    registry: sqlite3.Connection,
) -> None:
    first = _release(registry, "H")
    second = _release(registry, "J")
    third = _release(registry, "K")
    roots = (_root(first), _root(second), _root(third))

    forward = graph.resolve(registry, roots)
    backward = graph.resolve(registry, tuple(reversed(roots)))
    assert forward.order == backward.order
    assert forward.nodes == backward.nodes


def test_resolving_twice_gives_the_same_closure(registry: sqlite3.Connection) -> None:
    leaf = _release(registry, "M")
    top = _release(registry, "N", requires=((leaf[0], "1.0", leaf[1]),))
    assert graph.resolve(registry, (_root(top),)) == graph.resolve(registry, (_root(top),))


# Floating references: the whole determinism guarantee starts here.
@pytest.mark.parametrize(
    "reference",
    [
        graph.Reference("component_x", "", "sha256:" + "a" * 64),
        graph.Reference("component_x", "1.0", ""),
        graph.Reference("component_x", "^1.0", "sha256:" + "a" * 64),
        graph.Reference("component_x", "latest", "sha256:" + "a" * 64),
        graph.Reference("", "1.0", "sha256:" + "a" * 64),
        graph.Reference("component_x", "1.0", "not-a-digest"),
    ],
)
def test_a_reference_that_is_not_exact_is_refused(
    registry: sqlite3.Connection, reference: graph.Reference
) -> None:
    closure = graph.resolve(registry, (reference,))
    assert _codes(closure) == ("reference_floating",)
    assert not closure.resolved


def test_a_floating_dependency_inside_a_passport_is_refused(
    registry: sqlite3.Connection,
) -> None:
    """A bad edge deep in the graph is as fatal as a bad root."""
    top = _release(registry, "P", requires=((_id("Q"), "", "sha256:" + "b" * 64),))
    assert "reference_floating" in _codes(graph.resolve(registry, (_root(top),)))


def test_an_unreadable_dependency_entry_is_floating_rather_than_dropped(
    registry: sqlite3.Connection,
) -> None:
    """Silently skipping it would compose without a dependency somebody declared."""
    stable_id = _id("R")
    registry.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, AT),
    )
    stored = revisions.commit(
        registry,
        {  # pyright: ignore[reportArgumentType]
            "schema_version": 1,
            "kind": "component",
            "stable_id": stable_id,
            "owner_id": OWNER,
            "created_at": AT,
            "visibility": "private",
            "parent_revision_ids": [],
            "facts": {
                "requires_components": {
                    "value": ["not an object at all"],
                    "origin": "declared",
                    "confirmation": "none",
                    "observed_at": AT,
                }
            },
        },
        device_id=DEVICE,
    )
    digest = cache.digest_of(stored.envelope.model_dump(mode="json"))
    versions.record(
        registry,
        stable_id=stable_id,
        version="1.0",
        passport_digest=digest,
        revision_id=stored.revision_id,
        at=AT,
    )
    assert "reference_floating" in _codes(graph.resolve(registry, (_root((stable_id, digest)),)))


# Missing and mismatched are different situations with different fixes.
def test_a_dependency_this_machine_does_not_hold_is_missing(
    registry: sqlite3.Connection,
) -> None:
    closure = graph.resolve(registry, (graph.Reference(_id("S"), "1.0", "sha256:" + "c" * 64),))
    assert _codes(closure) == ("dependency_missing",)


def test_a_held_version_at_different_content_is_a_mismatch_not_a_miss(
    registry: sqlite3.Connection,
) -> None:
    held = _release(registry, "T")
    closure = graph.resolve(registry, (graph.Reference(held[0], "1.0", "sha256:" + "d" * 64),))
    assert _codes(closure) == ("digest_mismatch",)
    assert closure.refusals[0].details["held"] == held[1]


def test_a_missing_dependency_names_who_required_it(registry: sqlite3.Connection) -> None:
    top = _release(registry, "V", requires=((_id("W"), "1.0", "sha256:" + "e" * 64),))
    closure = graph.resolve(registry, (_root(top),))
    assert closure.refusals[0].details["required_by"] == top[0]


# REQ-626: a version conflict blocks; nothing chooses on the user's behalf.
def test_two_paths_requiring_different_versions_is_a_conflict(
    registry: sqlite3.Connection,
) -> None:
    first = _release(registry, "X", version="1.0")
    second = _release(registry, "X", version="2.0")
    left = _release(registry, "Y", requires=((first[0], "1.0", first[1]),))
    right = _release(registry, "Z", requires=((second[0], "2.0", second[1]),))

    closure = graph.resolve(registry, (_root(left), _root(right)))
    assert "version_conflict" in _codes(closure)
    assert not closure.resolved
    assert closure.nodes == (), "nothing is composed while a conflict stands"


def test_the_same_version_required_twice_is_not_a_conflict(
    registry: sqlite3.Connection,
) -> None:
    shared = _release(registry, "2")
    left = _release(registry, "3", requires=((shared[0], "1.0", shared[1]),))
    right = _release(registry, "4", requires=((shared[0], "1.0", shared[1]),))
    assert graph.resolve(registry, (_root(left), _root(right))).resolved


def test_a_cycle_is_named_rather_than_looped_over(registry: sqlite3.Connection) -> None:
    """Two objects requiring each other: the walk must end and say so."""
    first = _release(registry, "5")
    second = _release(registry, "6", requires=((first[0], "1.0", first[1]),))
    # Re-release the first so it now requires the second, closing the loop. The
    # digest changes with the content, so the root reference is taken afresh.
    reopened = _release(registry, "5", version="2.0", requires=((second[0], "1.0", second[1]),))

    closure = graph.resolve(registry, (_root(reopened, version="2.0"),))
    assert "dependency_cycle" in _codes(closure)
    assert closure.nodes == ()


def test_a_draft_or_deleted_dependency_blocks_the_closure(
    registry: sqlite3.Connection,
) -> None:
    leaf = _release(registry, "7")
    top = _release(registry, "8", requires=((leaf[0], "1.0", leaf[1]),))
    lifecycle.entomb(registry, leaf[0], reason="removed by the owner", at=AT)

    closure = graph.resolve(registry, (_root(top),))
    assert "dependency_not_registrable" in _codes(closure)


def test_a_closure_deeper_than_the_bound_is_refused_not_truncated(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A short answer that looks complete is the worst failure available here."""
    monkeypatch.setattr(graph, "MAX_DEPTH", 1)
    leaf = _release(registry, "9")
    middle = _release(registry, "AA", requires=((leaf[0], "1.0", leaf[1]),))
    top = _release(registry, "AB", requires=((middle[0], "1.0", middle[1]),))

    closure = graph.resolve(registry, (_root(top),))
    assert "closure_too_deep" in _codes(closure)
    assert closure.nodes == ()


def test_a_closure_wider_than_the_bound_is_refused(
    registry: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(graph, "MAX_NODES", 2)
    roots = tuple(_root(_release(registry, name)) for name in ("AC", "AD", "AE"))
    closure = graph.resolve(registry, roots)
    assert "closure_too_large" in _codes(closure)
    assert closure.nodes == ()


# REQ-608: an unresolved closure is not a partial one.
def test_an_unresolved_closure_returns_no_nodes_at_all(registry: sqlite3.Connection) -> None:
    good = _release(registry, "AF")
    closure = graph.resolve(
        registry, (_root(good), graph.Reference(_id("AG"), "1.0", "sha256:" + "f" * 64))
    )
    assert not closure.resolved
    assert closure.nodes == ()
    assert closure.order == ()


def test_every_reason_comes_back_rather_than_only_the_first(
    registry: sqlite3.Connection,
) -> None:
    """Three broken dependencies should be fixable in one pass, not three."""
    closure = graph.resolve(
        registry,
        (
            graph.Reference(_id("AH"), "1.0", "sha256:" + "1" * 64),
            graph.Reference(_id("AJ"), "1.0", "sha256:" + "2" * 64),
            graph.Reference("component_x", "", ""),
        ),
    )
    assert len(closure.refusals) == 3


def test_the_refusal_order_is_stable(registry: sqlite3.Connection) -> None:
    roots = (
        graph.Reference(_id("AK"), "1.0", "sha256:" + "3" * 64),
        graph.Reference("component_y", "", ""),
        graph.Reference(_id("AM"), "1.0", "sha256:" + "4" * 64),
    )
    forward = graph.resolve(registry, roots)
    backward = graph.resolve(registry, tuple(reversed(roots)))
    assert _codes(forward) == _codes(backward)
    assert [item.details for item in forward.refusals] == [
        item.details for item in backward.refusals
    ]


def test_the_declared_bounds_come_back_in_the_answer(registry: sqlite3.Connection) -> None:
    closure = graph.resolve(registry, (_root(_release(registry, "AN")),))
    assert closure.max_depth == graph.MAX_DEPTH
    assert closure.max_nodes == graph.MAX_NODES


def test_an_empty_composition_resolves_to_nothing(registry: sqlite3.Connection) -> None:
    closure = graph.resolve(registry, ())
    assert closure.resolved
    assert closure.nodes == ()


# Documentation and code are two statements of one closed set.
def test_the_refusal_registry_matches_the_contract() -> None:
    written = set(re.findall(r"^\| `([a-z_]+)` \|", CONTRACT.read_text("utf-8"), re.MULTILINE))
    assert written == graph.REFUSALS


def test_the_declared_bounds_match_the_contract() -> None:
    text = CONTRACT.read_text("utf-8")
    assert f"максимальная глубина: {graph.MAX_DEPTH}" in text
    assert f"максимальное число узлов: {graph.MAX_NODES}" in text


def test_every_test_identifier_is_a_valid_stable_id() -> None:
    """The helper above builds ids by hand, so the alphabet is worth pinning."""
    from ai_stp_foundation.ids import is_valid_id

    assert all(is_valid_id(_id(name), "component") for name in NAMES)
