"""`--provider` is an override, not a thing every program command must carry.

`provider fetch` installs a provider and records where it put it. Every program
command then required `--provider` anyway, so an agent had to copy a path the
system already held — and a copied path goes stale the moment the provider is
replaced, which is exactly what `provider update` does.

The precedence is `installations.resolve`'s and is not re-decided here: explicit
argument, configuration, the remembered choice, discovery. Ambiguity stays a
refusal, because two providers for one harness is the one case where picking is
deciding.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from ai_stp_cli.commands import harness as harness_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import provider_installations as installations
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.passports import moment

pytestmark = pytest.mark.cli


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    (tmp_path / "data").mkdir()
    (tmp_path / "config").mkdir()
    return tmp_path


def _executable(tmp_path: Path, name: str = "provider") -> Path:
    """A real regular executable file. Never run — only resolved."""
    place = tmp_path / (f"{name}.exe" if sys.platform == "win32" else name)
    shutil.copy2(sys.executable, place)
    return place


def _remember(harness_id: str, place: Path) -> None:
    """Record the choice `provider fetch` would have recorded."""
    registry = configured_path()
    registry.parent.mkdir(parents=True, exist_ok=True)
    with open_registry(registry, create=True) as connection:
        installations.remember(
            connection,
            installations.Installation(
                harness_id=harness_id,
                path=str(place),
                source=installations.SOURCE_ARGUMENT,
                state=installations.STATE_INSTALLED,
                provider_id=f"{harness_id}-setup-system",
                provider_version="0.0.48",
                tag="0.0.48",
                commit="a" * 40,
                checked_at=moment(),
                source_checked_at=moment(),
            ),
        )
        connection.commit()


def test_a_remembered_provider_is_found_without_the_flag(home: Path, tmp_path: Path) -> None:
    """The falsification: omit `--provider` and the recorded one must answer."""
    place = _executable(tmp_path)
    _remember("codex", place)

    with open_registry(configured_path()) as connection:
        found = harness_commands._resolve_provider(  # pyright: ignore[reportPrivateUsage]
            connection, "codex", {}
        )

    assert Path(found) == place.resolve()


def test_an_explicit_path_still_wins(home: Path, tmp_path: Path) -> None:
    """An override that could not override would not be one."""
    _remember("codex", _executable(tmp_path, "remembered"))
    override = _executable(tmp_path, "override")

    with open_registry(configured_path()) as connection:
        found = harness_commands._resolve_provider(  # pyright: ignore[reportPrivateUsage]
            connection, "codex", {"provider": str(override)}
        )

    assert Path(found) == override.resolve()


def test_no_provider_says_how_to_get_one(home: Path) -> None:
    with (
        open_registry(configured_path(), create=True) as connection,
        pytest.raises(CliFailure, match="no provider for this harness") as raised,
    ):
        harness_commands._resolve_provider(  # pyright: ignore[reportPrivateUsage]
            connection, "codex", {}
        )

    assert any("provider fetch" in item for item in raised.value.next_actions)


def test_a_discovered_observation_does_not_become_the_answer(home: Path, tmp_path: Path) -> None:
    """`provider check` records what it saw; seeing is not choosing (`#452`)."""
    place = _executable(tmp_path)
    registry = configured_path()
    registry.parent.mkdir(parents=True, exist_ok=True)
    with open_registry(registry, create=True) as connection:
        installations.remember(
            connection,
            installations.Installation(
                harness_id="codex",
                path=str(place),
                source=installations.SOURCE_DISCOVERED,
                state=installations.STATE_INSTALLED,
                provider_id="codex-setup-system",
                provider_version="0.0.48",
                tag="",
                commit="",
                checked_at=moment(),
                source_checked_at="",
            ),
        )
        connection.commit()

    with (
        open_registry(registry) as connection,
        pytest.raises(CliFailure, match="no provider for this harness"),
    ):
        harness_commands._resolve_provider(  # pyright: ignore[reportPrivateUsage]
            connection, "codex", {}
        )
