"""A merged Alembic revision keeps its parents (`docs/operations/runbooks/database-migration.md`).

Alembic treats every ancestor of the stamped revision as applied. Re-chaining a
revision a database already passed makes that database skip whatever is
inserted before it: `2b2ea703` did that to `0096_device_session_semantics`, and
production reached `0111` without eleven revisions until
`0112_replay_skipped_feature_chain` replayed them. `migrations/history.lock`
records each revision with its parents; new revisions are appended, recorded
ones never change.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

LOCK = Path("migrations/history.lock")


def _recorded() -> list[tuple[str, tuple[str, ...]]]:
    entries: list[tuple[str, tuple[str, ...]]] = []
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        revision, *parents = line.split()
        entries.append((revision, () if parents == ["-"] else tuple(parents)))
    return entries


def _current() -> dict[str, tuple[str, ...]]:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    current: dict[str, tuple[str, ...]] = {}
    for script in scripts.walk_revisions():
        parent = script.down_revision
        current[script.revision] = (
            () if parent is None else (parent,) if isinstance(parent, str) else tuple(parent)
        )
    return current


def test_recorded_revisions_keep_their_parents() -> None:
    recorded = _recorded()
    assert len({revision for revision, _ in recorded}) == len(recorded), "duplicate lock entry"
    current = _current()
    changed = {
        revision: (parents, current.get(revision))
        for revision, parents in recorded
        if current.get(revision) != parents
    }
    assert not changed, (
        f"recorded revisions changed or disappeared {changed}; a merged revision keeps "
        "its parents — add a forward revision instead"
    )


def test_every_revision_is_recorded() -> None:
    recorded = {revision for revision, _ in _recorded()}
    missing = sorted(set(_current()) - recorded)
    assert not missing, f"append `revision parent...` lines to {LOCK} for {missing}"
