"""Provider lifecycle: which one is here, which is newest, and replacing it (`#452`)."""

import sqlite3
import stat
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Final

import pytest

from ai_stp_cli import paths
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import provider_installations as installations
from ai_stp_cli.local.database import configured_path, open_registry

MOMENT = "2026-01-01T00:00:00.000Z"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


#: What "runnable" is spelled as on each platform. On POSIX it is a mode bit and
#: the name is free; on Windows it is the name and the mode bit does not exist.
#: Writing the fixtures either way keeps one test body honest on both legs of the
#: matrix instead of two bodies that agree only until one is edited.
_SUFFIX: Final[str] = "" if paths.POSIX else ".exe"


def _executable(place: Path) -> Path:
    place = place.with_name(place.name + _SUFFIX)
    place.parent.mkdir(parents=True, exist_ok=True)
    place.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if paths.POSIX:
        place.chmod(place.stat().st_mode | stat.S_IXUSR)
    return place


# --- version comparison ---------------------------------------------------


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        # The case a lexicographic comparison gets backwards, and the one
        # `#452` names explicitly: compare semantically, not as text.
        ("0.0.10", "0.0.9", True),
        ("0.0.9", "0.0.10", False),
        ("0.0.33", "0.0.33", False),
        ("v0.1.0", "0.0.32", True),
        # A version this cannot parse is never *shown* to be newer. Refusing to
        # claim an update is the honest answer; guessing one is not.
        ("nightly", "0.0.1", False),
        ("0.0.1", "nightly", True),
    ],
)
def test_versions_compare_as_numbers_not_as_text(latest: str, current: str, expected: bool) -> None:
    assert installations.newer(latest, current) is expected


# --- validation -----------------------------------------------------------


def test_a_relative_or_missing_or_linked_provider_path_is_refused(tmp_path: Path) -> None:
    real = _executable(tmp_path / "provider")
    link = tmp_path / "link"
    link.symlink_to(real)

    for path, expected in (
        ("relative/provider", "must be absolute"),
        (str(tmp_path / "absent"), "no provider executable"),
        (str(link), "not a symlink to it"),
    ):
        with pytest.raises(CliFailure, match=expected):
            installations.validated(path, harness_id="codex")

    assert installations.validated(str(real), harness_id="codex") == real


def test_a_file_that_is_not_executable_is_refused(tmp_path: Path) -> None:
    """The refusal has to survive the platform that has no permission bit.

    `os.access(path, X_OK)` answers `True` for every existing file on Windows,
    so a check written as "not executable" once accepted anything that was
    merely there. The fixture is a plain file by *name* as well as by mode, and
    it is refused on both legs for the reason each platform actually has.
    """
    plain = tmp_path / "notes.txt"
    plain.write_text("not runnable\n", encoding="utf-8")
    plain.chmod(0o600)
    with pytest.raises(CliFailure, match="not executable"):
        installations.validated(str(plain), harness_id="codex")


# --- resolution -----------------------------------------------------------


def test_an_argument_beats_the_configuration(registry: sqlite3.Connection, tmp_path: Path) -> None:
    argued = _executable(tmp_path / "argued")
    configured = _executable(tmp_path / "configured")
    found = installations.resolve(
        registry, "codex", argument=str(argued), configured=str(configured)
    )
    assert found.path == str(argued)
    assert found.source == installations.SOURCE_ARGUMENT


def test_a_remembered_discovery_does_not_settle_the_question(
    registry: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read-only report records what it saw; it does not make the choice.

    `provider check` writes a row for what discovery found. Honouring that row
    as a decision meant a machine that later grew a second provider went on
    reporting the first, and the ambiguity never surfaced — the report had
    quietly become the answer it was only supposed to describe.
    """
    root = tmp_path / "providers"
    monkeypatch.setattr(installations, "managed_root", lambda: root)
    first = _executable(root / "codex" / "0.0.32" / "provider")

    installations.remember(
        registry,
        installations.Installation(
            harness_id="codex",
            path=str(first),
            source=installations.SOURCE_DISCOVERED,
            state=installations.STATE_INSTALLED,
            checked_at=MOMENT,
        ),
    )
    assert installations.resolve(registry, "codex").path == str(first)

    _executable(root / "codex" / "0.0.33" / "provider")
    grown = installations.resolve(registry, "codex")
    assert grown.state == installations.STATE_AMBIGUOUS
    assert len(grown.candidates) == 2


def test_a_chosen_provider_settles_it_even_when_a_second_appears(
    registry: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once somebody chose, two installations are no longer a question."""
    root = tmp_path / "providers"
    monkeypatch.setattr(installations, "managed_root", lambda: root)
    chosen = _executable(root / "codex" / "0.0.32" / "provider")
    _executable(root / "codex" / "0.0.33" / "provider")

    installations.remember(
        registry,
        installations.Installation(
            harness_id="codex",
            path=str(chosen),
            source=installations.SOURCE_CHOSEN,
            state=installations.STATE_INSTALLED,
            checked_at=MOMENT,
        ),
    )
    found = installations.resolve(registry, "codex")
    assert found.path == str(chosen)
    # The stored row's own source travels, never the word "registry": that is
    # where the answer was kept, not where it came from, and returning it as a
    # provenance let a discovery be re-recorded as a choice on the next run.
    assert found.source == installations.SOURCE_CHOSEN


def test_a_chosen_path_that_is_gone_says_so(
    registry: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(installations, "managed_root", lambda: tmp_path / "providers")
    installations.remember(
        registry,
        installations.Installation(
            harness_id="codex",
            path=str(tmp_path / "gone"),
            source=installations.SOURCE_CHOSEN,
            state=installations.STATE_INSTALLED,
            checked_at=MOMENT,
        ),
    )
    found = installations.resolve(registry, "codex")
    assert found.state == installations.STATE_MISSING
    assert "gone" in found.reason


def test_forgetting_returns_to_discovery(registry: sqlite3.Connection, tmp_path: Path) -> None:
    installations.remember(
        registry,
        installations.Installation(
            harness_id="codex",
            path=str(_executable(tmp_path / "provider")),
            source=installations.SOURCE_CHOSEN,
            state=installations.STATE_INSTALLED,
            checked_at=MOMENT,
        ),
    )
    assert installations.remembered(registry, "codex") is not None
    assert installations.forget(registry, "codex") is True
    assert installations.remembered(registry, "codex") is None
    assert installations.forget(registry, "codex") is False


def test_one_row_per_harness(registry: sqlite3.Connection, tmp_path: Path) -> None:
    """Two rows would make "which provider runs" a question with two answers."""
    for name in ("first", "second"):
        installations.remember(
            registry,
            installations.Installation(
                harness_id="codex",
                path=str(_executable(tmp_path / name)),
                source=installations.SOURCE_CHOSEN,
                state=installations.STATE_INSTALLED,
                provider_version=name,
                checked_at=MOMENT,
            ),
        )
    held = installations.all_remembered(registry)
    assert len(held) == 1
    assert held[0].provider_version == "second"


# --- configuration --------------------------------------------------------


def test_a_provider_path_is_checked_when_it_is_written(tmp_path: Path) -> None:
    """A value that stores cleanly and fails inside an install is worse than a refusal."""
    from ai_stp_cli.config import set_values

    with pytest.raises(CliFailure, match="must be absolute"):
        set_values({"provider.paths.codex": "relative/provider"})

    real = _executable(tmp_path / "provider")
    set_values({"provider.paths.codex": str(real)})
    # Clearing is always allowed: making a value harder to remove than to set
    # is how a machine gets stuck on a path that no longer exists.
    set_values({"provider.paths.codex": ""})


def test_every_supported_harness_has_a_configurable_path() -> None:
    """One declared field per harness, never a map keyed by whatever is typed."""
    from ai_stp_cli.config import declared_fields
    from ai_stp_foundation.harnesses import HARNESS_IDS

    declared = {field.path for field in declared_fields()}
    assert {f"provider.paths.{harness}" for harness in HARNESS_IDS} <= declared
    assert all(field.is_path for field in declared_fields() if "provider.paths" in field.path)


def test_discovery_ignores_a_symlink_and_a_plain_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "providers"
    monkeypatch.setattr(installations, "managed_root", lambda: root)
    real = _executable(root / "codex" / "0.0.32" / "provider")
    (root / "codex" / "0.0.32" / "linked").symlink_to(real)
    plain = root / "codex" / "0.0.32" / "notes.txt"
    plain.write_text("read me\n", encoding="utf-8")
    assert not paths.is_executable_file(plain)

    assert installations.discover("codex") == (real,)
