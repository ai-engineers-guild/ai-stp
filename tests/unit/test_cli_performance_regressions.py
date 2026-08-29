"""Structural guards for the two costs `#453` measured and removed.

Both are written as properties rather than as durations wherever a property
will do. A budget in seconds fails on a loaded runner and passes on a fast one
that regressed, which makes it a check nobody can trust the third time it goes
red — and one nobody runs protects nothing.

The one timing assertion here is unavoidable, because "these run concurrently"
is a statement about time. It is given a margin no plausible machine crosses:
seven detections of a tenth of a second each are 0.7s in series, and the bound
is 0.35s.
"""

import hashlib
import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from ai_stp_cli.commands import select
from ai_stp_cli.local import harnesses, project_index
from ai_stp_cli.local.database import configured_path, open_registry

#: How long each stubbed detection pretends its subprocess takes.
DELAY = 0.1


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


def test_every_harness_is_asked_its_version_at_the_same_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seven independent subprocesses, not seven waits one after another.

    Measured before the fix: 1.688s in series against 0.700s together, the
    latter bound by the slowest single program rather than by their sum.
    `cursor` and `opencode` take about 0.62s each to answer `--version`;
    `claude-code` and `codex` take nine milliseconds. The slow ones are
    somebody else's program booting, and nothing here can make them faster —
    only stop them queueing behind each other.
    """

    def slow(detector: Any, **_kwargs: Any) -> Any:
        time.sleep(DELAY)
        return harnesses.Found(
            harness_id=detector.harness_id,
            title=detector.harness_id,
            support="supported",
            state="available",
            installations=(),
            configuration=None,
            reason="stubbed",
        )

    monkeypatch.setattr(harnesses, "detect", slow)
    started = time.perf_counter()
    found = harnesses.detect_all()
    elapsed = time.perf_counter() - started

    serial = DELAY * len(harnesses.DETECTORS)
    assert elapsed < serial / 2, f"{elapsed:.3f}s of a {serial:.3f}s serial cost"
    # Concurrency must not reorder the answer: `map` yields in input order, and
    # a set of harnesses that arrives in completion order would make the output
    # depend on which program booted first.
    assert [item.harness_id for item in found] == [
        detector.harness_id for detector in harnesses.DETECTORS
    ]


def test_an_index_without_digests_says_so_rather_than_looking_truncated(
    tmp_path: Path,
) -> None:
    """`digest is None` must not have to mean two things at once.

    It already meant "too large to read". Letting it also mean "no hash was
    asked for" would leave a reader unable to tell an unread file from an
    unhashed one, so the index states which it is.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# b\n", encoding="utf-8")

    full = project_index.build(tmp_path)
    assert full.digested
    assert all(item.digest for item in full.entries)

    plain = project_index.build(tmp_path, digests=False)
    assert not plain.digested
    assert all(item.digest is None for item in plain.entries)
    # Everything the inventory is for is unchanged: the same files, the same
    # languages, the same sizes. Only the hash is absent.
    assert [(i.path, i.language, i.size_bytes) for i in plain.entries] == [
        (i.path, i.language, i.size_bytes) for i in full.entries
    ]


def test_assessing_eligibility_hashes_no_project_file(
    registry: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command reads names, languages and `.git`, so it should hash nothing.

    Hashing was three quarters of its walk — 0.91s against 0.29s to read the
    same 4080 files — and no digest reached the answer. This asserts the
    absence directly rather than a duration, because the duration is a
    consequence of it and the absence is the thing that must not come back.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.go").write_text("package main\n", encoding="utf-8")

    hashed = 0
    real = hashlib.sha256

    def counted(*args: Any, **kwargs: Any) -> Any:
        nonlocal hashed
        hashed += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(hashlib, "sha256", counted)
    target = select._target(  # pyright: ignore[reportPrivateUsage]
        "claude-code", tmp_path, for_redistribution=False, owner_id="account_01J" + "0" * 20 + "FAR"
    )
    assert hashed == 0
    # And the languages still arrive — this is the capability set the engine
    # refuses components on, so an empty one would pass this test for the
    # wrong reason.
    assert "project.language.python" in target.capabilities
    assert "project.language.go" in target.capabilities
