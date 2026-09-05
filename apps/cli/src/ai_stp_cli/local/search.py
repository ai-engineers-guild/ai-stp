"""Local structured search and the three trust lanes (`#161`, `ADR-0016`).

No vectors and no model. `SPEC-011` REQ-1118 makes that an invariant of the whole
CLI, and it is also what makes this answerable offline and identically twice: a
prefix, a phrase, a tag and a field are all decidable from stored bytes, and
none of them needs an embedding or a service.

**The lanes are separate and one never becomes another.** `authoritative` needs
a confirmed author *and* a confirmed version — `ADR-0016` keeps those two axes
independent and a lane that accepted either alone would silently promote.
`experimental` reaches the answer only with consent, in its own section.
`local_owner_or_pinned` is the user's own or exactly pinned: installable after
local checks, never displayed as platform-confirmed. Nothing here can move a
candidate between lanes, which is why `lane_of` takes facts and returns a name
rather than taking a name and adjusting it.

**Order is total and stable.** REQ-607 wants one canonical input to produce one
order. Every comparison ends in the stable identifier, so two candidates that
tie on everything else still sort the same way on every machine and on every
run — a sort that leaves ties unresolved is a sort that changes with the
insertion order of a dictionary.
"""

import sqlite3
import unicodedata
from dataclasses import dataclass
from typing import Final, Protocol

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import consent, lifecycle, revisions
from ai_stp_foundation.canonical import JsonValue

#: The three lanes of `ADR-0016`. Closed: a fourth would be a trust level nobody
#: decided, and "unknown" is not a lane — it is a reason to be in none.
LANE_AUTHORITATIVE: Final[str] = "authoritative"
LANE_EXPERIMENTAL: Final[str] = "experimental"
LANE_LOCAL: Final[str] = "local_owner_or_pinned"
LANES: Final[tuple[str, ...]] = (LANE_AUTHORITATIVE, LANE_LOCAL, LANE_EXPERIMENTAL)

#: Facts a candidate is searched and filtered by. Closed, because a filter over
#: an open set of names is a filter whose behaviour depends on what somebody
#: happened to write into a passport.
QUERYABLE_FIELDS: Final[frozenset[str]] = frozenset(
    {"name", "description", "component_type", "harness_id", "scope", "tags"}
)

#: The most a single search may return. A bound rather than a page: local search
#: answers from one file and a caller that wants more can narrow the query.
MAX_RESULTS: Final[int] = 200

#: The longest query text accepted. A phrase longer than this is not a phrase.
MAX_QUERY_LENGTH: Final[int] = 512


class TrustAxes(Protocol):
    """The four independent facts a lane is decided from (`ADR-0016`).

    Structural rather than a base class, because more than one caller needs the
    lane and none of them owns the others: the mechanical constraint engine
    assembles a different object from the same four axes, and a second copy of
    the lane rule is precisely the silent promotion `ADR-0016` exists to stop.
    """

    @property
    def author_verified(self) -> bool: ...
    @property
    def component_verified(self) -> bool: ...
    @property
    def checks_current(self) -> bool: ...
    @property
    def owned_or_pinned(self) -> bool: ...


@dataclass(frozen=True)
class Candidate:
    """One local object as search sees it."""

    stable_id: str
    revision_id: str
    fields: dict[str, JsonValue]

    #: Who published it, and which exact version this is. Both are here because
    #: the durable consent records are keyed by them — a `publisher` record by
    #: the owner, an `object_major` record by the object and its major line.
    #: They used to be absent, and the publisher arrived instead through a
    #: `publisher_of` mapping that `search` accepted and no caller ever passed;
    #: the lookup therefore always missed and every durable record was inert.
    #: A fact the candidate owns cannot be forgotten by a caller.
    owner_id: str = ""
    version: str = ""

    #: Independent axes (`ADR-0016`): a confirmed author does not confirm a
    #: version and a confirmed version does not confirm an author. Kept apart
    #: here because `authoritative` needs both and a single flag would let one
    #: stand in for the other.
    author_verified: bool = False
    component_verified: bool = False

    #: Whether the local owner owns this, or pinned it exactly.
    owned_or_pinned: bool = False

    #: Whether every mandatory check is current and compatibility evidence
    #: exists for the target (`REQ-602`).
    checks_current: bool = False


@dataclass(frozen=True)
class Hit:
    """One candidate that matched, and the lane it is in."""

    stable_id: str
    revision_id: str
    lane: str
    reason: str
    fields: dict[str, JsonValue]


@dataclass(frozen=True)
class Results:
    """What a search found, with each lane kept in its own section.

    Separate lists rather than one list with a label: `REQ-603` requires the
    unverified section to be *separate*, and a caller that renders a flat list
    of labelled rows has already lost that distinction.
    """

    authoritative: tuple[Hit, ...]
    local: tuple[Hit, ...]
    experimental: tuple[Hit, ...]

    #: Why the experimental section is empty when it is: no consent, or no
    #: matches. Those are different situations and a bare empty list confuses
    #: them.
    experimental_reason: str
    truncated: bool


def normalise(text: str) -> str:
    """Fold text for comparison: NFC, casefolded, whitespace collapsed.

    NFC because the canonical form is what the rest of the system stores, and
    two spellings of one accented word must not be two different search terms.
    Casefold rather than lower: it is the one that handles the cases lowering
    quietly gets wrong.
    """
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def matches(
    candidate: Candidate,
    *,
    prefix: str = "",
    phrase: str = "",
    tags: tuple[str, ...] = (),
    field: str = "",
    value: str = "",
) -> bool:
    """Whether one candidate satisfies every filter given (`REQ-1118`: no model).

    Filters combine with AND, which is the only combination that lets a caller
    narrow a result set predictably. An empty filter is not a filter and matches
    everything rather than nothing.
    """
    name = normalise(str(candidate.fields.get("name", "")))
    if prefix and not name.startswith(normalise(prefix)):
        return False
    if phrase:
        haystack = normalise(
            " ".join(str(candidate.fields.get(key, "")) for key in ("name", "description"))
        )
        if normalise(phrase) not in haystack:
            return False
    if tags:
        held = {normalise(str(item)) for item in _as_list(candidate.fields.get("tags"))}
        # Every requested tag, not any: asking for two tags and getting objects
        # with one of them is a filter that widens as you add to it.
        if not {normalise(item) for item in tags} <= held:
            return False
    if field:
        if field not in QUERYABLE_FIELDS:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a structured filter must name one of the declared fields",
                details={"field": field, "allowed": ", ".join(sorted(QUERYABLE_FIELDS))},
            )
        if normalise(str(candidate.fields.get(field, ""))) != normalise(value):
            return False
    return True


def validate_query(*, prefix: str, phrase: str, field: str, value: str) -> None:
    """Validate a query even when there are no candidates to iterate over."""
    _bounded(prefix, phrase, value)
    if field and field not in QUERYABLE_FIELDS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a structured filter must name one of the declared fields",
            details={"field": field, "allowed": ", ".join(sorted(QUERYABLE_FIELDS))},
        )


def lane_of(candidate: TrustAxes) -> tuple[str, str]:
    """Which lane a candidate is in, and why. Takes facts, returns a name.

    Order matters and it is not arbitrary. Ownership is checked first because
    `local_owner_or_pinned` is about who the object belongs to, not how good it
    is: an object of the user's own does not need a platform confirmation to be
    installable, and putting it in `experimental` would ask them for consent to
    use their own work.

    Then `authoritative`, which needs **both** axes and current checks. A silent
    promotion is the failure `ADR-0016` names, so every condition is required
    and none of them substitutes for another.
    """
    if candidate.owned_or_pinned:
        return LANE_LOCAL, "your own or exactly pinned; installable after local checks"
    if candidate.author_verified and candidate.component_verified and candidate.checks_current:
        return LANE_AUTHORITATIVE, "confirmed author and confirmed version, checks current"

    missing: list[str] = []
    if not candidate.author_verified:
        missing.append("the author is not confirmed")
    if not candidate.component_verified:
        missing.append("this version is not confirmed")
    if not candidate.checks_current:
        missing.append("mandatory checks are not current")
    return LANE_EXPERIMENTAL, "; ".join(missing)


def search(
    connection: sqlite3.Connection,
    candidates: tuple[Candidate, ...],
    *,
    prefix: str = "",
    phrase: str = "",
    tags: tuple[str, ...] = (),
    field: str = "",
    value: str = "",
    include_unverified: bool = False,
) -> Results:
    """Filter, sort and lane every candidate. Offline, deterministic, bounded.

    `include_unverified` is the request flag of `ADR-0016` — per command, never
    stored. A durable consent record can also cover a candidate, and either is
    enough; what does not exist is a config key that allows everything
    unverified forever. Scope `task` is a named, revocable profile, not that
    key.
    """
    validate_query(prefix=prefix, phrase=phrase, field=field, value=value)
    laned: dict[str, list[Hit]] = {lane: [] for lane in LANES}
    truncated = False

    for candidate in candidates:
        stored = revisions.get(connection, candidate.revision_id)
        # A draft is not finished and a tombstoned object is deleted. `REQ-509`
        # keeps the first out of search; `SPEC-013` REQ-1308 the second.
        if stored is None or not lifecycle.registrable(connection, stored):
            continue
        if not matches(
            candidate, prefix=prefix, phrase=phrase, tags=tags, field=field, value=value
        ):
            continue

        lane, reason = lane_of(candidate)
        if lane == LANE_EXPERIMENTAL:
            allowed, why = _consented(connection, candidate, include_unverified=include_unverified)
            if not allowed:
                continue
            reason = f"{reason}; {why}"
        laned[lane].append(
            Hit(candidate.stable_id, candidate.revision_id, lane, reason, candidate.fields)
        )

    for lane in LANES:
        laned[lane].sort(key=_ordering)
        if len(laned[lane]) > MAX_RESULTS:
            laned[lane] = laned[lane][:MAX_RESULTS]
            truncated = True

    return Results(
        authoritative=tuple(laned[LANE_AUTHORITATIVE]),
        local=tuple(laned[LANE_LOCAL]),
        experimental=tuple(laned[LANE_EXPERIMENTAL]),
        experimental_reason=(
            "matched and consented"
            if laned[LANE_EXPERIMENTAL]
            else "no consent was given for any unverified candidate"
            if not include_unverified
            else "no unverified candidate matched"
        ),
        truncated=truncated,
    )


def _consented(
    connection: sqlite3.Connection,
    candidate: Candidate,
    *,
    include_unverified: bool,
) -> tuple[bool, str]:
    """Whether an unverified candidate may be shown, and on what basis.

    The request flag and a durable record are both valid, and the record is
    checked even when the flag is set — a record that no longer covers the
    candidate is a revoking event the user must be told about, and a flag does
    not answer that question.
    """
    found = consent.consulted(
        connection,
        stable_id=candidate.stable_id,
        owner_id=candidate.owner_id,
        version=candidate.version,
        capabilities=candidate.fields,
    )
    if found.covered:
        return True, f"shown by a durable consent ({found.source}): {found.reason}"
    if found.source:
        # A record that stopped covering is not silently ignored: the contract
        # requires the exact cause, and a request flag must not paper over it.
        return False, found.reason
    if include_unverified:
        return True, "shown by the request flag, for this command only"
    return False, found.reason


def _ordering(hit: Hit) -> tuple[str, str]:
    """A total order. The identifier last so nothing ever ties."""
    return normalise(str(hit.fields.get("name", ""))), hit.stable_id


def _bounded(*texts: str) -> None:
    for text in texts:
        if len(text) > MAX_QUERY_LENGTH:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "the query is longer than a query may be",
                details={"length": str(len(text)), "limit": str(MAX_QUERY_LENGTH)},
            )


def _as_list(value: JsonValue) -> list[JsonValue]:
    return value if isinstance(value, list) else []
