"""The exact dependency closure of a composition (`#165`, `SPEC-006` REQ-605).

One question, answered from stored bytes: which exact versions are needed for a
composition to be complete, and why there is no answer when there is none. It
builds nothing and writes nothing — `harness-bundle.md` owns the package and
`ADR-0028` keeps this side deterministic.

**Every reference is exact or refused.** A dependency without a version or
without a digest is floating, and two machines resolving it at different moments
would compose different things from one input. That is REQ-607 lost at the first
step, so floating references are rejected before anything else is looked at.

**Missing and mismatched are different answers.** An absent version means fetch
it; a version whose digest disagrees means the object is *not the one the
reference names* — a substitution or a reissued number. One code for both would
hide the second behind the first, and the second is the dangerous one.

**A version conflict is not resolved by preferring the newer.** `REQ-626`
forbids automatic resolution of a semantic conflict, and choosing a version on
the user's behalf is exactly that. The closure blocks and a person decides.

**A closure that hit a bound is refused, not truncated.** A short answer that
looks complete is the worst failure available here: everything downstream would
build, install and verify a composition that is missing a dependency.
"""

import sqlite3
from dataclasses import dataclass
from typing import Final, cast

from ai_stp_cli.local import lifecycle, revisions, versions
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import is_digest
from ai_stp_foundation.versioning import VersionError, parse_version

#: Every refusal this resolver can produce, closed by `setup-graph.md`. A code
#: invented in passing is a reason no test names and no caller can branch on.
REFUSALS: Final[frozenset[str]] = frozenset(
    {
        "reference_floating",
        "dependency_missing",
        "digest_mismatch",
        "version_conflict",
        "dependency_cycle",
        "dependency_not_registrable",
        "dependency_unreadable",
        "closure_too_deep",
        "closure_too_large",
    }
)

#: Resource bounds (`SPEC-006`: "ограничения ресурсов сдерживают размер графа").
#: Declared rather than implicit, and returned in the answer, so a closure that
#: reached one is distinguishable from a complete one.
MAX_DEPTH: Final[int] = 32
MAX_NODES: Final[int] = 512

#: The fact a version passport carries its exact dependencies in. Read by name
#: because the local registry stores passports as envelopes of facts, and a
#: component adopted from a native file simply has no such fact.
REQUIRES_FACT: Final[str] = "requires_components"


@dataclass(frozen=True)
class Reference:
    """One exact edge: who requires what, and at which content."""

    stable_id: str
    version: str
    passport_digest: str

    #: Which node stated this requirement. Empty for a root, so a refusal can
    #: name the path a bad reference arrived by rather than only the reference.
    required_by: str = ""

    @property
    def exact(self) -> bool:
        """Whether this names one version of one object at one content.

        All three, not any of them. A digest without a version cannot be looked
        up and a version without a digest cannot be verified, and either alone
        would let the resolver proceed on half a statement.
        """
        if not self.stable_id or not is_digest(self.passport_digest):
            return False
        try:
            parse_version(self.version)
        except VersionError:
            return False
        return True


@dataclass(frozen=True)
class Node:
    """One exact version inside the closure."""

    stable_id: str
    version: str
    passport_digest: str
    revision_id: str
    requires: tuple[Reference, ...]

    #: Shortest distance from a root. Descriptive: the order below is
    #: topological, and depth would order two independent chains arbitrarily.
    depth: int


@dataclass(frozen=True)
class Refusal:
    """One reason a closure could not be resolved."""

    code: str
    summary: str
    details: dict[str, str]


@dataclass(frozen=True)
class Closure:
    """The whole answer: either every node, or every reason there is none."""

    nodes: tuple[Node, ...]
    refusals: tuple[Refusal, ...]
    max_depth: int = MAX_DEPTH
    max_nodes: int = MAX_NODES

    @property
    def resolved(self) -> bool:
        return not self.refusals

    @property
    def order(self) -> tuple[str, ...]:
        """Install order: a dependency before whatever requires it."""
        return tuple(f"{item.stable_id}@{item.version}" for item in self.nodes)


def resolve(connection: sqlite3.Connection, roots: tuple[Reference, ...]) -> Closure:
    """Walk the exact closure of `roots`, or explain why it cannot be walked.

    Breadth-first from roots sorted by identifier, so the depth recorded on a
    node is genuinely the shortest one and two runs over one input visit the
    same nodes in the same order.

    Every refusal is collected rather than the first one raised: a composition
    with three missing dependencies should be fixable in one pass, not three.
    """
    refusals: list[Refusal] = []
    found: dict[str, Node] = {}
    # What each object was first required at. A second requirement for a
    # different version of the same object is the conflict REQ-626 blocks on.
    pinned: dict[str, Reference] = {}

    frontier = [(item, 0) for item in sorted(roots, key=_by_reference)]
    while frontier:
        reference, depth = frontier.pop(0)

        if not reference.exact:
            refusals.append(
                _refuse(
                    "reference_floating",
                    "a dependency does not name an exact version and digest",
                    reference,
                    {"version": reference.version or "none"},
                )
            )
            continue

        held = pinned.get(reference.stable_id)
        if held is not None:
            if (held.version, held.passport_digest) != (
                reference.version,
                reference.passport_digest,
            ):
                refusals.append(
                    _refuse(
                        "version_conflict",
                        "two paths require different versions of one object",
                        reference,
                        {"already": held.version, "also": reference.version},
                    )
                )
            # Either it agrees and is already expanded, or it conflicts and the
            # refusal above stands. Expanding twice would double the work and
            # could not change the answer.
            continue
        pinned[reference.stable_id] = reference

        if depth > MAX_DEPTH:
            refusals.append(
                _refuse(
                    "closure_too_deep",
                    "this dependency chain is longer than the declared bound",
                    reference,
                    {"depth": str(depth), "limit": str(MAX_DEPTH)},
                )
            )
            continue
        if len(found) >= MAX_NODES:
            refusals.append(
                _refuse(
                    "closure_too_large",
                    "this closure holds more objects than the declared bound",
                    reference,
                    {"limit": str(MAX_NODES)},
                )
            )
            continue

        node = _node(connection, reference, depth, refusals)
        if node is None:
            continue
        found[reference.stable_id] = node
        frontier.extend((item, depth + 1) for item in sorted(node.requires, key=_by_reference))

    ordered, cycle = _ordered(found)
    if cycle:
        refusals.append(
            Refusal(
                "dependency_cycle",
                "these objects require each other in a cycle",
                {"members": ", ".join(cycle)},
            )
        )

    # Refusals sort by code then by object, so one input produces one answer
    # regardless of the order the walk happened to meet them.
    refusals.sort(key=lambda item: (item.code, item.details.get("stable_id", "")))
    # `REQ-608`: an unresolved closure is not a partial one. Returning the nodes
    # that did resolve would read as "almost composed", and a composition
    # missing a dependency is not composed at all.
    return Closure(nodes=() if refusals else ordered, refusals=tuple(refusals))


def _node(
    connection: sqlite3.Connection,
    reference: Reference,
    depth: int,
    refusals: list[Refusal],
) -> Node | None:
    """One node, or a refusal appended and nothing returned."""
    recorded = versions.held(connection, reference.stable_id, reference.version)
    if recorded is None:
        refusals.append(
            _refuse(
                "dependency_missing",
                "this machine does not hold that exact version",
                reference,
                {"version": reference.version},
            )
        )
        return None
    if recorded.passport_digest != reference.passport_digest:
        # Not "missing": the object is here and is *not the one named*. That is
        # a substitution or a reissued number, and it deserves its own code.
        refusals.append(
            _refuse(
                "digest_mismatch",
                "the held version stands for different content than the reference names",
                reference,
                {"expected": reference.passport_digest, "held": recorded.passport_digest},
            )
        )
        return None

    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        refusals.append(
            _refuse(
                "dependency_unreadable",
                "the revision behind that version cannot be read",
                reference,
                {"revision_id": recorded.revision_id},
            )
        )
        return None
    if not lifecycle.registrable(connection, stored):
        refusals.append(
            _refuse(
                "dependency_not_registrable",
                "a draft or deleted object is required by this composition",
                reference,
                {"version": reference.version},
            )
        )
        return None

    document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
    return Node(
        stable_id=reference.stable_id,
        version=reference.version,
        passport_digest=reference.passport_digest,
        revision_id=recorded.revision_id,
        requires=_declared(document, reference.stable_id),
        depth=depth,
    )


def _declared(document: dict[str, JsonValue], parent: str) -> tuple[Reference, ...]:
    """The exact dependencies a passport declares, as references.

    A component adopted from a native file declares none, and that is a complete
    answer rather than a missing field: nothing about a `settings.json` states a
    dependency, so inventing one would be worse than reading none.
    """
    value = document.get("requires_components")
    if value is None:
        facts = document.get("facts")
        if not isinstance(facts, dict):
            return ()
        fact = cast(dict[str, JsonValue], facts).get(REQUIRES_FACT)
        value = fact.get("value") if isinstance(fact, dict) else fact
    if not isinstance(value, list):
        return ()

    declared: list[Reference] = []
    for item in cast(list[JsonValue], value):
        if not isinstance(item, dict):
            # Kept rather than skipped: an unreadable entry is a floating
            # reference, and silently dropping it would compose without it.
            declared.append(Reference("", "", "", required_by=parent))
            continue
        held = cast(dict[str, JsonValue], item)
        declared.append(
            Reference(
                stable_id=str(held.get("stable_id", "")),
                version=str(held.get("version", "")),
                passport_digest=str(held.get("passport_digest", "")),
                required_by=parent,
            )
        )
    return tuple(declared)


def _ordered(found: dict[str, Node]) -> tuple[tuple[Node, ...], tuple[str, ...]]:
    """Topological order, and whatever a cycle left behind.

    Kahn's algorithm over a ready set kept sorted, so the order is total: two
    nodes that could go in either order always go in the same one. Anything
    still holding an edge when the queue empties is in a cycle.
    """
    # Only edges inside the closure count. A reference that failed to resolve is
    # already a refusal, and treating it as an edge would report a cycle on top.
    outgoing = {
        name: {item.stable_id for item in node.requires if item.stable_id in found}
        for name, node in found.items()
    }
    ordered: list[Node] = []
    remaining = dict(outgoing)

    while remaining:
        ready = sorted(name for name, needs in remaining.items() if not needs)
        if not ready:
            return tuple(ordered), tuple(sorted(remaining))
        for name in ready:
            ordered.append(found[name])
            del remaining[name]
        for needs in remaining.values():
            needs.difference_update(ready)

    return tuple(ordered), ()


def _refuse(code: str, summary: str, reference: Reference, details: dict[str, str]) -> Refusal:
    """Build a refusal, refusing a code the contract never declared."""
    if code not in REFUSALS:  # pragma: no cover - guarded by the registry test
        raise KeyError(code)
    named = {"stable_id": reference.stable_id or "unnamed", **details}
    if reference.required_by:
        named["required_by"] = reference.required_by
    return Refusal(code, summary, named)


def _by_reference(reference: Reference) -> tuple[str, str]:
    """A total order over references. The version last so nothing ever ties."""
    return reference.stable_id, reference.version
