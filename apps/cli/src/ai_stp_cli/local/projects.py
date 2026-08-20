"""Finding projects and deciding what a project root is (`SPEC-004`).

`REQ-401` is the shape of the whole module: the user names an exact root, or a
directory to look inside. The home directory is never scanned, and neither is a
disk. Everything here reads; nothing is created.

Containment is the security boundary and it is easy to get subtly wrong.
`Path.is_relative_to` is documented as string-based — it "neither accesses the
filesystem nor treats `..` segments specially" — so on its own it is not a
containment check at all. Both sides are resolved first, which is what collapses
`..` and follows symlinks to where they actually point.
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from ai_stp_cli.errors import CliFailure

#: Files that mark a directory as an established project. Closed on purpose:
#: `REQ-403` names manifests as the second-level source, and a heuristic like
#: "contains code" would classify a scratch directory as a project.
MANIFESTS: Final[tuple[str, ...]] = (
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pubspec.yaml",
)

#: Extensions that do not make a directory an established project on their own.
#: `REQ-402`: a folder holding only documentation is a *new* project.
DOCUMENT_SUFFIXES: Final[frozenset[str]] = frozenset({".md", ".rst", ".txt", ".adoc", ".markdown"})

#: How many entries a single directory contributes before discovery gives up on
#: it. A directory with a hundred thousand children is not a place to look for
#: projects, and reading it all to find that out is the cost being avoided.
DISCOVERY_ENTRIES: Final[int] = 2000

#: Never entered while looking for projects. These hold other people's code and
#: build output; a project inside one of them is not this user's project.
SKIPPED_DIRECTORIES: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "vendor",
        "target",
        "dist",
        "build",
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".idea",
        ".vscode",
    }
)


@dataclass(frozen=True)
class Candidate:
    """One directory that could be registered as a project."""

    root: Path

    #: `project` or `nested_repository`. A nested repository is reported so the
    #: user can see it, and registered only if they say so (`REQ-410`).
    kind: str

    #: `new` or `established` (`REQ-402`).
    state: str

    #: What identified it: manifest names, `git`, or nothing.
    markers: tuple[str, ...]

    #: Why it is classified this way, in words a caller can show.
    reason: str


@dataclass(frozen=True)
class Diagnostic:
    """One explicit reason discovery did not inspect a path."""

    path: Path
    code: Literal["excluded", "entry_limit", "symlink", "unreadable"]
    reason: str


@dataclass(frozen=True)
class Discovery:
    """Candidates plus proof of whether the named scope was fully examined."""

    candidates: tuple[Candidate, ...]
    diagnostics: tuple[Diagnostic, ...]

    @property
    def complete(self) -> bool:
        return not any(item.code in {"entry_limit", "unreadable"} for item in self.diagnostics)

    def __iter__(self) -> Iterator[Candidate]:
        return iter(self.candidates)

    def __len__(self) -> int:
        return len(self.candidates)

    def __getitem__(self, index: int) -> Candidate:
        return self.candidates[index]


def resolved(path: Path) -> Path:
    """The path this actually refers to, with `..` and symlinks collapsed.

    `strict=False` so a path that does not exist yet still resolves as far as it
    can. Containment must be decidable for a path the caller only proposes.
    """
    return path.expanduser().resolve()


def contains(root: Path, candidate: Path) -> bool:
    """Whether `candidate` really is inside `root`.

    Both sides are resolved, because `is_relative_to` compares text. Comparing
    unresolved paths would accept `root/../elsewhere` and would follow a symlink
    out of the tree without noticing.
    """
    return resolved(candidate).is_relative_to(resolved(root))


def _entries(directory: Path) -> Iterator[Path]:
    """Direct children, bounded, tolerating a directory that cannot be read."""
    entries, _diagnostic = _listed(directory)
    yield from entries


def _listed(directory: Path) -> tuple[tuple[Path, ...], Diagnostic | None]:
    """A stable bounded listing and the reason it may be incomplete."""
    entries: list[Path] = []
    try:
        with os.scandir(directory) as scan:
            for index, entry in enumerate(scan):
                if index >= DISCOVERY_ENTRIES:
                    # A filesystem listing has no stable order. Returning the
                    # arbitrary prefix would make two identical trees produce
                    # different partial candidates, so an over-limit directory
                    # contributes no children and an explicit diagnostic.
                    return (), Diagnostic(
                        directory,
                        "entry_limit",
                        "directory entry limit reached; this scope is incomplete",
                    )
                entries.append(Path(entry.path))
    except OSError as error:
        return (), Diagnostic(
            directory,
            "unreadable",
            f"directory could not be listed: {type(error).__name__}",
        )
    return tuple(sorted(entries)), None


def _markers_of(root: Path) -> tuple[str, ...]:
    """Markers present in `root`, tolerating a directory that cannot be read.

    One guarded listing rather than a probe per name. Probing with `is_file()`
    looked simpler and was environment-dependent: it swallows some `OSError`s
    and not `PermissionError`, and CI showed an unreadable directory raising
    where the developer machine returned `False`. Discovery runs over
    directories nobody promised are readable, so it has to answer the same way
    everywhere.
    """
    names = {child.name for child in _entries(root)}
    found = [name for name in MANIFESTS if name in names]
    if ".git" in names:
        found.append("git")
    return tuple(sorted(found))


def classify(root: Path) -> Candidate:
    """Decide what this directory is, without changing it.

    `REQ-402`: an empty folder, an empty Git repository and a folder holding
    only documentation are all *new* projects. That is one rule with three
    faces — none of them has anything to index yet, and telling the user "not a
    project" would be wrong in all three.
    """
    place = resolved(root)
    if not place.is_dir():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that path is not a directory",
            next_actions=["project discover --root <path> --json"],
        )

    markers = _markers_of(place)
    manifests = tuple(name for name in markers if name != "git")
    if manifests:
        return Candidate(place, "project", "established", markers, "carries a project manifest")

    # Files only. A directory holding nothing but other directories is a place
    # projects live in, not a project — counting subdirectories here made a
    # workspace container classify as established and hid everything inside it.
    documents = 0
    other = 0
    for child in _entries(place):
        if child.name.startswith(".") or child.is_dir():
            continue
        if child.suffix.lower() in DOCUMENT_SUFFIXES:
            documents += 1
        else:
            other += 1

    if other == 0:
        reason = "only documentation so far" if documents else "nothing here yet"
        return Candidate(place, "project", "new", markers, reason)
    return Candidate(place, "project", "established", markers, "carries files but no manifest")


def discover(discovery_root: Path) -> Discovery:
    """Candidates inside a directory the user named. Never the home directory.

    A monorepo is one project (`REQ-409`): once a directory is identified, its
    children are not examined, so a workspace package does not become a project
    of its own.

    A Git repository nested inside another is reported separately (`REQ-410`)
    rather than folded in or silently registered — it is somebody's decision,
    and the CLI does not get to make it.
    """
    top = resolved(discovery_root)
    if not top.is_dir():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that discovery root is not a directory",
            next_actions=["project discover --root <path> --json"],
        )
    configured_home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    home = Path(configured_home).expanduser() if configured_home else Path.home()
    if top == resolved(home):
        # `REQ-1416` and `REQ-401`. Not a size limit dressed up as a rule: the
        # home directory is where everything else lives, and walking it is how a
        # tool ends up reading somebody's mail.
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the home directory is not a discovery root; name a directory inside it",
            next_actions=["project discover --root <path> --json"],
        )

    found: list[Candidate] = []
    diagnostics: list[Diagnostic] = []
    self_candidate = classify(top)
    if self_candidate.state == "established":
        found.append(self_candidate)
        nested, observed = _repository_descendants(top, nested=True)
        found.extend(nested)
        diagnostics.extend(observed)
        return _discovery(found, diagnostics)

    children, root_diagnostic = _listed(top)
    if root_diagnostic is not None:
        diagnostics.append(root_diagnostic)
    for child in children:
        # Containment is the filter, not a check beside one. A symlink pointing
        # out of the tree resolves outside and is excluded by the same rule that
        # excludes `..`; a symlink pointing back inside is part of this tree and
        # is kept. One rule, no second place to forget.
        if child.name in SKIPPED_DIRECTORIES:
            diagnostics.append(Diagnostic(child, "excluded", "directory is excluded by policy"))
            continue
        if child.is_symlink():
            diagnostics.append(Diagnostic(child, "symlink", "symlink is not followed"))
            continue
        if not child.is_dir() or not contains(top, child):
            continue
        candidate = classify(child)
        found.append(candidate)
        repositories, observed = _repository_descendants(
            child,
            nested=candidate.state == "established",
        )
        found.extend(repositories)
        diagnostics.extend(observed)
    if not found:
        found.append(self_candidate)
    return _discovery(found, diagnostics)


def _repository_descendants(
    root: Path,
    *,
    nested: bool,
) -> tuple[tuple[Candidate, ...], tuple[Diagnostic, ...]]:
    """Find every Git marker below an explicit root, without following links."""
    base = resolved(root)
    found: list[Candidate] = []
    diagnostics: list[Diagnostic] = []
    stack: list[tuple[Path, bool]] = [(base, nested)]
    seen: set[Path] = set()
    while stack:
        directory, inside_project = stack.pop()
        canonical = resolved(directory)
        if canonical in seen:
            continue
        seen.add(canonical)
        entries, diagnostic = _listed(directory)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
            continue
        names = {item.name for item in entries}
        is_repository = directory != base and ".git" in names
        child_inside = inside_project
        if is_repository:
            kind = "nested_repository" if inside_project else "project"
            found.append(
                Candidate(
                    directory,
                    kind,
                    classify(directory).state,
                    _markers_of(directory),
                    (
                        "a separate repository inside the root; register it only on purpose"
                        if kind == "nested_repository"
                        else "a Git repository inside the named discovery scope"
                    ),
                )
            )
            child_inside = True
        for child in reversed(entries):
            if child.name == ".git":
                continue
            if child.name in SKIPPED_DIRECTORIES:
                diagnostics.append(Diagnostic(child, "excluded", "directory is excluded by policy"))
                continue
            if child.is_symlink():
                diagnostics.append(Diagnostic(child, "symlink", "symlink is not followed"))
                continue
            try:
                is_directory = child.is_dir()
            except OSError as error:
                diagnostics.append(
                    Diagnostic(
                        child,
                        "unreadable",
                        f"path could not be inspected: {type(error).__name__}",
                    )
                )
                continue
            if is_directory and contains(base, child):
                stack.append((child, child_inside))
    return tuple(found), tuple(diagnostics)


def _discovery(found: list[Candidate], diagnostics: list[Diagnostic]) -> Discovery:
    """Deduplicate aliases and make both output lists deterministic."""
    candidates = {resolved(item.root): item for item in found}
    observations = {(resolved(item.path), item.code): item for item in diagnostics}
    return Discovery(
        candidates=tuple(candidates[path] for path in sorted(candidates)),
        diagnostics=tuple(observations[key] for key in sorted(observations)),
    )
