"""The project passport, and what it may and may not carry (`SPEC-004`).

Three things this file exists to get right.

A re-scan keeps the project's identity. A stable id is a ULID and cannot be
derived from a path, so preserving it across scans means looking the project up
by something it already knows — its root — and minting only when that lookup
comes back empty. The alternative, hashing the path into an identifier, would
make identity and location the same fact and would silently rename a project
that moved.

A revision pins exact digests. The index, the toolchain and the configuration
each contribute one digest, and a scan that finds nothing changed adds no
revision at all: content addressing already refuses to store the same content
twice, so idempotency is a property of the store rather than a check here.

Nothing that crosses to the cloud carries source. Nothing crosses at all today:
`summary()` named the counts, digests and language names that were allowed to
leave, and it was removed once nothing called it. If a projection is ever needed
again, build it by naming what goes in rather than by filtering a larger object
— a filter is one forgotten field away from leaking and a whitelist is not.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.local import journal, project_index, revisions, symbols
from ai_stp_cli.local.database import transaction
from ai_stp_cli.local.passports import carry_unchanged, moment, owner
from ai_stp_cli.paths import redact_any_home
from ai_stp_cli.toolchain import install
from ai_stp_cli.toolchain import load as load_manifest
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id

#: Domain separation for each digest this file computes. Two digests of the same
#: bytes for different purposes must not be equal, or a caller could satisfy one
#: check with the other's answer.
INDEX_DOMAIN: Final[str] = "ai-stp:project-index:v1"
TOOLCHAIN_DOMAIN: Final[str] = "ai-stp:project-toolchain:v1"
CONFIGURATION_DOMAIN: Final[str] = "ai-stp:project-configuration:v1"

#: Which indexed kinds count as this project's configuration. Named rather than
#: assumed: `pyproject.toml` and `package.json` are classified as manifests, not
#: as config, and a digest that took only `config` would have silently ignored
#: the two files that decide most about how a project builds. A lock file is
#: here for the same reason, and the agent surface because it decides how an
#: agent behaves inside the project — which is part of reproducing it.
CONFIGURATION_KINDS: Final[frozenset[str]] = frozenset(
    {"manifest", "lock", "config", "agent_surface"}
)


@dataclass(frozen=True)
class Scan:
    """One reading of a project: what is there, and the digests that pin it."""

    root: Path
    stable_id: str
    index_digest: str
    toolchain_digest: str
    configuration_digest: str
    index: project_index.Index
    languages: tuple[symbols.LanguageSummary, ...]


def stable_id_for(connection: sqlite3.Connection, root: Path) -> str | None:
    """The passport already describing this root, if there is one."""
    row = connection.execute(
        "SELECT stable_id FROM project_root WHERE root = ?", (str(root),)
    ).fetchone()
    return None if row is None else str(row["stable_id"])


def scan(connection: sqlite3.Connection, root: Path) -> Scan:
    """Read a project and pin what was read. Writes only the identity mapping.

    The identity is minted at most once per root. Everything else here is a
    reading, so running this twice over an unchanged project produces two equal
    scans — which is what makes the revision below idempotent without needing to
    compare anything.
    """
    resolved = root.resolve()
    index = project_index.build(resolved)
    survey = symbols.survey(
        index.root, [(item.path, item.language) for item in index.entries if item.language]
    )

    # The filesystem reading above runs outside any lock — it is slow and
    # touches no shared state. The identity claim below runs under
    # `BEGIN IMMEDIATE`: two concurrent scans of one root used to both find no
    # mapping, both mint, and the loser died on the naked PRIMARY KEY conflict
    # as `AI_STP_INTERNAL` — leaving its entity row behind as an orphan no
    # command can address. Under the write lock the second scan's lookup runs
    # after the first one's commit and adopts the same identity.
    with transaction(connection):
        known = stable_id_for(connection, index.root)
        if known is None:
            known = new_id("project")
            connection.execute(
                "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'project', ?)",
                (known, moment()),
            )
            connection.execute(
                "INSERT INTO project_root (root, stable_id) VALUES (?, ?)",
                (str(index.root), known),
            )

    return Scan(
        root=index.root,
        stable_id=known,
        index_digest=_index_digest(index),
        toolchain_digest=_toolchain_digest(),
        configuration_digest=_configuration_digest(index),
        index=index,
        languages=survey.languages,
    )


def record(
    connection: sqlite3.Connection, found: Scan, *, device_id: str
) -> revisions.StoredRevision:
    """Store this scan as a revision of the project passport.

    A second scan of an unchanged project stores nothing new: the content is
    identical, the revision id is that content's digest, and `commit` returns
    the revision that is already there rather than adding one beside it. That is
    the store's guarantee, not a comparison performed here — a comparison could
    disagree with the store and this cannot.
    """
    at = moment()
    # One write transaction from reading the heads to committing the child.
    # Read outside it, two concurrent recorders both saw no head and both
    # committed a parentless root — a fork nothing raced for. Under
    # `BEGIN IMMEDIATE` the second recorder reads the first one's head and
    # threads it as a parent, which is the whole point of the parent chain.
    try:
        with transaction(connection):
            # Every head, not `head()`: that helper refuses a forked object,
            # and a scan is exactly the thing that can converge one — it
            # states the whole current truth of the filesystem, so it
            # supersedes every open line at once.
            current = revisions.heads(connection, found.stable_id)
            previous = current[-1] if current else None
            content = _content(found, at, previous, parents=[item.revision_id for item in current])
            if (
                len(current) == 1
                and previous is not None
                and previous.envelope.model_dump(mode="json")["facts"] == (content["facts"])
            ):
                # Nothing observed has changed. Committing anyway would store
                # a revision whose only difference is when it was written, and
                # `SPEC-003` REQ-312 is explicit that a re-scan must not
                # manufacture history. With more than one head the commit
                # happens even for equal facts, because its purpose is then
                # the convergence itself.
                return previous

            operation_id = journal.begin(connection, "passport.project.record", at)
            stored = revisions.commit(
                connection,
                content,
                device_id=device_id,
                operation_id=operation_id,
            )
            journal.settle(connection, operation_id, "verified", moment())
            return stored
    except BaseException as error:
        # The transaction rolled the attempt back, the begun operation row
        # included. Record the failure durably on its own: an operation that
        # started and neither finished nor failed is worse than one that
        # failed, because a later reader cannot tell it from one still running.
        failed = journal.begin(connection, "passport.project.record", at)
        journal.settle(connection, failed, "failed", moment(), type(error).__name__)
        raise


def _content(
    found: Scan,
    at: str,
    previous: revisions.StoredRevision | None,
    *,
    parents: list[str],
) -> dict[str, JsonValue]:
    """The passport content itself, which stays on this machine.

    Two things here are deliberately not the current clock. A fact whose value
    did not change keeps the `observed_at` it already had, and `created_at`
    stays at the moment the passport was created — otherwise every re-scan would
    differ from the last by a timestamp alone, and content addressing would
    faithfully record that as a change.

    The root is redacted even here. A local passport is still read by agents,
    copied into reports and pasted into issues, and the home directory is not
    something a project's identity needs to carry.
    """
    facts: dict[str, JsonValue] = {
        "root": _fact(redact_any_home(found.root), at),
        "index_digest": _fact(found.index_digest, at),
        "toolchain_digest": _fact(found.toolchain_digest, at),
        "configuration_digest": _fact(found.configuration_digest, at),
        "file_count": _fact(len(found.index.entries), at),
        "index_state": _fact(found.index.state, at),
    }
    if previous is not None:
        earlier = previous.envelope.model_dump(mode="json")
        facts = carry_unchanged(facts, cast(dict[str, JsonValue], earlier["facts"]))
        at = str(earlier["created_at"])

    return {
        "schema_version": 1,
        "kind": "project",
        "stable_id": found.stable_id,
        "owner_id": owner().account_id,
        "created_at": at,
        "visibility": "private",
        # The heads this scan supersedes. This used to be hardcoded empty, so
        # the first legitimate change committed a second parentless root: two
        # heads, composition refused with "needs a merge", and no command able
        # to perform one for a project.
        "parent_revision_ids": cast(JsonValue, parents),
        "facts": facts,
    }


def _fact(value: JsonValue, at: str) -> JsonValue:
    return {"value": value, "origin": "observed", "confirmation": "none", "observed_at": at}


def _index_digest(index: project_index.Index) -> str:
    """A digest over what the index found, and nothing about when it ran.

    Paths and content digests only. Sizes and line counts are derived from the
    same bytes, and timestamps are not content at all — including either would
    make two identical trees disagree and defeat the point.
    """
    entries: list[JsonValue] = [
        {"path": item.path, "digest": item.digest} for item in sorted(index.entries, key=_by_path)
    ]
    return digest_canonical(INDEX_DOMAIN, {"state": index.state, "entries": entries})


def _toolchain_digest() -> str:
    """A digest over which managed tools are actually current on this machine.

    What is pinned *and* installed, not what is pinned. Two machines running the
    same manifest with different tools installed are not reproducing each other,
    and a digest that could not tell them apart would say they were.
    """
    tools: list[JsonValue] = []
    for tool in load_manifest().tools:
        active = install.current_target(tool.tool_id)
        tools.append(
            {
                "tool_id": tool.tool_id,
                "pinned": tool.version,
                "installed": active.name if active is not None else None,
            }
        )
    return digest_canonical(TOOLCHAIN_DOMAIN, {"tools": tools})


def _configuration_digest(index: project_index.Index) -> str:
    """A digest over the project's configuration files, by content.

    The index already classified these and already read their digests under its
    own bounds, so this reads nothing further: a second read could see a
    different file than the one the index recorded and pin a state that never
    existed as a whole.
    """
    configuration: list[JsonValue] = [
        {"path": item.path, "digest": item.digest}
        for item in sorted(index.entries, key=_by_path)
        if item.kind in CONFIGURATION_KINDS
    ]
    return digest_canonical(CONFIGURATION_DOMAIN, {"files": configuration})


def _by_path(entry: project_index.Entry) -> str:
    return entry.path
