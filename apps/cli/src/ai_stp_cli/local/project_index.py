"""The bounded second-level index of a project (`SPEC-004` REQ-403 to REQ-406).

What this is *not* is as load-bearing as what it is. `REQ-411` excludes the call
graph, vector representations, private symbol bodies, a global semantic graph and
deep data-flow analysis. This reads names, sizes and shapes — it is an inventory,
not an understanding, and the difference is what keeps it cheap and safe.

Three rules decide every path:

**Containment.** Everything is checked against the root with `projects.contains`,
which resolves both sides — `Path.is_relative_to` is documented as string-based
and would accept `..` and a symlink pointing anywhere. `Path.walk` also lists a
symlinked directory among *files* rather than descending into it, so one that
points outside would arrive here as something to index.

**Exclusion.** `REQ-406` names secrets, binary content, version-control internals,
vendor, cache and generated directories. A file is excluded with a reason rather
than silently dropped, because "why is this not in my index" is a question the
caller will have.

**Bounds.** `REQ-405` makes size, depth and time limits mandatory, and hitting one
produces a typed partial state rather than a short answer that looks complete.
"""

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import projects

#: Read to decide whether a file is text. Git's `buffer_is_binary` uses exactly
#: this: a NUL byte within the first 8000 bytes means binary. Borrowed rather
#: than invented — every tool a user already trusts agrees on it.
BINARY_PROBE_BYTES: Final[int] = 8000

#: Above this a file is inventoried but not read. `REQ-405` requires a size
#: bound; without one a single generated blob decides how long indexing takes.
MAX_FILE_BYTES: Final[int] = 1 * 1024 * 1024

#: How deep the tree is walked, counted from the root.
MAX_DEPTH: Final[int] = 12

#: How many files are indexed before the answer becomes partial.
MAX_ENTRIES: Final[int] = 20_000

#: The wall-clock budget. A slow filesystem is a real thing, and an index that
#: takes minutes is one an agent will stop waiting for.
MAX_SECONDS: Final[float] = 20.0

#: Files whose *name* says they hold a credential. Content is never inspected to
#: decide this: reading a file to find out whether it holds a secret is the one
#: thing that must not happen. `ADR-0058` keeps credentials out of this CLI, and
#: `SPEC-004` REQ-406 keeps them out of the index.
SECRET_NAMES: Final[frozenset[str]] = frozenset(
    {
        ".env",
        ".envrc",
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".htpasswd",
        "credentials",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "secrets.yaml",
        "secrets.yml",
        "secrets.json",
    }
)

SECRET_PREFIXES: Final[tuple[str, ...]] = (".env.",)

SECRET_SUFFIXES: Final[tuple[str, ...]] = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".ppk",
)

#: Declared, not guessed from a suffix: which file means what is a fact about an
#: ecosystem, and a rename must not silently change what a file is taken to be.
MANIFEST_NAMES: Final[frozenset[str]] = frozenset(
    {
        "pyproject.toml",
        "setup.cfg",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pubspec.yaml",
        "requirements.txt",
    }
)

LOCK_NAMES: Final[frozenset[str]] = frozenset(
    {
        "uv.lock",
        "poetry.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "Cargo.lock",
        "go.sum",
        "pubspec.lock",
    }
)

#: Surfaces an agent reads. `REQ-403` asks for them by name, and they are the
#: reason a coding agent can be told anything about a project at all.
AGENT_SURFACE_NAMES: Final[frozenset[str]] = frozenset(
    {"AGENTS.md", "CLAUDE.md", "CLAUDE.local.md", "SKILL.md", ".mcp.json"}
)

DOCUMENT_SUFFIXES: Final[frozenset[str]] = frozenset({".md", ".markdown", ".rst", ".txt", ".adoc"})

CONFIG_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".properties"}
)

#: The five language groups `REQ-404` bounds the symbol index to. Here they only
#: classify a file; the adapters that read them are a separate concern.
SOURCE_SUFFIXES: Final[dict[str, str]] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".dart": "dart",
}


@dataclass(frozen=True)
class Entry:
    """One indexed file, described without its content being kept."""

    #: Relative to the root, in POSIX form, so an index is comparable across
    #: machines and no absolute path reaches a passport.
    path: str
    kind: str
    language: str | None
    size_bytes: int

    #: `None` for two different reasons, and `Index.digested` says which: the
    #: file was too large to read — its size is still known — or no digest was
    #: asked for. Stating only the first was true until `build` grew a
    #: `digests` argument on 2026-08-29, and stayed here afterwards: the new
    #: meaning was documented on `Index`, one field away, while this went on
    #: telling a reader the file was too large.
    digest: str | None
    lines: int | None


@dataclass(frozen=True)
class Excluded:
    """One path left out, and why. Silence here is a bug report waiting."""

    path: str
    reason: str


@dataclass
class Budget:
    """What the walk is allowed to spend, and what it has spent."""

    started: float = field(default_factory=time.monotonic)
    entries: int = 0

    def exhausted(self) -> str | None:
        if self.entries >= MAX_ENTRIES:
            return "entry budget"
        if time.monotonic() - self.started >= MAX_SECONDS:
            return "time budget"
        return None


@dataclass(frozen=True)
class Index:
    """Everything the index knows about one project root."""

    root: Path

    #: `complete`, or `partial` when a bound was reached.
    state: str
    entries: tuple[Entry, ...]
    excluded: tuple[Excluded, ...]

    #: Which bound stopped it, when one did.
    stopped_by: str | None

    #: Whether the entries carry content digests. When false, every `digest` is
    #: `None` because none was asked for — which is a different fact from a
    #: file too large to read, and the two would otherwise be spelled the same.
    digested: bool = True


def is_secret_name(name: str) -> bool:
    """Whether this file name says it holds a credential.

    By name only. Opening a file to decide whether it contains a secret is the
    one inspection that cannot be justified, because doing it is the harm.
    """
    lowered = name.lower()
    if lowered in {item.lower() for item in SECRET_NAMES}:
        return True
    if lowered.startswith(SECRET_PREFIXES):
        return True
    return lowered.endswith(SECRET_SUFFIXES)


def is_binary(head: bytes) -> bool:
    """Git's rule: a NUL byte within the first 8000 bytes means binary.

    Takes the bytes rather than the path, because reading them is also how a
    file is found to be unreadable — and "cannot be read" and "binary content"
    are different answers that a caller acts on differently. Deciding both from
    one read is what keeps them from being confused for each other.
    """
    return b"\0" in head[:BINARY_PROBE_BYTES]


def classify(path: Path) -> tuple[str, str | None]:
    """What kind of file this is, and which language if any."""
    name = path.name
    if name in AGENT_SURFACE_NAMES:
        return "agent_surface", None
    if name in MANIFEST_NAMES:
        return "manifest", None
    if name in LOCK_NAMES:
        return "lock", None
    suffix = path.suffix.lower()
    language = SOURCE_SUFFIXES.get(suffix)
    if language is not None:
        return "source", language
    if suffix in DOCUMENT_SUFFIXES:
        return "document", None
    if suffix in CONFIG_SUFFIXES:
        return "config", None
    return "text", None


def build(root: Path, *, digests: bool = True) -> Index:
    """Walk the root once and describe what is safely readable inside it.

    Deterministic: entries come back sorted by path, so two runs over an
    unchanged tree produce the same index and a difference between them is worth
    looking at.

    `digests=False` is for a caller that needs the inventory and not the
    content-addressed part of it. Measured on this repository (`#453`, 4080
    files): reading them costs 0.29s and hashing them 0.91s, so the hash is
    three quarters of the walk and `select eligibility` — which reads only
    names, languages and whether `.git` exists — paid all of it.

    Everything else is unchanged: the same walk, the same classification, the
    same exclusions, the same binary check, which is why the content is still
    read. Only the hash is skipped, and `Index.digested` says so, so that
    `digest is None` does not have to carry two meanings at once.
    """
    base = projects.resolved(root)
    if not base.is_dir():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that project root is not a directory",
            next_actions=["project discover --root <path> --json"],
        )

    budget = Budget()
    entries: list[Entry] = []
    excluded: list[Excluded] = []
    stopped_by: str | None = None

    for directory, subdirectories, filenames in base.walk(on_error=lambda _error: None):
        depth = len(directory.relative_to(base).parts)
        if depth >= MAX_DEPTH:
            excluded.append(Excluded(_relative(base, directory), "depth budget"))
            subdirectories.clear()
            continue

        # Only real directories reach this list: `Path.walk` does not follow
        # symlinks and puts a symlinked directory among the *file* names, so a
        # link pointing out of the tree is refused below rather than here. A
        # containment check on this list could never fire.
        kept: list[str] = []
        for name in sorted(subdirectories):
            place = directory / name
            if name in projects.SKIPPED_DIRECTORIES:
                excluded.append(Excluded(_relative(base, place), "excluded directory"))
                continue
            kept.append(name)
        subdirectories[:] = kept

        for name in sorted(filenames):
            reached = budget.exhausted()
            if reached is not None:
                stopped_by = reached
                break
            place = directory / name
            outcome = _describe(base, place, digests=digests)
            if isinstance(outcome, Excluded):
                excluded.append(outcome)
                continue
            entries.append(outcome)
            budget.entries += 1
        if stopped_by is not None:
            break

    return Index(
        root=base,
        state="partial" if stopped_by else "complete",
        entries=tuple(sorted(entries, key=lambda item: item.path)),
        excluded=tuple(sorted(excluded, key=lambda item: item.path)),
        stopped_by=stopped_by,
        digested=digests,
    )


def _relative(base: Path, place: Path) -> str:
    """The path as walked, not as resolved.

    Containment resolves; naming must not. A symlink inside the tree resolves to
    its target, so naming it by the resolved path filed it under the target's
    name — the entry appeared twice and the link itself vanished from the index.
    The walk only ever hands out paths under `base`, so this is a plain slice.
    """
    try:
        return place.relative_to(base).as_posix()
    except ValueError:  # pragma: no cover - the walk never leaves the base
        return place.name


def _describe(base: Path, place: Path, *, digests: bool = True) -> Entry | Excluded:
    """Decide one file: excluded with a reason, or an entry."""
    relative = _relative(base, place)
    if is_secret_name(place.name):
        return Excluded(relative, "looks like a credential")
    if not projects.contains(base, place):
        # `Path.walk` puts a symlinked directory among the file names, so one
        # pointing outside arrives here rather than as a directory.
        return Excluded(relative, "outside the root")

    if place.is_dir():
        # A symlinked directory arrives among the file names. One pointing
        # inside the tree is already walked on its own; indexing the link as a
        # file would report a directory as one.
        return Excluded(relative, "a directory link is not indexed")

    try:
        size = place.stat().st_size
    except OSError:
        return Excluded(relative, "cannot be read")

    kind, language = classify(place)
    if size > MAX_FILE_BYTES:
        # Inventoried, not read: its existence and size are facts worth having,
        # and its content is not worth the budget.
        return Entry(relative, kind, language, size, None, None)

    try:
        content = place.read_bytes()
    except OSError:
        return Excluded(relative, "cannot be read")
    if is_binary(content):
        return Excluded(relative, "binary content")
    return Entry(
        path=relative,
        kind=kind,
        language=language,
        size_bytes=size,
        digest=f"sha256:{hashlib.sha256(content).hexdigest()}" if digests else None,
        lines=content.count(b"\n") + (0 if content.endswith(b"\n") or not content else 1),
    )
