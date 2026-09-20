"""Shared executable lifecycle for catalog `cli` components."""

from __future__ import annotations

import os
import time
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


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell fixture")
def test_a_loud_program_is_bounded_while_it_is_read_not_after_it_exits() -> None:
    """The limit has to bind during capture, or it is not a limit.

    `capture_output=True` keeps everything the child writes and trims afterwards,
    so a program printing without stopping is held whole in this process first.
    The child here writes far past the bound and must still be drained to the
    end: a reader that stops reading blocks it on a full pipe.
    """
    line = "x" * 1023
    count = (cli_program.MAX_INVOKE_OUTPUT // 1024) * 8
    script = f"#!/bin/sh\ni=0\nwhile [ $i -lt {count} ]; do echo '{line}'; i=$((i+1)); done\n"
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="cli",
            harness_id="claude-code",
            payload=script.encode("utf-8"),
            managed_path="bin/loud",
            native_ids=["loud"],
        )
        cli_program.install(connection, stable_id=member[0], version="1.0")
        invoked = cli_program.invoke(connection, stable_id=member[0], version="1.0", arguments=())
    assert invoked.exit_code == 0
    assert len(invoked.output) == cli_program.MAX_INVOKE_OUTPUT


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell fixture")
def test_bytes_that_are_not_text_do_not_fail_the_invocation() -> None:
    """A program is free to write anything; the report stays valid JSON."""
    script = "#!/bin/sh\nprintf '\\377\\376ready'\n"
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="cli",
            harness_id="claude-code",
            payload=script.encode("utf-8"),
            managed_path="bin/binary",
            native_ids=["binary"],
        )
        cli_program.install(connection, stable_id=member[0], version="1.0")
        invoked = cli_program.invoke(connection, stable_id=member[0], version="1.0", arguments=())
    assert invoked.exit_code == 0
    assert invoked.output.endswith("ready")


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_a_program_that_outlives_the_timeout_is_ended_with_its_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A forked child holding the pipe is the same hang by another route.

    The invocation environment has no `PATH`, so the fixture waits with shell
    builtins rather than `sleep`, and records the background process it starts
    so the test can see whether it survived.
    """
    monkeypatch.setattr(cli_program, "INVOKE_TIMEOUT_SECONDS", 0.5)
    script = (
        '#!/bin/sh\nwhile : ; do : ; done &\necho $! > "$HOME/loop.pid"\nwhile : ; do : ; done\n'
    )
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="cli",
            harness_id="claude-code",
            payload=script.encode("utf-8"),
            managed_path="bin/slow",
            native_ids=["slow"],
        )
        cli_program.install(connection, stable_id=member[0], version="1.0")
        with pytest.raises(CliFailure) as raised:
            cli_program.invoke(connection, stable_id=member[0], version="1.0", arguments=())
    assert raised.value.code == "AI_STP_CONFLICT"

    recorded = Path(os.environ["HOME"]) / "loop.pid"
    forked = int(recorded.read_text(encoding="utf-8").strip())
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.kill(forked, 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.05)
    raise AssertionError("the forked child outlived the invocation that started it")


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell fixture")
def test_a_program_receives_the_variables_it_declared_and_nothing_else() -> None:
    """Readiness and execution have to describe the same process.

    `environment inspect` called a declared variable satisfied when it was
    present here, while the program was started with `PATH` and `HOME` alone —
    so the variable it declared could never reach it, and whichever of the two
    answers a caller believed, one was wrong. The bound is the declaration, not
    the ambient environment: an unrelated secret in this process stays here.
    """
    script = '#!/bin/sh\necho "${DEMO_TOKEN:-absent} ${CANARY:-absent} path=[${PATH}]"\n'
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="cli",
            harness_id="claude-code",
            payload=script.encode("utf-8"),
            managed_path="bin/declared-env",
            native_ids=["declared-env"],
            required_env=[{"name": "DEMO_TOKEN", "purpose": "the declared one"}],
        )
        cli_program.install(connection, stable_id=member[0], version="1.0")
        os.environ["DEMO_TOKEN"] = "forwarded"
        os.environ["CANARY"] = "must-not-travel"
        try:
            invoked = cli_program.invoke(
                connection, stable_id=member[0], version="1.0", arguments=()
            )
        finally:
            del os.environ["DEMO_TOKEN"]
            del os.environ["CANARY"]

    assert invoked.exit_code == 0
    assert invoked.output.strip() == "forwarded absent path=[]"


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell fixture")
def test_a_declared_variable_this_process_lacks_is_named_before_the_program_runs() -> None:
    script = "#!/bin/sh\necho ran\n"
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="cli",
            harness_id="claude-code",
            payload=script.encode("utf-8"),
            managed_path="bin/needs-env",
            native_ids=["needs-env"],
            required_env=[{"name": "AI_STP_TEST_ABSENT_TOKEN", "purpose": "never set"}],
        )
        cli_program.install(connection, stable_id=member[0], version="1.0")
        with pytest.raises(CliFailure) as raised:
            cli_program.invoke(connection, stable_id=member[0], version="1.0", arguments=())

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    # The name is what the caller acts on; the value is exactly what must never
    # travel into output.
    assert raised.value.details["variables"] == "AI_STP_TEST_ABSENT_TOKEN"


@pytest.mark.skipif(os.name == "nt", reason="POSIX shebang fixture")
def test_a_shebang_that_resolves_through_path_is_refused_with_the_reason() -> None:
    """`#!/usr/bin/env python3` is an absolute path to a resolver.

    What it resolves is a `PATH` lookup this program deliberately does not get,
    so it would start, fail to find its runtime, and report whatever that looked
    like. Saying so before it runs is the precise answer.
    """
    with closing(open_registry(configured_path(), create=True)) as connection:
        member = _release_component(
            connection,
            component_type="cli",
            harness_id="claude-code",
            payload=b"#!/usr/bin/env python3\nprint('ready')\n",
            managed_path="bin/env-shebang",
            native_ids=["env-shebang"],
        )
        cli_program.install(connection, stable_id=member[0], version="1.0")
        with pytest.raises(CliFailure) as raised:
            cli_program.invoke(connection, stable_id=member[0], version="1.0", arguments=())

    assert raised.value.code == "AI_STP_CONFLICT"
    assert "python3" in str(raised.value.details["interpreter"])
