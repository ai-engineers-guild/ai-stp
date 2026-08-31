"""A program operation is settled by the prefix, never by a reply or a target.

Two defects met here, and they were the same defect twice. `harness install`
recorded `verified` because the provider's answer carried the word; `harness
resume` recorded it because the provider's *configuration target* reported an
ordinary state. Neither ever read the prefix, which is the operation's subject.

The falsification these tests exist for: build a stopped `software_install`
against an empty prefix and let the provider report perfectly. Nothing may
settle it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_stp_cli.provider import program_state

pytestmark = pytest.mark.cli


def _install(prefix: Path, version: str, *, command: str = "codex", marker: bool = True) -> None:
    """Lay out one installed build the way a released provider does."""
    (prefix / version).mkdir(parents=True)
    (prefix / version / command).write_text("#!/bin/sh\n", encoding="utf-8")
    exposed = prefix / "bin"
    exposed.mkdir(exist_ok=True)
    (exposed / command).write_text("#!/bin/sh\n", encoding="utf-8")
    if marker:
        (exposed / f".{command}.version").write_text(version, encoding="utf-8")


def test_an_empty_prefix_settles_nothing(tmp_path: Path) -> None:
    """The exact case that used to verify from `missing` on a configuration target."""
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    before = program_state.observe(prefix, entry_point="bin/codex")
    after = program_state.observe(prefix, entry_point="bin/codex")

    settlement = program_state.settles(before, after, operation="software_install")

    assert not settlement.met
    assert "entry point" in settlement.reason


@pytest.mark.parametrize("claimed", ["0.9.0", ""])
def test_a_provider_reporting_success_over_an_empty_prefix_is_refused(
    tmp_path: Path, claimed: str
) -> None:
    """Testimony without evidence, with and without a version to check it against."""
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    before = program_state.observe(prefix, entry_point="bin/codex")

    settlement = program_state.settles(
        before,
        program_state.observe(prefix, entry_point="bin/codex"),
        operation="software_install",
        claimed_version=claimed,
    )

    assert not settlement.met


def test_an_install_that_landed_settles(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    before = program_state.observe(prefix, entry_point="bin/codex")
    _install(prefix, "0.9.0")

    settlement = program_state.settles(
        before,
        program_state.observe(prefix, entry_point="bin/codex"),
        operation="software_install",
        claimed_version="0.9.0",
    )

    assert settlement.met
    assert settlement.observed_version == "0.9.0"


def test_a_version_the_provider_named_that_is_not_there_is_refused(tmp_path: Path) -> None:
    """The sandbox-tmpfs case: a perfect answer for files that did not survive."""
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    before = program_state.observe(prefix, entry_point="bin/codex")
    _install(prefix, "0.9.0")

    settlement = program_state.settles(
        before,
        program_state.observe(prefix, entry_point="bin/codex"),
        operation="software_install",
        claimed_version="1.0.0",
    )

    assert not settlement.met
    assert "1.0.0" in settlement.reason


def test_an_exposure_pointing_at_another_build_is_refused(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    _install(prefix, "0.9.0")
    before = program_state.observe(prefix, entry_point="bin/codex")
    (prefix / "1.0.0").mkdir()

    settlement = program_state.settles(
        before,
        program_state.observe(prefix, entry_point="bin/codex"),
        operation="software_install",
        claimed_version="1.0.0",
    )

    assert not settlement.met
    assert "exposes 0.9.0" in settlement.reason


def test_staging_left_behind_owes_recovery(tmp_path: Path) -> None:
    """`.incoming-` exists only between steps, so finding it is finding an unfinished one."""
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    before = program_state.observe(prefix, entry_point="bin/codex")
    _install(prefix, "0.9.0")
    (prefix / ".incoming-1.0.0").mkdir()

    settlement = program_state.settles(
        before,
        program_state.observe(prefix, entry_point="bin/codex"),
        operation="software_install",
        claimed_version="0.9.0",
    )

    assert not settlement.met
    assert settlement.recovery_owed


def test_a_removal_that_left_a_survivor_settles(tmp_path: Path) -> None:
    """Removing an inactive build must not be read from the exposed command."""
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    _install(prefix, "0.9.0")
    (prefix / "0.8.0").mkdir()
    before = program_state.observe(prefix, entry_point="bin/codex")

    (prefix / "0.8.0").rmdir()
    settlement = program_state.settles(
        before,
        program_state.observe(prefix, entry_point="bin/codex"),
        operation="software_remove",
        claimed_version="0.8.0",
    )

    assert settlement.met
    assert settlement.observed_version == "0.9.0"


def test_a_removal_the_provider_reported_that_did_not_happen_is_refused(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    _install(prefix, "0.9.0")
    before = program_state.observe(prefix, entry_point="bin/codex")

    settlement = program_state.settles(
        before,
        program_state.observe(prefix, entry_point="bin/codex"),
        operation="software_remove",
        claimed_version="0.9.0",
    )

    assert not settlement.met


def test_a_plan_recorded_before_prefix_state_refuses_rather_than_guesses(tmp_path: Path) -> None:
    """`None` is not an empty prefix, and treating it as one would settle old rows."""
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    _install(prefix, "0.9.0")

    settlement = program_state.settles(
        None,
        program_state.observe(prefix, entry_point="bin/codex"),
        operation="software_install",
    )

    assert not settlement.met
    assert settlement.reason == program_state.Settlement.UNREADABLE


def test_a_windows_cmd_exposure_finds_its_marker(tmp_path: Path) -> None:
    """Cursor exposes `agent.cmd` and still writes `.agent.version`."""
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    (prefix / "0.9.0").mkdir()
    (prefix / "bin").mkdir()
    (prefix / "bin" / "agent.cmd").write_text("@echo off\n", encoding="utf-8")
    (prefix / "bin" / ".agent.version").write_text("0.9.0", encoding="utf-8")

    observed = program_state.observe(prefix, entry_point="bin/agent.cmd")

    assert observed.exposed == "0.9.0"
    assert observed.entry_point_present


def test_a_marker_naming_a_tree_that_is_not_there_is_not_believed(tmp_path: Path) -> None:
    """A truncated or hand-edited marker must not name a build that does not exist."""
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    _install(prefix, "0.9.0")
    (prefix / "bin" / ".codex.version").write_text("1.2.3", encoding="utf-8")

    assert program_state.observe(prefix, entry_point="bin/codex").exposed == ""


def test_a_reading_round_trips_through_the_durable_plan(tmp_path: Path) -> None:
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    _install(prefix, "0.9.0")
    observed = program_state.observe(prefix, entry_point="bin/codex")

    assert program_state.deserialize(observed.serialize()) == observed
    assert program_state.deserialize("") is None
    assert program_state.deserialize("not json") is None
