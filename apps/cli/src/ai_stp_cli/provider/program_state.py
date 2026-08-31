"""What stands under a program prefix, read from disk rather than from a reply.

The subject of a program operation is the prefix, and until this module existed
nothing ever looked at it. `harness install` recorded `verified` because the
provider's answer carried the word, and `harness resume` recorded it because the
provider's *configuration target* reported an ordinary state — `missing` on an
empty directory settled a program operation about a directory nobody read.

Both are the same mistake with two faces: a provider result is testimony, and a
postcondition is evidence. This is the evidence half, and it is consumer-side on
purpose. The kit's seven commands describe the target and none of them describes
a prefix, so asking the provider would mean a new protocol command and a release
wave across seven systems — while the layout is already a stable machine-readable
contract that this process can read directly:

```text
<prefix>/<version>/            one immutable tree per installed build
<prefix>/bin/<exposed>         the command, exposing exactly one of them
<prefix>/bin/.<command>.version  which one, written by the side that exposed it
<prefix>/.incoming-<version>   staging, present only mid-install
<prefix>/.replaced-<version>   quarantine, present only mid-update
```

The two dotted forms are the reason an observation can say *recovery is owed*
rather than guessing: they exist only while an operation is between steps, so
finding one is finding an operation that did not finish.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

#: Where the provider records which version `bin/<command>` points into. Written
#: by the same code that does the exposing and deleted with the command it
#: described, so it cannot disagree with the disk the way a separate ledger can.
VERSION_MARKER: Final[str] = ".{command}.version"

#: Suffixes the exposed file may carry that the marker's name does not. The
#: provider exposes `<command>.cmd` for a JavaScript member on Windows while
#: still writing `.<command>.version`, so the marker is found from the stem
#: rather than from the file that is actually there.
#:
#: Only `.cmd` has a subject: cursor exposes `agent.cmd` on Windows because its
#: member is JavaScript. No harness exposes a `.exe` — codex ships `codex.exe`
#: as its member and exposes it as `codex`, because `CreateProcess` on an
#: explicit path reads the PE header rather than the name. `.exe` and `.bat`
#: are breadth, not coverage, and are named here so this set is not later read
#: as evidence that such an exposure exists.
EXPOSED_SUFFIXES: Final[frozenset[str]] = frozenset({".cmd", ".exe", ".bat"})

#: Prefixes of the two directories the provider uses between steps. Staging for
#: an arriving tree, quarantine for a displaced one; both are removed when the
#: operation completes, so either one surviving means it did not.
_UNFINISHED: Final[tuple[str, ...]] = (".incoming-", ".replaced-")

#: There is deliberately no digest of a reading. Staleness of a program plan is
#: the provider's to decide: it takes the prefix lock and refuses a plan that no
#: longer describes what it holds, which is a check on the same side of the lock
#: as the effect. A consumer-side digest compared before the call would be the
#: same question asked where the answer can still change, and settling needs to
#: know *which* builds arrived or left — which a digest cannot say.


def command_of(entry_point: str) -> str:
    """The command name behind a planned entry point.

    `entry_point` is relative to the prefix and is what the provider will
    expose, so `bin/codex` and `bin/agent.cmd` both name a command whose marker
    is written without the suffix.
    """
    name = PurePosixPath(entry_point).name
    stem = Path(name)
    return stem.stem if stem.suffix.casefold() in EXPOSED_SUFFIXES else name


@dataclass(frozen=True)
class PrefixState:
    """One reading of a prefix. A statement about now, never about intent."""

    #: Version trees present, sorted. Sorted rather than in directory order so
    #: two readings of an unchanged prefix compare equal.
    versions: tuple[str, ...]
    #: What the marker names, filtered to a version tree that exists. Empty
    #: means *unknown*, never *absent*: a prefix written before the marker
    #: existed reads the same as one nothing installed into.
    exposed: str
    #: Whether the planned entry point is on disk.
    entry_point_present: bool
    #: Staging and quarantine directories still standing, sorted. Non-empty
    #: means an operation stopped between steps.
    unfinished: tuple[str, ...]

    def serialize(self) -> str:
        """Canonical JSON, for the durable plan. Read back by `deserialize`."""
        return json.dumps(
            {
                "versions": list(self.versions),
                "exposed": self.exposed,
                "entry_point_present": self.entry_point_present,
                "unfinished": list(self.unfinished),
            },
            sort_keys=True,
            separators=(",", ":"),
        )


#: A reading that carries nothing. What a plan recorded before this module
#: existed deserializes to this, and every comparison against it is refused
#: rather than guessed — see `Settlement.UNREADABLE`.
EMPTY: Final[PrefixState] = PrefixState(
    versions=(), exposed="", entry_point_present=False, unfinished=()
)


def deserialize(raw: str) -> PrefixState | None:
    """Read a stored reading back, or `None` when there is not one.

    `None` and `EMPTY` are different answers. `None` is a plan recorded before
    prefix state was stored — nothing may be concluded from it, and the caller
    must refuse rather than treat an old operation as having started from an
    empty prefix.
    """
    if not raw:
        return None
    try:
        held = cast("object", json.loads(raw))
    except ValueError:
        return None
    if not isinstance(held, dict):
        return None
    fields = cast("dict[str, object]", held)
    versions = fields.get("versions")
    unfinished = fields.get("unfinished")
    exposed = fields.get("exposed")
    present = fields.get("entry_point_present")
    if not isinstance(versions, list) or not isinstance(unfinished, list):
        return None
    if not isinstance(exposed, str) or not isinstance(present, bool):
        return None
    return PrefixState(
        versions=tuple(str(item) for item in cast("list[object]", versions)),
        exposed=exposed,
        entry_point_present=present,
        unfinished=tuple(str(item) for item in cast("list[object]", unfinished)),
    )


def observe(prefix: Path, *, entry_point: str) -> PrefixState:
    """Read the prefix. Runs nothing and writes nothing.

    A prefix that does not exist reads as empty rather than raising: "nothing is
    installed there" is an answer, and it is the correct precondition for an
    install.

    The exposed version is believed only where the command it describes is
    actually there and where it names a version directory that exists. Both
    guards are taken from the provider's own reader rather than invented here: a
    hand-edited or half-written marker must not name a build that is not.
    """
    versions: list[str] = []
    unfinished: list[str] = []
    try:
        entries = sorted(prefix.iterdir())
    except OSError:
        return EMPTY
    for item in entries:
        if not item.is_dir():
            continue
        name = item.name
        if name.startswith(_UNFINISHED):
            unfinished.append(name)
        elif not name.startswith(".") and name != "bin":
            versions.append(name)

    command = command_of(entry_point)
    exposed_path = prefix / entry_point if entry_point else None
    present = exposed_path is not None and exposed_path.exists()

    marked = ""
    if command:
        marker = prefix / "bin" / VERSION_MARKER.format(command=command)
        try:
            held = marker.read_text(encoding="utf-8").strip()
        except OSError:
            held = ""
        if held and held in versions:
            marked = held

    return PrefixState(
        versions=tuple(sorted(versions)),
        exposed=marked,
        entry_point_present=present,
        unfinished=tuple(sorted(unfinished)),
    )


@dataclass(frozen=True)
class Settlement:
    """Whether an observation settles one program operation, and why.

    `met` is the only field a caller may branch on. `reason` is written for a
    person and for the journal, and `observed_version` is what the prefix
    actually shows — carried out so a caller records the disk's answer rather
    than the provider's.
    """

    met: bool
    reason: str
    observed_version: str = ""
    #: True when the prefix carries staging or quarantine the provider still
    #: owes cleanup for. Distinct from a plain `met=False`: this one has a
    #: named next action, `recover-operation`, and the other does not.
    recovery_owed: bool = False

    #: What a settlement cannot be built from. A plan recorded before prefix
    #: state existed has no reading to compare against, and inventing one would
    #: mean deciding that an old operation started from an empty prefix.
    UNREADABLE: Final[str] = (
        "this operation was planned before the prefix was read, so nothing here can "
        "settle it; plan it again against the prefix as it stands"
    )


def settles(
    before: PrefixState | None,
    after: PrefixState,
    *,
    operation: str,
    claimed_version: str = "",
) -> Settlement:
    """Whether the prefix now shows what this operation was supposed to do.

    `claimed_version` is the provider's own answer when there is one — at apply
    there is, at resume there is not. Given, it is *checked* rather than
    believed: the disk must agree with it, and a disagreement is the integrity
    failure this whole module exists to catch. Absent, the verdict rests on the
    difference between the two readings, which is weaker and still sound.

    `software_remove` is the one operation whose success is an absence, so it is
    the one where "the entry point is there" proves nothing on its own: removing
    a build that is merely present leaves the running command alone, and that is
    the point of being able to remove it.
    """
    if before is None:
        return Settlement(False, Settlement.UNREADABLE)
    if after.unfinished:
        return Settlement(
            False,
            f"the prefix carries {', '.join(after.unfinished)}, which the provider "
            "leaves only between steps, so this operation did not finish",
            observed_version=after.exposed,
            recovery_owed=True,
        )

    if operation == "software_remove":
        if claimed_version:
            if claimed_version in after.versions:
                return Settlement(
                    False,
                    f"{claimed_version} is still under the prefix, so the removal "
                    "the provider reported did not land",
                    observed_version=after.exposed,
                )
            return Settlement(
                True,
                f"{claimed_version} is gone from the prefix"
                + (f" and {after.exposed} still holds the exposure" if after.exposed else ""),
                observed_version=after.exposed,
            )
        gone = tuple(item for item in before.versions if item not in after.versions)
        if not gone:
            return Settlement(
                False,
                "no version left the prefix, so nothing here shows a removal landed",
                observed_version=after.exposed,
            )
        return Settlement(
            True,
            f"{', '.join(gone)} left the prefix",
            observed_version=after.exposed,
        )

    # install and update: a build has to be there, and the command has to point
    # into it. Either one alone is the false success this replaces — a tree with
    # nothing exposing it, or a command left over from a build that is gone.
    if not after.entry_point_present:
        return Settlement(
            False,
            "the planned entry point is not on disk, so nothing is exposed here",
            observed_version=after.exposed,
        )
    if claimed_version:
        if claimed_version not in after.versions:
            return Settlement(
                False,
                f"the provider reported {claimed_version} and no such tree is under the prefix",
                observed_version=after.exposed,
            )
        if after.exposed and after.exposed != claimed_version:
            return Settlement(
                False,
                f"the provider reported {claimed_version} and the prefix exposes {after.exposed}",
                observed_version=after.exposed,
            )
        return Settlement(
            True,
            f"{claimed_version} is under the prefix and holds the exposure",
            observed_version=claimed_version,
        )

    arrived = tuple(item for item in after.versions if item not in before.versions)
    if arrived:
        return Settlement(
            True,
            f"{', '.join(arrived)} arrived under the prefix and the entry point is exposed",
            observed_version=after.exposed or arrived[0],
        )
    if after.exposed and after.exposed != before.exposed:
        return Settlement(
            True,
            f"the exposure moved to {after.exposed}, which is under the prefix",
            observed_version=after.exposed,
        )
    return Settlement(
        False,
        "the prefix holds the same builds and the same exposure as when this was "
        "planned, so nothing here shows the operation landed",
        observed_version=after.exposed,
    )
