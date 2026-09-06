"""Shared executable lifecycle for catalog `cli` components."""

from __future__ import annotations

import os
from contextlib import closing

from tests.unit.test_cli_setup_recast import (
    _release_component,  # pyright: ignore[reportPrivateUsage]
)

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
