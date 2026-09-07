"""Shared executable lifecycle for catalog `cli` components."""

from __future__ import annotations

import os
from contextlib import closing
from pathlib import Path

import pytest
from tests.unit.test_cli_setup_recast import (
    _release_component,  # pyright: ignore[reportPrivateUsage]
)

from ai_stp_cli.commands import cli_program as command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cli_program, composition
from ai_stp_cli.local.database import configured_path, open_registry


def test_a_required_cli_member_does_not_lose_a_native_surface() -> None:
    report = composition.compose(
        (
            composition.Surface(
                stable_id="component_cli",
                version="1.0",
                component_type="cli",
                harness_id="claude-code",
                required=True,
            ),
        ),
        composition.Target(harness_id="claude-code", os="linux", arch="x86_64"),
    )
    assert not any(item.code == "native_surface_lost" for item in report.conflicts)
    converted = composition.convert(
        (
            composition.Surface(
                stable_id="component_cli",
                version="1.0",
                component_type="cli",
                harness_id="claude-code",
            ),
        ),
        composition.Target(harness_id="codex", os="linux", arch="x86_64"),
    )
    assert converted.entries[0].state == composition.STATE_COMPLETE
    assert converted.entries[0].native_surface == "bin"


def test_cli_program_install_status_invoke_and_remove() -> None:
    script = b"#!/bin/sh\necho ready\n"
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="cli",
            harness_id="claude-code",
            payload=script,
            managed_path="bin/ready",
            native_ids=["ready"],
        )
        installed = cli_program.install(connection, stable_id=member[0], version="1.0")
        assert installed.state == "present"
        standing = cli_program.status(connection, stable_id=member[0])
        assert standing.state == "present"
        if os.name != "nt":
            invoked = cli_program.invoke(
                connection, stable_id=member[0], version="1.0", arguments=()
            )
            assert invoked.exit_code == 0
            assert "ready" in invoked.output
        removed = cli_program.remove(stable_id=member[0])
        assert removed.state == "removed"
        gone = cli_program.status(connection, stable_id=member[0])
        assert gone.state == "never_installed"


def _victim_outside_prefix() -> tuple[Path, Path, str]:
    """A directory that `prefix() / id` can reach only by leaving the prefix."""
    root = cli_program.prefix()
    root.mkdir(parents=True, exist_ok=True)
    victim = root.parent.parent / "outside-cli-program"
    victim.mkdir(parents=True)
    marker = victim / "keep"
    marker.write_text("safe", encoding="utf-8")
    return victim, marker, os.path.relpath(victim, start=root)


def test_program_remove_refuses_a_path_id_and_does_not_delete_outside_the_prefix() -> None:
    """`--id` is a typed component id. A relative path must not be a delete root."""
    victim, marker, relative = _victim_outside_prefix()
    with pytest.raises(CliFailure) as raised:
        command.remove({"id": relative, "confirm": True})
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8") == "safe"
    assert victim.is_dir()


def test_program_remove_unlinks_an_escaping_symlink_without_following_it() -> None:
    """A symlink under the prefix is ours to unlink; its target is not."""
    script = b"#!/bin/sh\necho ready\n"
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="cli",
            harness_id="claude-code",
            payload=script,
            managed_path="bin/ready",
            native_ids=["ready"],
        )
        installed = cli_program.install(connection, stable_id=member[0], version="1.0")
        assert installed.state == "present"
        program_root = cli_program.prefix() / member[0]
        victim, marker, _relative = _victim_outside_prefix()
        for child in sorted(program_root.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        program_root.rmdir()
        program_root.symlink_to(victim)
        removed = command.remove({"id": member[0], "confirm": True})
    assert removed.payload.state == "removed"
    assert not program_root.exists()
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8") == "safe"
    assert victim.is_dir()
