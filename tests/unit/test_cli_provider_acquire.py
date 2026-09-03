"""Missing managed providers are acquired through attested GitHub releases."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_stp_cli.commands import harness as harness_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import provider_installations as installations
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.passports import moment
from ai_stp_cli.provider import acquire

pytestmark = pytest.mark.cli


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    (tmp_path / "data").mkdir()
    (tmp_path / "config").mkdir()
    return tmp_path


def _executable(tmp_path: Path, name: str = "provider") -> Path:
    place = tmp_path / (f"{name}.exe" if sys.platform == "win32" else name)
    place.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sys.executable, place)
    return place


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, fetch: object) -> None:
    monkeypatch.setattr("ai_stp_cli.provider.acquire.attested_bind.fetch", fetch)


def _bound(place: Path) -> SimpleNamespace:
    return SimpleNamespace(
        harness_id="codex",
        artifact=place,
        provider_id="codex-setup-system",
        provider_version="0.0.60",
        tag="0.0.60",
        commit="a" * 40,
        artifact_digest="sha256:" + "b" * 64,
    )


def test_a_missing_provider_is_acquired_and_remembered(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched = _executable(tmp_path, "fetched")

    def fetch(**_kwargs: object) -> SimpleNamespace:
        return _bound(fetched)

    _patch_fetch(monkeypatch, fetch)

    with open_registry(configured_path(), create=True) as connection:
        found = acquire.ensure_provider(connection, "codex", {})
        remembered = installations.remembered(connection, "codex")

    assert Path(found) == fetched.resolve()
    assert remembered is not None
    assert remembered.source == installations.SOURCE_CHOSEN
    assert remembered.path == str(fetched)


def test_an_explicit_path_is_not_fetched(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = _executable(tmp_path, "named")

    def boom(**_k: object) -> None:
        raise AssertionError("explicit provider must not fetch")

    _patch_fetch(monkeypatch, boom)
    with open_registry(configured_path(), create=True) as connection:
        found = acquire.ensure_provider(connection, "codex", {"provider": str(named)})
    assert Path(found) == named.resolve()


def test_ambiguity_is_not_fetched(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = installations.managed_root() / "codex"
    _executable(root / "0.0.32", "provider")
    _executable(root / "0.0.33", "provider")

    def boom(**_k: object) -> None:
        raise AssertionError("ambiguous providers must not fetch")

    _patch_fetch(monkeypatch, boom)
    with (
        open_registry(configured_path(), create=True) as connection,
        pytest.raises(CliFailure, match="more than one provider") as raised,
    ):
        acquire.ensure_provider(connection, "codex", {})
    assert raised.value.code == "AI_STP_USER_DECISION_REQUIRED"
    assert any("provider fetch" in item for item in raised.value.next_actions)


def test_unverified_without_a_path_is_not_fetched(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(**_k: object) -> None:
        raise AssertionError("unverified acquisition must not fetch")

    _patch_fetch(monkeypatch, boom)
    with (
        open_registry(configured_path(), create=True) as connection,
        pytest.raises(CliFailure, match="unverified provider must be named") as raised,
    ):
        acquire.ensure_provider(connection, "codex", {"unverified-provider": True})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_a_failed_acquisition_names_provider_fetch(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**_k: object) -> None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the GitHub release does not contain this platform artifact",
            next_actions=["provider fetch --harness codex --json"],
        )

    _patch_fetch(monkeypatch, fail)
    with (
        open_registry(configured_path(), create=True) as connection,
        pytest.raises(CliFailure) as raised,
    ):
        acquire.ensure_provider(connection, "codex", {})
    assert any("provider fetch" in item for item in raised.value.next_actions)


def test_harness_resolution_acquires_when_missing(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched = _executable(tmp_path, "fetched")

    def fetch(**_kwargs: object) -> SimpleNamespace:
        return _bound(fetched)

    _patch_fetch(monkeypatch, fetch)
    with open_registry(configured_path(), create=True) as connection:
        found = harness_commands._resolve_provider(  # pyright: ignore[reportPrivateUsage]
            connection, "codex", {}
        )
    assert Path(found) == fetched.resolve()


def test_a_discovered_observation_is_not_the_acquired_provider(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _executable(tmp_path, "observed")
    fetched = _executable(tmp_path, "fetched")
    registry = configured_path()
    registry.parent.mkdir(parents=True, exist_ok=True)
    with open_registry(registry, create=True) as connection:
        installations.remember(
            connection,
            installations.Installation(
                harness_id="codex",
                path=str(observed),
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

    def fetch(**_kwargs: object) -> SimpleNamespace:
        return _bound(fetched)

    _patch_fetch(monkeypatch, fetch)
    with open_registry(registry) as connection:
        found = harness_commands._resolve_provider(  # pyright: ignore[reportPrivateUsage]
            connection, "codex", {}
        )
    assert Path(found) == fetched.resolve()
    assert Path(found) != observed.resolve()
