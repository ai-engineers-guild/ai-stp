"""Replacement reads exact filesystem identity without executing unknown bytes."""

from pathlib import Path

import pytest

from ai_stp_cli.commands import provider as provider_commands
from ai_stp_cli.provider import release

pytestmark = pytest.mark.cli


def test_replacement_identity_does_not_execute_an_unmatched_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.provider import attested_bind

    executable = tmp_path / "unmatched-provider"
    executable.write_bytes(b"untrusted executable bytes")

    def must_not_run(_path: Path) -> object:
        raise AssertionError("replacement inspection must not execute unverified bytes")

    monkeypatch.setattr(attested_bind, "inspect_provider", must_not_run)
    identity = provider_commands._identity(executable)  # pyright: ignore[reportPrivateUsage]
    assert identity.version == ""
    assert identity.digest == release.artifact_identity(executable)[0]
