"""Where each harness's setup-system provider is, and which version it is (`#452`).

A provider is the only thing that writes a harness target, so which copy of it
is about to run is a fact the user has to be able to see and choose. Before
this, `ai-stp` could fetch one and could be handed one with `--provider`, and
had nowhere to record which one it had settled on: the choice lived in whatever
argument the last command happened to carry.

Four sources answer "which provider", in a fixed order, and every answer says
which source it came from. Silence about provenance is what makes an accidental
executable indistinguishable from a chosen one.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.paths import data_dir, is_executable_file

#: How a path was arrived at, narrowest authority first. The order is the
#: resolution order: an explicit argument beats the configuration file, which
#: beats what the registry remembers, which beats looking around the disk.
SOURCE_ARGUMENT: Final[str] = "argument"
SOURCE_CONFIG: Final[str] = "config"
SOURCE_DISCOVERED: Final[str] = "discovered"

#: How a remembered row came to exist. `chosen` is the one that settles the
#: question: somebody named this provider, through an argument, the
#: configuration, or an update that installed it here.
SOURCE_CHOSEN: Final[str] = "chosen"

SOURCES: Final[tuple[str, ...]] = (
    SOURCE_ARGUMENT,
    SOURCE_CONFIG,
    SOURCE_CHOSEN,
    SOURCE_DISCOVERED,
)

#: What is known about the installation, as one word.
#:
#: `ambiguous` is a state and not an error because more than one provider on a
#: machine is normal — a fetched one beside one a package manager placed — and
#: picking silently is the failure. `foreign` marks an executable this tool did
#: not put there: it can be adopted, but not overwritten without being asked.
STATE_INSTALLED: Final[str] = "installed"
STATE_UNKNOWN_VERSION: Final[str] = "unknown_version"
STATE_MISSING: Final[str] = "missing"
STATE_AMBIGUOUS: Final[str] = "ambiguous"
STATE_FOREIGN: Final[str] = "foreign"


@dataclass(frozen=True)
class Installation:
    """One provider executable this machine can run, and what is known of it."""

    harness_id: str

    #: Absolute. Machine output uses it as-is; only rendering folds the home
    #: directory away, because a shortened path cannot be executed.
    path: str
    source: str
    state: str

    provider_id: str = ""
    provider_version: str = ""
    tag: str = ""
    commit: str = ""
    artifact_digest: str = ""

    #: When the local file was last looked at, and when the release source was
    #: last asked. Two separate facts: a version read from disk a second ago
    #: says nothing about whether a newer release exists.
    checked_at: str = ""
    source_checked_at: str = ""


def managed_root() -> Path:
    """Where `provider fetch` puts what it downloads, and so where to look."""
    return data_dir() / "providers"


def discover(harness_id: str) -> tuple[Path, ...]:
    """Every provider executable for this harness this machine appears to hold.

    Sorted, so two runs agree, and complete rather than first-match: returning
    one of several would make the others invisible, and `#452` asks for the
    candidates to be shown rather than chosen between silently.
    """
    root = managed_root() / harness_id
    found: list[Path] = []
    if root.is_dir():
        for tag in sorted(p for p in root.iterdir() if p.is_dir()):
            found.extend(sorted(item for item in tag.iterdir() if _runnable(item)))
    return tuple(found)


def _runnable(place: Path) -> bool:
    """A real file this user could execute. A symlink is not adopted as one.

    `#452` refuses a symlink where an executable is expected, and the reason is
    the same one that makes the containment checks resolve: what a link points
    at can change after it was inspected, and the inspection is what the trust
    verdict was attached to.

    A `.backup` named by digest is the recovery copy `provider update` leaves
    beside the executable. It is runnable by construction and is not a second
    provider: treating it as one made the harness the update had just replaced
    unresolvable.
    """
    return (
        not place.is_symlink() and is_executable_file(place) and not _is_replacement_backup(place)
    )


def _is_replacement_backup(place: Path) -> bool:
    """Whether this name is a digest-named recovery copy, not a provider."""
    stem, marker, leftover = place.name.rpartition(".backup")
    if leftover or marker != ".backup" or not stem:
        return False
    _name, separator, digest = stem.rpartition(".")
    return (
        bool(_name)
        and separator == "."
        and len(digest) == 16
        and set(digest) <= set("0123456789abcdef")
    )


def validated(path: str, *, harness_id: str) -> Path:
    """A configured or supplied provider path, or a refusal naming the reason."""
    if not path:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a provider path is required",
            details={"harness": harness_id},
        )
    place = Path(path).expanduser()
    if not place.is_absolute():
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a provider path must be absolute",
            details={"harness": harness_id, "path": path},
        )
    if place.is_symlink():
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a provider path must name the executable itself, not a symlink to it",
            details={"harness": harness_id, "path": path},
        )
    if not place.is_file():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no provider executable is at that path",
            details={"harness": harness_id, "path": path},
        )
    if not is_executable_file(place):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "that provider path is not executable",
            details={"harness": harness_id, "path": path},
        )
    return place


def remembered(connection: sqlite3.Connection, harness_id: str) -> Installation | None:
    """The installation the registry settled on for this harness, if any."""
    row = connection.execute(
        "SELECT * FROM provider_installation WHERE harness_id = ?", (harness_id,)
    ).fetchone()
    return None if row is None else _decode(row)


def all_remembered(connection: sqlite3.Connection) -> tuple[Installation, ...]:
    """Every remembered installation, by harness, in a fixed order."""
    rows = connection.execute("SELECT * FROM provider_installation ORDER BY harness_id").fetchall()
    return tuple(_decode(row) for row in rows)


def remember(connection: sqlite3.Connection, installation: Installation) -> None:
    """Record the chosen installation for a harness, replacing any earlier one.

    One row per harness: two would make "which provider runs" a question with
    two answers, and the one read would not always be the one meant.
    """
    connection.execute(
        """
        INSERT INTO provider_installation
            (harness_id, path, source, state, provider_id, provider_version,
             tag, commit_sha, artifact_digest, checked_at, source_checked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (harness_id) DO UPDATE SET
            path = excluded.path,
            source = excluded.source,
            state = excluded.state,
            provider_id = excluded.provider_id,
            provider_version = excluded.provider_version,
            tag = excluded.tag,
            commit_sha = excluded.commit_sha,
            artifact_digest = excluded.artifact_digest,
            checked_at = excluded.checked_at,
            source_checked_at = excluded.source_checked_at
        """,
        (
            installation.harness_id,
            installation.path,
            installation.source,
            installation.state,
            installation.provider_id,
            installation.provider_version,
            installation.tag,
            installation.commit,
            installation.artifact_digest,
            installation.checked_at,
            installation.source_checked_at,
        ),
    )


def forget(connection: sqlite3.Connection, harness_id: str) -> bool:
    """Drop the remembered choice, returning to configuration and discovery."""
    cursor = connection.execute(
        "DELETE FROM provider_installation WHERE harness_id = ?", (harness_id,)
    )
    return cursor.rowcount > 0


def _decode(row: sqlite3.Row) -> Installation:
    return Installation(
        harness_id=str(row["harness_id"]),
        path=str(row["path"]),
        source=str(row["source"]),
        state=str(row["state"]),
        provider_id=str(row["provider_id"]),
        provider_version=str(row["provider_version"]),
        tag=str(row["tag"]),
        commit=str(row["commit_sha"]),
        artifact_digest=str(row["artifact_digest"]),
        checked_at=str(row["checked_at"]),
        source_checked_at=str(row["source_checked_at"]),
    )


@dataclass(frozen=True)
class Resolution:
    """Which provider a command would use for one harness, and why that one."""

    harness_id: str
    path: str
    source: str
    state: str

    #: Every candidate found, when more than one was. Shown rather than chosen
    #: between: `#452` requires an explicit choice before update or reinstall
    #: touches a machine holding two.
    candidates: tuple[str, ...] = ()
    reason: str = ""


def resolve(
    connection: sqlite3.Connection | None,
    harness_id: str,
    *,
    argument: str = "",
    configured: str = "",
) -> Resolution:
    """Which provider serves this harness, by the fixed precedence of `#452`.

    Explicit argument, then configuration, then the remembered choice, then
    discovery. Each answer names its own source, because "a provider was found"
    and "this provider was chosen" are different facts and only the second is a
    decision anybody made.
    """
    if argument:
        place = validated(argument, harness_id=harness_id)
        return Resolution(harness_id, str(place), SOURCE_ARGUMENT, STATE_INSTALLED)
    if configured:
        place = validated(configured, harness_id=harness_id)
        return Resolution(harness_id, str(place), SOURCE_CONFIG, STATE_INSTALLED)

    held = None if connection is None else remembered(connection, harness_id)
    # A row written by a **decision** settles the question; a row that merely
    # recorded what discovery saw does not. `provider check` writes the second
    # kind, and honouring it here made a read-only report into a choice: after
    # one check, a machine that later grew a second provider went on reporting
    # the first and never showed the ambiguity. Discovery runs again, and the
    # ambiguity surfaces where it should.
    chosen = held is not None and held.source != SOURCE_DISCOVERED
    if held is not None and chosen and _runnable(Path(held.path)):
        # The stored row's own source travels, not the word "registry". The
        # registry is where the answer was kept, never where it came from, and
        # returning it as a provenance let a discovery be re-recorded as a
        # choice on the next run — after which the machine could grow a second
        # provider and nothing would ever say so.
        return Resolution(harness_id, held.path, held.source, STATE_INSTALLED)

    found: tuple[Path, ...] = discover(harness_id)
    if len(found) == 0:
        return Resolution(
            harness_id,
            "",
            SOURCE_DISCOVERED,
            STATE_MISSING,
            reason=(
                "the registry pointed at a path that is gone"
                if held is not None and chosen
                else "no provider for this harness is installed here"
            ),
        )
    if len(found) > 1:
        # Not an error and not resolved: `#452` asks for the candidates to be
        # shown. Choosing the newest-looking one would be a guess about which
        # copy the user meant, made silently, before overwriting one of them.
        return Resolution(
            harness_id,
            "",
            SOURCE_DISCOVERED,
            STATE_AMBIGUOUS,
            candidates=tuple(str(item) for item in found),
            reason="more than one provider is installed; name one explicitly",
        )
    return Resolution(harness_id, str(found[0]), SOURCE_DISCOVERED, STATE_INSTALLED)


def newer(latest: str, current: str) -> bool:
    """Whether `latest` is a later release than `current`, compared by number.

    Field by field as integers, because `0.0.10` is later than `0.0.9` and is
    the lesser of the two as text — which is the comparison `#452` names
    explicitly, and the one an obvious implementation gets wrong.
    """
    return _ordered(latest) > _ordered(current)


def _ordered(version: str) -> tuple[int, ...]:
    """A version as comparable numbers. Unreadable parts sort before readable.

    A field that is not a number contributes `-1` rather than raising: a
    provider is allowed to spell its version in a way this does not parse, and
    the honest consequence is "cannot be shown to be newer", not a crash.
    """
    cleaned = version.strip().lstrip("v")
    parts = cleaned.split("+")[0].split("-")[0].split(".")
    return tuple(int(part) if part.isdigit() else -1 for part in parts)
