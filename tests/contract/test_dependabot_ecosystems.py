"""Dependabot must name the package manager each directory actually uses.

Both JavaScript directories carry `bun.lock` and no `package-lock.json`, and
both were declared `package-ecosystem: npm`. Dependabot's npm ecosystem edits
`package.json` and cannot regenerate a bun lockfile, so every pull request it
opened against them failed with

    error: lockfile had changes, but lockfile is frozen

Five were open at once, none mergeable as generated, and they had been
accumulating weekly. Nothing failed: the pull requests were red, `main` was
green, and a red branch nobody owns is a thing people stop reading.

The check is the pairing rather than the value. A directory's lockfile says
which manager owns it, and that is a fact on disk rather than a preference, so
a declaration that disagrees with it can be caught without asking anybody.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

CONFIG = Path(".github/dependabot.yml")

#: The lockfile each ecosystem writes, for the ecosystems this repository uses.
#: Only those: a table of every ecosystem Dependabot supports would be a second
#: copy of GitHub's documentation, maintained by nobody and wrong the week it
#: changes.
LOCKFILES: dict[str, str] = {
    "bun": "bun.lock",
    "npm": "package-lock.json",
    "uv": "uv.lock",
}


#: The private working copy carries no `.github` at all — no workflows, no
#: Dependabot, by decision (`ADR-0109`/`ADR-0110`): CI runs in the public tree.
#: This file travels there with everything else and read the config
#: unconditionally, so it had been red in that copy since it was written, in a
#: repository whose gate nobody runs. A declaration that does not exist has no
#: ecosystems to disagree with.
_DECLARED = CONFIG.is_file()


def _updates() -> list[dict[str, Any]]:
    parsed = cast(dict[str, Any], yaml.safe_load(CONFIG.read_text(encoding="utf-8")))
    return cast(list[dict[str, Any]], parsed["updates"])


@pytest.mark.skipif(not _DECLARED, reason="this copy declares no Dependabot updates")
def test_every_declared_ecosystem_matches_the_lockfile_in_its_directory() -> None:
    wrong: list[str] = []
    for update in _updates():
        ecosystem = str(update["package-ecosystem"])
        expected = LOCKFILES.get(ecosystem)
        if expected is None:
            # `github-actions` has no lockfile and no directory contents to
            # check; it is declared here so its absence is a decision.
            continue
        directory = Path(str(update["directory"]).lstrip("/"))
        if not (directory / expected).is_file():
            present = sorted(
                name.name for name in directory.iterdir() if name.name in set(LOCKFILES.values())
            )
            wrong.append(
                f"{directory or '.'} declared {ecosystem}, but holds {present or 'no lockfile'}"
            )
    assert not wrong, wrong


@pytest.mark.skipif(not _DECLARED, reason="this copy declares no Dependabot updates")
def test_the_ecosystems_this_repository_declares_are_ones_the_table_knows() -> None:
    """A new ecosystem must add its lockfile above, or the guard above skips it.

    Without this, declaring one the table has never heard of passes silently —
    the check would `continue` past it exactly as it does for `github-actions`,
    which is the one case where skipping is right.
    """
    known = set(LOCKFILES) | {"github-actions"}
    declared = {str(update["package-ecosystem"]) for update in _updates()}
    assert declared <= known, sorted(declared - known)
