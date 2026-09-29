"""An adopted replacement is a decision the registry keeps, bound to bytes.

Measured on a live registry before the fix: `provider update apply --adopt`
verified a release onto a custom path and remembered the row — `chosen`, with
the digest of the exact bytes it wrote — and the very next
`provider update plan` for the same executable refused again with "that
provider was not installed by ai-stp". The premise of that refusal was no
longer true, and the question it re-asked had already been answered and acted
on. `_is_managed` looked only at the fetch store's directory and never at the
journal its own apply had just written.

The rule under test: a path is managed when the registry remembers it as the
chosen installation *and* the file still hashes to the digest that row
recorded. Bound to bytes, not to the path alone — a file someone replaced
afterwards is foreign again, and the adoption question returns exactly when
its premise does.
"""

from __future__ import annotations

import sqlite3
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from ai_stp_cli.commands import provider as provider_commands
from ai_stp_cli.local import provider_installations as installations
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.provider import release

pytestmark = pytest.mark.cli


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sqlite3.Connection]:
    home = tmp_path / "home"
    (home / "data").mkdir(parents=True)
    (home / "config").mkdir(parents=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    connection = open_registry(configured_path(), create=True)
    yield connection
    connection.close()


def _executable(tmp_path: Path, content: bytes) -> Path:
    place = tmp_path / "claude-setup-system"
    place.write_bytes(content)
    place.chmod(place.stat().st_mode | stat.S_IXUSR)
    return place


def _remember(connection: sqlite3.Connection, place: Path, digest: str) -> None:
    installations.remember(
        connection,
        installations.Installation(
            harness_id="claude-code",
            path=str(place),
            source=installations.SOURCE_CHOSEN,
            state=installations.STATE_INSTALLED,
            provider_id="claude-setup-system",
            provider_version="0.0.53",
            artifact_digest=digest,
        ),
    )
    connection.commit()


def test_an_adopted_replacement_is_not_asked_to_be_adopted_again(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    place = _executable(tmp_path, b"#!/bin/sh\nexit 0\n")
    digest, _size = release.artifact_identity(place)
    _remember(registry, place, digest)

    assert provider_commands._is_managed(registry, place) is True, (  # pyright: ignore[reportPrivateUsage]
        "these exact bytes were written by an adopted apply this registry remembers"
    )


def test_a_remembered_path_with_replaced_bytes_is_foreign_again(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    place = _executable(tmp_path, b"#!/bin/sh\nexit 0\n")
    digest, _size = release.artifact_identity(place)
    _remember(registry, place, digest)
    place.write_bytes(b"#!/bin/sh\nexit 1\n")

    assert provider_commands._is_managed(registry, place) is False, (  # pyright: ignore[reportPrivateUsage]
        "someone replaced the file since the adopted apply; the question must come back"
    )


def test_an_unremembered_path_outside_the_store_stays_foreign(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    place = _executable(tmp_path, b"#!/bin/sh\nexit 0\n")

    assert provider_commands._is_managed(registry, place) is False  # pyright: ignore[reportPrivateUsage]


def test_an_in_place_replacement_rewrites_the_sibling_manifest(tmp_path: Path) -> None:
    """`provider check` identifies a managed provider from sibling release.json.

    Replacing only the executable left the old digest in that file, so the
    just-updated provider was reported unmanaged and never asked for a newer
    tag.
    """
    from ai_stp_cli.provider import attested_bind
    from ai_stp_cli.provider.release import ReleaseManifest

    place = _executable(tmp_path, b"new-bytes\n")
    (tmp_path / "release.json").write_text("stale", encoding="utf-8")
    digest, size = release.artifact_identity(place)
    bound = attested_bind.BoundRelease(
        harness_id="claude-code",
        repository="github.com/NDDev-OpenNetwork/claude-setup-system",
        tag="0.0.65",
        commit="a" * 40,
        provider_id="claude-setup-system",
        provider_version="0.0.65",
        protocol_version=3,
        sequence=65,
        artifact=place,
        manifest_path=tmp_path / "staging-release.json",
        artifact_digest=digest,
        artifact_url="https://example.invalid/artifact",
        trust_level="verified_publisher",
        manifest=ReleaseManifest(
            provider_id="claude-setup-system",
            provider_version="0.0.65",
            protocol_version=3,
            repository="github.com/NDDev-OpenNetwork/claude-setup-system",
            commit="a" * 40,
            license="AGPL-3.0-or-later",
            artifact_url="https://example.invalid/artifact",
            artifact_size=size,
            artifact_digest=digest,
            entry_point=place.name,
            supported_os=frozenset({"linux"}),
            supported_arch=frozenset({"x86_64"}),
            sequence=65,
            policy_id="nddev/provider/1",
            publisher="nddev-opennetwork",
            signing_key="attested",
            signature_subject="ai-stp:provider-release-manifest:v1",
            signature="",
        ),
    )
    provider_commands._write_bound_manifest(place, bound)  # pyright: ignore[reportPrivateUsage]
    identity = provider_commands._manifest_identity(place)  # pyright: ignore[reportPrivateUsage]
    assert identity is not None
    assert identity.provider_version == "0.0.65"
    assert identity.provider_id == "claude-setup-system"


def test_a_post_install_failure_restores_bytes_manifest_and_registry(
    registry: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The replacement is one write: a failure after the rename must not leave
    new bytes beside an old manifest and no registry row.
    """
    from ai_stp_cli.provider import attested_bind
    from ai_stp_cli.provider.release import ReleaseManifest

    place = _executable(tmp_path, b"old-bytes\n")
    (tmp_path / "release.json").write_text("old-release", encoding="utf-8")
    old_digest, old_size = release.artifact_identity(place)

    fetch_dir = tmp_path / "fetch"
    fetch_dir.mkdir()
    fetched = _executable(fetch_dir, b"new-bytes\n")
    new_digest, new_size = release.artifact_identity(fetched)
    bound = attested_bind.BoundRelease(
        harness_id="claude-code",
        repository="github.com/NDDev-OpenNetwork/claude-setup-system",
        tag="0.0.66",
        commit="b" * 40,
        provider_id="claude-setup-system",
        provider_version="0.0.66",
        protocol_version=3,
        sequence=66,
        artifact=fetched,
        manifest_path=fetch_dir / "release.json",
        artifact_digest=new_digest,
        artifact_url="https://example.invalid/artifact",
        trust_level="verified_publisher",
        manifest=ReleaseManifest(
            provider_id="claude-setup-system",
            provider_version="0.0.66",
            protocol_version=3,
            repository="github.com/NDDev-OpenNetwork/claude-setup-system",
            commit="b" * 40,
            license="AGPL-3.0-or-later",
            artifact_url="https://example.invalid/artifact",
            artifact_size=new_size,
            artifact_digest=new_digest,
            entry_point=fetched.name,
            supported_os=frozenset({"linux"}),
            supported_arch=frozenset({"x86_64"}),
            sequence=66,
            policy_id="nddev/provider/1",
            publisher="nddev-opennetwork",
            signing_key="attested",
            signature_subject="ai-stp:provider-release-manifest:v1",
            signature="",
        ),
    )
    current = provider_commands.Identity("0.0.53", old_digest)
    assert old_size > 0
    plan_answer = provider_commands._planned_or_applied(  # pyright: ignore[reportPrivateUsage]
        registry,
        bound=bound,
        operation="update",
        harness_id="claude-code",
        target=place,
        current=current,
        foreign=False,
        confirmed=False,
        expected="",
    )
    expected = plan_answer.payload.plan_digest

    def fail_remember(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("registry write failed")

    monkeypatch.setattr(installations, "remember", fail_remember)
    with pytest.raises(RuntimeError, match="registry write failed"):
        provider_commands._planned_or_applied(  # pyright: ignore[reportPrivateUsage]
            registry,
            bound=bound,
            operation="update",
            harness_id="claude-code",
            target=place,
            current=current,
            foreign=False,
            confirmed=True,
            expected=expected,
        )

    # Exact prior state: old bytes, the manifest that described them, and no
    # registry row pointing at either.
    assert release.artifact_identity(place)[0] == old_digest
    assert (tmp_path / "release.json").read_text(encoding="utf-8") == "old-release"
    assert installations.remembered(registry, "claude-code") is None
