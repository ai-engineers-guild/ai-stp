"""Assemble the public `ai-stp` tree from this repository.

The public repository is not this repository with files deleted. It is built
from a manifest that names what may be published, so a path nobody named stays
private by default. A denylist would publish every future file until somebody
remembered to exclude it, and the cost of that mistake is not symmetric: an
omission is fixed by naming the path, a leak is fixed by rotating whatever
leaked.

Two nets, not one. The manifest decides which paths are eligible; a content
scan then refuses the build outright if an eligible file still carries private
infrastructure — fleet class names, the deployment host's filesystem layout,
the private tracker. The scan exists because eligibility is decided per
directory and leakage happens per line.

Only tracked files are considered, so build output, caches, virtualenvs and
anything already ignored cannot reach the public tree by accident.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MANIFEST: Final[Path] = ROOT / "release_scripts" / "public_manifest.toml"
#: The private names the scan refuses, kept apart from the manifest so the
#: manifest can be published without publishing them. Absent in a built tree,
#: which is correct: it has no private infrastructure to look for.
FORBIDDEN: Final[Path] = ROOT / "release_scripts" / "public_forbidden.toml"
#: Files the public tree carries instead of, or in addition to, the source.
#: Committed here rather than under the build directory, which is output.
OVERLAY: Final[Path] = ROOT / "release_scripts" / "public_overlay"

#: Files whose bytes are not text and cannot be scanned line by line. They are
#: still published; the manifest decides that, and a binary carrying a host
#: name is a different problem from a document mentioning one.
BINARY_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".pdf", ".zip"}
)


class ExportError(RuntimeError):
    """The public tree cannot be built as described."""


@dataclass(frozen=True)
class Manifest:
    roots: tuple[str, ...]
    withheld: dict[str, str]
    forbidden: dict[str, str]


def _load_forbidden(path: Path = FORBIDDEN) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ExportError(f"forbidden list unreadable: {error}") from error
    return {str(k): str(v) for k, v in dict(raw.get("forbidden", {})).items()}


def load_manifest(path: Path = MANIFEST) -> Manifest:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ExportError(f"manifest unreadable: {error}") from error
    roots = raw.get("roots")
    if not isinstance(roots, list) or not roots:
        raise ExportError("manifest declares no roots")
    return Manifest(
        roots=tuple(str(item) for item in roots),
        withheld={str(k): str(v) for k, v in dict(raw.get("withheld", {})).items()},
        forbidden=_load_forbidden(),
    )


def tracked_files(root: Path = ROOT) -> tuple[str, ...]:
    """Every file Git tracks, which is the only source the export reads."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExportError(f"could not list tracked files: {error}") from error
    return tuple(name for name in listed.split("\0") if name)


def eligible(files: tuple[str, ...], manifest: Manifest) -> tuple[str, ...]:
    """The tracked files the manifest publishes, in listing order.

    A file is eligible when its root is published and neither it nor its root
    is withheld. Withholding a single path is how a directory stays public
    while one document inside it does not.
    """
    roots = set(manifest.roots)
    return tuple(
        name
        for name in files
        if (name in roots or name.split("/", 1)[0] in roots) and not _is_withheld(name, manifest)
    )


def _is_withheld(name: str, manifest: Manifest) -> bool:
    """Whether a tracked path is withheld by itself or by a directory above it.

    Prefix matching, not equality. Naming a directory has to withhold what is
    inside it, or a withholding reads as effective while every file under it
    still ships — which is exactly what happened to the overlay directory the
    first time this was written.
    """
    return any(
        name == withheld or name.startswith(f"{withheld}/") for withheld in manifest.withheld
    )


def unnamed_roots(files: tuple[str, ...], manifest: Manifest) -> tuple[str, ...]:
    """Tracked top-level entries nothing accounts for.

        Reported rather than assumed private. Silence would let a new top-level
        directory sit unpublished and unexplained, which is how an export starts
        lying about being complete.

    `roots` names what the built tree may contain, whether the source or the
        overlay puts it there, so the overlay is not a separate account. Treating it
        as one would pass here and still fail inside the built tree, where the
        overlay does not exist and the published repository runs this same report in
        its own gate — the worst place to learn it.
    """
    named = set(manifest.roots) | {name.split("/", 1)[0] for name in manifest.withheld}
    seen = {name.split("/", 1)[0] if "/" in name else name for name in files}
    return tuple(sorted(seen - named))


def forbidden_hits(
    files: tuple[str, ...], manifest: Manifest, root: Path = ROOT
) -> dict[str, list[str]]:
    """Which eligible files still carry private infrastructure, by pattern."""
    hits: dict[str, list[str]] = {}
    for name in files:
        if Path(name).suffix in BINARY_SUFFIXES:
            continue
        try:
            body = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in manifest.forbidden:
            if pattern in body:
                hits.setdefault(pattern, []).append(name)
    return hits


def overlay_files(overlay: Path = OVERLAY) -> tuple[str, ...]:
    """Paths the overlay supplies, relative to the tree root."""
    if not overlay.is_dir():
        return ()
    return tuple(
        sorted(str(path.relative_to(overlay)) for path in overlay.rglob("*") if path.is_file())
    )


def write_tree(files: tuple[str, ...], destination: Path, root: Path = ROOT) -> int:
    if destination.exists():
        shutil.rmtree(destination)
    for name in files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    for name in overlay_files():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OVERLAY / name, target)
    _initialise_repository(destination)
    _regenerate_indexes(destination)
    return len(files) + len(overlay_files())


def _regenerate_indexes(destination: Path) -> None:
    """Rebuild the generated indexes against the tree that was actually built.

    The source indexes list every document this working copy has, including the
    ones the manifest withholds, so copying them unchanged would publish a table
    of contents pointing at files that are not there. The generator ships inside
    the tree and derives its root from its own location, so running the copy
    rebuilds the copy.
    """
    linter = destination / "docs_scripts" / "docs_lint.py"
    if not linter.is_file():
        return
    try:
        subprocess.run(
            [sys.executable, str(linter), "--fix"],
            cwd=destination,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExportError(f"could not rebuild the built tree's indexes: {error}") from error


def _initialise_repository(destination: Path) -> None:
    """Make the built tree its own repository, with no history carried over.

    Two reasons, and the second one is not obvious. The public repository is
    meant to start clean rather than inherit this working copy's history, so it
    has to be initialised somewhere. And the tooling that ships inside the tree
    asks Git which documents exist: run inside a directory that belongs to the
    *parent* repository and is ignored by it, `git ls-files` succeeds and
    answers nothing, so every cross-reference in the built tree looks broken
    while the same check passes at the source.
    """
    try:
        subprocess.run(["git", "init", "--quiet"], cwd=destination, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExportError(f"could not initialise the built tree: {error}") from error


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "public" / "build")
    parser.add_argument(
        "--report",
        action="store_true",
        help="describe what would be published without writing anything",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        manifest = load_manifest()
        files = tracked_files()
    except ExportError as error:
        print(f"public export failed: {error}", file=sys.stderr)
        return 1

    chosen = eligible(files, manifest)
    unnamed = unnamed_roots(files, manifest)
    # The overlay is scanned on the same terms as the source. A file written
    # for the public tree is exactly as able to name a private host.
    hits = forbidden_hits(chosen, manifest)
    for pattern, names in forbidden_hits(overlay_files(), manifest, OVERLAY).items():
        hits.setdefault(pattern, []).extend(f"overlay:{name}" for name in names)

    print(f"tracked: {len(files)}")
    print(f"eligible: {len(chosen)}")
    print(f"overlay: {len(overlay_files())}")
    reasons: dict[str, int] = {}
    for reason in manifest.withheld.values():
        reasons[reason] = reasons.get(reason, 0) + 1
    for reason, count in sorted(reasons.items()):
        print(f"withheld: {count} path(s) — {reason}")
    for name in unnamed:
        print(f"UNNAMED ROOT: {name}", file=sys.stderr)
    for pattern, names in sorted(hits.items()):
        print(f"FORBIDDEN {pattern!r} ({manifest.forbidden[pattern]}): {len(names)} file(s)")
        for name in names[:20]:
            print(f"    {name}")
        if len(names) > 20:
            print(f"    ... and {len(names) - 20} more")

    if unnamed:
        print("public export failed: tracked roots the manifest does not name", file=sys.stderr)
        return 1
    if hits:
        print("public export failed: private infrastructure in eligible files", file=sys.stderr)
        return 1
    if args.report:
        return 0

    written = write_tree(chosen, args.out)
    print(f"written: {written} file(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
