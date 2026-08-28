"""Bring the public tree back into this working copy.

The inverse of `public_export.py`, and it exists because the direction of work
changed: `ai-stp` is where contributors land changes, and this repository is
the working copy that carries what the public tree deliberately does not — the
runner fleet's workflows, the internal status reports, the agent's memory, the
decisions about infrastructure only this copy has.

Nothing new has to be declared for that. The set this import must not overwrite
is already written down twice over: `[withheld]` in the manifest names what
stays private, and `release_scripts/public_overlay/` names the files the public
tree carries *instead of* this one's. Everything else is published, so
everything else is imported.

An overlay path is not skipped, though — it is imported one directory over.
`release_scripts/public_overlay/<name>` is the source of the public tree's copy
of `<name>`, so an edit made upstream belongs there, and only the private
document at `<name>` itself has to survive untouched.

The asymmetry with the export is deliberate. The export refuses on doubt,
because a mistake there publishes something private and is fixed by rotating
whatever leaked. A mistake here overwrites a local file, which Git makes
recoverable — so this reports loudly and writes, rather than refusing.

What it does not do is regenerate. `docs/adr/index.md`, `docs/index.md`,
`schemas/v1` and the rest are derived, and the public tree's copies are derived
from a tree that has fewer documents in it. Importing them unchanged leaves this
copy with an index that omits its own records. `just public-sync` therefore runs
the generators afterwards, and `just back-static` and `just docs-check` fail on
the drift if anybody skips that step.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

from release_scripts.public_export import (
    ROOT,
    ExportError,
    Manifest,
    _is_withheld,
    eligible,
    load_manifest,
    overlay_files,
    tracked_files,
)


def overlay_targets() -> frozenset[str]:
    """Paths the public tree holds that this one keeps its own version of.

    They exist in both trees with different content — `AGENTS.md`, the CI
    documents, the workflows — so importing one *at its own path* would replace
    the private half with the public half and lose it without a word.

    That is why they are separated, and it is only half the story. The bytes the
    public tree carries came from `release_scripts/public_overlay/<name>`, and
    that copy is a file of this repository like any other. Skipping the name
    outright left the overlay unable to learn anything: work lands in the public
    tree (`ADR-0110`), so a workflow edited there had no route home, and the
    next `public-build` put the old bytes back without failing anything.

    Measured on 2026-08-29, seven of twenty-one had drifted that way — the
    Dependabot ecosystem fix, a pinned Postgres digest, the deploy timeout
    raised against a measured 27 minutes, a script-injection fix and two action
    bumps. `public-sync-verify` answered `disagreements: 0` throughout, because
    it excluded exactly the paths that can disagree unobserved.

    So the name is kept out of `write` and its bytes are imported into the
    overlay instead.
    """
    return frozenset(overlay_files())


def overlay_dir(root: Path = ROOT) -> Path:
    """Where this copy keeps the bytes the public tree publishes at `<name>`."""
    return root / "release_scripts" / "public_overlay"


class ImportError_(RuntimeError):
    """The public tree cannot be imported as described."""


def public_files(tree: Path) -> tuple[str, ...]:
    """Every file the public checkout tracks.

    Tracked, not walked. A public checkout carries build output, virtual
    environments and caches exactly like this one does, and none of that is
    part of what was published.
    """
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=tree,
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ImportError_(f"could not list the public tree: {error}") from error
    names = tuple(name for name in listed.split("\0") if name)
    if not names:
        raise ImportError_(f"{tree} tracks no files; is it a checkout of the public repository?")
    return names


def plan(
    tree: Path, manifest: Manifest, root: Path = ROOT
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """What to write, what to delete and what to leave alone.

    Deletion is the half that is easy to forget and the reason this cannot be a
    copy. A file removed in the public repository stays here forever otherwise,
    and the next export puts it back — so the two trees disagree in a direction
    that only shows up as a file nobody remembers adding.
    """
    overlay = overlay_targets()
    public = public_files(tree)

    incoming = tuple(name for name in public if name not in overlay)
    write = tuple(
        name
        for name in incoming
        if not (root / name).is_file() or not filecmp.cmp(tree / name, root / name, shallow=False)
    )

    held = overlay_dir(root)
    overlay_write = tuple(
        name
        for name in sorted(overlay & set(public))
        if not (held / name).is_file() or not filecmp.cmp(tree / name, held / name, shallow=False)
    )

    published_here = set(eligible(tracked_files(root), manifest))
    delete = tuple(sorted(published_here - set(public) - overlay))
    return write, delete, overlay_write


def apply(
    tree: Path,
    write: tuple[str, ...],
    delete: tuple[str, ...],
    root: Path = ROOT,
    overlay: tuple[str, ...] = (),
) -> None:
    destinations = [(name, root / name) for name in write]
    # The overlay's copy, never the path itself: `AGENTS.md` at the root is this
    # repository's own document and is withheld from publication precisely so
    # that it can say more.
    destinations += [(name, overlay_dir(root) / name) for name in overlay]
    for name, target in destinations:
        target.parent.mkdir(parents=True, exist_ok=True)
        # `copy2` carries the mode, which matters for the same reason it
        # mattered in the publisher: `deploy/pull-deploy.sh` is executed
        # directly by systemd, and a copy that drops the bit stops production
        # without failing anything.
        shutil.copy2(tree / name, target)
    for name in delete:
        (root / name).unlink(missing_ok=True)


#: What `just docs-gen` stamps into every index it writes. A file carrying it
#: enumerates the documents of the tree it was generated in, so the two copies
#: are *supposed* to differ: this one has records the public tree withholds.
#: Detected by the marker rather than listed, because a list goes stale the
#: first time somebody adds a directory and nobody notices it was missing.
GENERATED_MARKER: Final[str] = "генерируется через just docs-gen"


def is_generated(path: Path) -> bool:
    try:
        return GENERATED_MARKER in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def verify(tree: Path, manifest: Manifest, root: Path = ROOT) -> tuple[str, ...]:
    """Paths where the two trees still disagree after an import.

    A round trip, and the only check worth trusting here: every published file
    of this copy must equal the public one byte for byte, except the ones the
    overlay owns and the ones a generator writes from the local document set.
    Anything left is either a path the manifest accounts for wrongly or a
    generator that has not been re-run.
    """
    overlay = overlay_targets()
    public = set(public_files(tree))
    mine = set(eligible(tracked_files(root), manifest))

    disagreements: list[str] = []
    for name in sorted(public - overlay):
        here = root / name
        if not here.is_file():
            disagreements.append(f"missing here: {name}")
        elif not filecmp.cmp(tree / name, here, shallow=False) and not is_generated(here):
            disagreements.append(f"differs: {name}")
    held = overlay_dir(root)
    for name in sorted(overlay & public):
        source = held / name
        if not source.is_file():
            disagreements.append(f"overlay missing: {name}")
        elif not filecmp.cmp(tree / name, source, shallow=False):
            disagreements.append(f"overlay differs: {name}")
    for name in sorted(mine - public - overlay):
        disagreements.append(f"only here: {name}")
    return tuple(disagreements)


def withheld_touched(write: tuple[str, ...], manifest: Manifest) -> tuple[str, ...]:
    """Withheld paths an import would write, which must always be none.

    Belt and braces. The public tree cannot contain a withheld path — the export
    is what decides that — so this can only fire if somebody published one by
    another route. Cheap to assert, and the failure it catches is a private
    document being replaced by a public copy of itself.
    """
    return tuple(name for name in write if _is_withheld(name, manifest))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tree",
        type=Path,
        required=True,
        help="a checkout of the public repository to import from",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="describe what would change without writing anything",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="report where the two trees disagree, and change nothing",
    )
    return parser.parse_args(argv)


LIST_LIMIT: Final[int] = 40


def _print_names(label: str, names: tuple[str, ...]) -> None:
    print(f"{label}: {len(names)}")
    for name in names[:LIST_LIMIT]:
        print(f"  {label[:-1] if label.endswith('s') else label}: {name}")
    if len(names) > LIST_LIMIT:
        print(f"  … and {len(names) - LIST_LIMIT} more")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        manifest = load_manifest()
    except ExportError as error:
        print(f"public import failed: {error}", file=sys.stderr)
        return 1

    tree = args.tree.resolve()
    if not (tree / ".git").exists():
        print(f"public import failed: {tree} is not a Git checkout", file=sys.stderr)
        return 1

    try:
        if args.verify:
            disagreements = verify(tree, manifest)
            for line in disagreements:
                print(f"  {line}")
            print(f"disagreements: {len(disagreements)}")
            return 1 if disagreements else 0

        write, delete, overlay = plan(tree, manifest)
        offenders = withheld_touched(write, manifest)
    except (ImportError_, ExportError) as error:
        print(f"public import failed: {error}", file=sys.stderr)
        return 1

    if offenders:
        print("public import refused: the public tree carries withheld paths", file=sys.stderr)
        for name in offenders:
            print(f"  withheld: {name}", file=sys.stderr)
        return 1

    _print_names("writes", write)
    _print_names("deletes", delete)
    _print_names("overlays", overlay)

    if args.report:
        return 0
    apply(tree, write, delete, overlay=overlay)
    print(f"imported: {len(write)} written, {len(delete)} removed, {len(overlay)} into the overlay")
    print("run `just docs-gen` and `just back-gen`: the indexes are derived")
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
