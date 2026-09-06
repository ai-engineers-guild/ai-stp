"""Installed program identity follows bytes and version paths, not registry order."""

from __future__ import annotations

import io
import os
import sqlite3
import stat
import zipfile
from contextlib import closing
from pathlib import Path
from typing import cast

import pytest
from tests.unit.test_cli_setup_recast import (
    CREATED,
    DEVICE,
    _release_component,  # pyright: ignore[reportPrivateUsage]
)

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, cli_program, revisions, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_foundation.canonical import JsonValue

SCRIPT = b"#!/bin/sh\nprintf 'ready\\n'\n"


def _component(connection: sqlite3.Connection, payload: bytes = SCRIPT) -> str:
    return _release_component(
        connection,
        component_type="cli",
        harness_id="claude-code",
        payload=payload,
        managed_path="bin/ready",
        native_ids=["ready"],
    )[0]


def _next_version(connection: sqlite3.Connection, stable_id: str) -> None:
    previous = versions.held(connection, stable_id, "1.0")
    assert previous is not None
    held = revisions.get(connection, previous.revision_id)
    assert held is not None
    body = cast(
        dict[str, JsonValue], held.envelope.model_dump(mode="json", exclude={"revision_id"})
    )
    body["version"] = "1.1"
    stored = revisions.store_snapshot(connection, body, device_id=DEVICE)
    versions.record(
        connection,
        stable_id=stable_id,
        version="1.1",
        passport_digest=cache.digest_of(cast(JsonValue, stored.envelope.model_dump(mode="json"))),
        revision_id=stored.revision_id,
        at=CREATED,
    )


def test_status_reports_the_installed_version_not_the_newest_registry_version() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _component(connection)
        cli_program.install(connection, stable_id=stable_id, version="1.0")
        _next_version(connection, stable_id)
        result = cli_program.status(connection, stable_id=stable_id)
        assert result.state == "present"
        assert result.version == "1.0"


def test_explicit_uninstalled_version_cannot_invoke_a_different_current_program() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _component(connection)
        cli_program.install(connection, stable_id=stable_id, version="1.0")
        _next_version(connection, stable_id)
        with pytest.raises(CliFailure) as raised:
            cli_program.invoke(connection, stable_id=stable_id, version="1.1", arguments=())
        assert raised.value.code == "AI_STP_NOT_FOUND"


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX shell invocation; Windows needs a native fixture"
)
def test_explicit_and_implicit_invocation_select_the_actual_program() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _component(connection)
        cli_program.install(connection, stable_id=stable_id, version="1.0")
        _next_version(connection, stable_id)
        current = cli_program.invoke(connection, stable_id=stable_id, version=None, arguments=())
        assert current.version == "1.0"
        cli_program.install(connection, stable_id=stable_id, version="1.1")
        explicit = cli_program.invoke(connection, stable_id=stable_id, version="1.0", arguments=())
        assert explicit.version == "1.0"
        assert Path(explicit.executable).parent.name == "1.0"
        assert explicit.exit_code == 0
        assert explicit.output == "ready\n"
        assert cli_program.status(connection, stable_id=stable_id).version == "1.1"


@pytest.mark.parametrize("operation", ["status", "invoke"])
def test_modified_installed_bytes_are_not_reported_present_or_executed(operation: str) -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _component(connection)
        cli_program.install(connection, stable_id=stable_id, version="1.0")
        executable = cli_program.prefix() / stable_id / "1.0" / "program"
        executable.write_bytes(b"#!/bin/sh\necho unexpected\n")
        with pytest.raises(CliFailure) as raised:
            if operation == "status":
                cli_program.status(connection, stable_id=stable_id)
            else:
                cli_program.invoke(connection, stable_id=stable_id, version=None, arguments=())
        assert raised.value.code == "AI_STP_CONFLICT"


def _redirect(pointer: Path, target: Path) -> None:
    pointer.unlink()
    if os.name == "nt":
        pointer.write_text(f"path:{target}", encoding="utf-8")
    else:
        pointer.symlink_to(target)


@pytest.mark.parametrize("operation", ["status", "invoke"])
def test_current_pointer_cannot_select_another_component(operation: str) -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        first = _component(connection)
        other = _component(connection)
        cli_program.install(connection, stable_id=first, version="1.0")
        cli_program.install(connection, stable_id=other, version="1.0")
        _redirect(
            cli_program.prefix() / first / "current",
            cli_program.prefix() / other / "1.0" / "program",
        )
        with pytest.raises(CliFailure) as raised:
            if operation == "status":
                cli_program.status(connection, stable_id=first)
            else:
                cli_program.invoke(connection, stable_id=first, version=None, arguments=())
        assert raised.value.code == "AI_STP_CONFLICT"


@pytest.mark.parametrize("level", ["component", "version", "program"])
def test_install_refuses_linked_destinations_and_keeps_outside_bytes(
    tmp_path: Path, level: str
) -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _component(connection)
        outside = tmp_path / "outside"
        outside.mkdir()
        marker = outside / "program"
        marker.write_bytes(b"outside must not be overwritten")
        component = cli_program.prefix() / stable_id
        linked = component if level == "component" else component / "1.0"
        if level == "program":
            linked = linked / "program"
        linked.parent.mkdir(parents=True, exist_ok=True)
        linked.symlink_to(
            marker if level == "program" else outside, target_is_directory=level != "program"
        )
        with pytest.raises(CliFailure) as raised:
            cli_program.install(connection, stable_id=stable_id, version="1.0")
        assert raised.value.code == "AI_STP_CONFLICT"
        assert marker.read_bytes() == b"outside must not be overwritten"


def test_install_keeps_the_other_name_of_a_hardlinked_inode(tmp_path: Path) -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _component(connection)
        outside = tmp_path / "keep"
        outside.write_bytes(b"unchanged")
        executable = cli_program.prefix() / stable_id / "1.0" / "program"
        executable.parent.mkdir(parents=True)
        executable.hardlink_to(outside)
        cli_program.install(connection, stable_id=stable_id, version="1.0")
        assert outside.read_bytes() == b"unchanged"
        assert executable.read_bytes() == SCRIPT


def _archive(kind: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        if kind == "empty":
            archive.writestr("empty/", b"")
        elif kind == "multiple":
            archive.writestr("first", SCRIPT)
            archive.writestr("second", SCRIPT)
        elif kind == "symlink":
            member = zipfile.ZipInfo("program")
            member.create_system = 3
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(member, b"/outside")
        else:
            archive.writestr("program", SCRIPT)
    return buffer.getvalue()


@pytest.mark.parametrize("kind", ["empty", "multiple", "symlink", "corrupt"])
def test_ambiguous_or_invalid_archives_are_refused_before_install(kind: str) -> None:
    payload = b"PKbroken" if kind == "corrupt" else _archive(kind)
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _component(connection, payload)
        with pytest.raises(CliFailure) as raised:
            cli_program.install(connection, stable_id=stable_id, version="1.0")
        assert raised.value.code == "AI_STP_CONFLICT"
        assert not (cli_program.prefix() / stable_id).exists()


def test_single_program_archive_is_a_valid_install_input() -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        stable_id = _component(connection, _archive("single"))
        result = cli_program.install(connection, stable_id=stable_id, version="1.0")
        assert result.state == "present"
        assert (cli_program.prefix() / stable_id / "1.0" / "program").read_bytes() == SCRIPT
