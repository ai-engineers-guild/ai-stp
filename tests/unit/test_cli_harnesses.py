"""Harness detection: a declared set, no search, and nothing written."""

import hashlib
import os
import stat
from pathlib import Path

import pytest

from ai_stp_cli.local import harnesses
from ai_stp_foundation.harnesses import SUPPORT_TIERS

SUPPORTED = {"claude-code", "codex", "pi", "opencode", "grok-build"}


def _fake(directory: Path, name: str, *, answer: str = "9.9.9", code: int = 0) -> Path:
    """A stand-in executable that answers a version query."""
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        place = directory / f"{name}.cmd"
        output = f"echo {answer}\n" if answer else ""
        place.write_text(f"@echo off\n{output}exit /b {code}\n", encoding="utf-8")
    else:
        place = directory / name
        place.write_text(f'#!/bin/sh\necho "{answer}"\nexit {code}\n', encoding="utf-8")
        place.chmod(place.stat().st_mode | stat.S_IXUSR)
    return place


def _snapshot(root: Path) -> dict[str, str]:
    taken: dict[str, str] = {}
    for item in sorted(root.rglob("*")):
        if item.is_file():
            taken[str(item)] = hashlib.sha256(item.read_bytes()).hexdigest()
        else:
            taken[str(item)] = "dir"
    return taken


def test_every_supported_harness_has_a_declared_detector() -> None:
    # `REQ-1414`: the supported set is the point, and detection outside it is
    # not a thing this can do — there is no search, only this table.
    assert {item.harness_id for item in harnesses.DETECTORS} == SUPPORTED
    for detector in harnesses.DETECTORS:
        assert detector.executable
        assert detector.version_arguments
        assert detector.config_root
        assert detector.support in {"primary", "beta"}
        # Where the path was established. These change upstream, and a future
        # reader needs to know what to re-check rather than guess.
        assert detector.source


def test_the_primary_harnesses_are_the_ones_the_specification_names() -> None:
    """The set is owned by `SPEC-033` `REQ-3315`, not by this test.

    It used to be `claude-code` and `codex`. `grok-build` joined them as a
    product decision, which is what a support *tier* is: `REQ-3306` says
    evidence never raises a tier, and whether an end-to-end run has been
    recorded is answered separately by support state.

    Read from the owner rather than restated, so this file cannot become the
    place where the set silently disagrees with the specification.
    """
    primary = {item.harness_id for item in harnesses.DETECTORS if item.support == "primary"}
    assert primary == {name for name, tier in SUPPORT_TIERS.items() if tier == "primary"}
    assert primary == {"claude-code", "codex", "grok-build"}


def test_present_installations_exclude_supported_but_absent_harnesses(tmp_path: Path) -> None:
    environment = {"PATH": str(tmp_path / "empty"), "HOME": str(tmp_path / "home")}
    found = harnesses.detect_all(environment)
    assert all(item.state == "available" for item in found)
    assert harnesses.present_installations(found) == ()
    pi = next(item for item in found if item.harness_id == "pi")
    assert pi.state == "available"
    assert pi.installations == ()


def test_windows_exe_is_a_cli_surface(tmp_path: Path) -> None:
    detector = next(item for item in harnesses.DETECTORS if item.harness_id == "claude-code")
    executable = tmp_path / "bin" / "claude.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"not a real binary")
    found = harnesses.detect(detector, explicit=executable, system_name="Windows")
    assert found.state in {"installed", "unknown_version"}
    assert found.installations[0].surface == "cli"


def test_a_harness_that_is_not_installed_is_available_rather_than_absent(
    tmp_path: Path,
) -> None:
    # `REQ-1415`. Absent from the answer would be indistinguishable from
    # unsupported, which is a different thing entirely.
    environment = {"PATH": str(tmp_path / "empty"), "HOME": str(tmp_path / "home")}
    found = harnesses.detect(harnesses.DETECTORS[0], environment=environment)
    assert found.state == "available"
    assert found.installations == ()
    assert found.reason


def test_an_installed_harness_reports_its_path_version_and_reason(tmp_path: Path) -> None:
    binaries = tmp_path / "bin"
    fake = _fake(binaries, "claude", answer="2.1.223 (Claude Code)")
    environment = {"PATH": str(binaries), "HOME": str(tmp_path / "home")}

    found = harnesses.detect(harnesses.DETECTORS[0], environment=environment)
    assert found.state == "installed"
    assert found.installations[0].path.casefold() == str(fake).casefold()
    assert found.installations[0].version == "2.1.223 (Claude Code)"
    assert found.installations[0].reason
    assert found.configuration is None


def test_a_configured_harness_is_distinguished_from_a_merely_installed_one(
    tmp_path: Path,
) -> None:
    binaries = tmp_path / "bin"
    _fake(binaries, "claude")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    environment = {"PATH": str(binaries), "HOME": str(home)}

    found = harnesses.detect(harnesses.DETECTORS[0], environment=environment)
    assert found.state == "configured"
    assert found.configuration == str(home / ".claude")


def test_a_harness_that_will_not_say_its_version_is_unknown_not_guessed(
    tmp_path: Path,
) -> None:
    # `REQ-1415` allows the word `unknown`. It does not allow an invented number,
    # and a passport is what later decisions are made from.
    binaries = tmp_path / "bin"
    _fake(binaries, "claude", answer="", code=3)
    environment = {"PATH": str(binaries), "HOME": str(tmp_path / "home")}

    found = harnesses.detect(harnesses.DETECTORS[0], environment=environment)
    assert found.state == "unknown_version"
    assert found.installations[0].version == "unknown"
    assert "exited 3" in found.reason
    assert found.installations[0].version_source == "unavailable"
    assert found.installations[0].diagnostic == "version_query_exit"


def test_a_harness_that_answers_with_nothing_is_also_unknown(tmp_path: Path) -> None:
    binaries = tmp_path / "bin"
    _fake(binaries, "claude", answer="")
    environment = {"PATH": str(binaries), "HOME": str(tmp_path / "home")}
    found = harnesses.detect(harnesses.DETECTORS[0], environment=environment)
    assert found.installations[0].version == "unknown"
    assert "nothing" in found.reason


def test_a_version_query_that_cannot_run_is_a_reason_not_a_crash(tmp_path: Path) -> None:
    missing = tmp_path / "bin" / "claude"
    version, reason = harnesses.ask_version(missing, ("--version",))
    assert version == "unknown"
    assert "failed" in reason


def test_every_installation_is_listed_not_just_the_first(tmp_path: Path) -> None:
    # `REQ-1417`: two versions of one harness on one machine is ordinary, and
    # reporting one hides the other.
    first = tmp_path / "one"
    second = tmp_path / "two"
    _fake(first, "claude", answer="1.0.0")
    _fake(second, "claude", answer="2.0.0")
    environment = {
        "PATH": os.pathsep.join([str(first), str(second)]),
        "HOME": str(tmp_path / "home"),
    }

    found = harnesses.detect(harnesses.DETECTORS[0], environment=environment)
    assert [item.version for item in found.installations] == ["1.0.0", "2.0.0"]


def test_the_same_binary_reached_twice_is_one_installation(tmp_path: Path) -> None:
    real = tmp_path / "real"
    _fake(real, "claude", answer="1.0.0")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    environment = {
        "PATH": os.pathsep.join([str(real), str(alias)]),
        "HOME": str(tmp_path / "home"),
    }
    found = harnesses.detect(harnesses.DETECTORS[0], environment=environment)
    assert len(found.installations) == 1


def test_an_explicit_path_beats_what_the_search_path_offers(tmp_path: Path) -> None:
    # `REQ-1417`: the user naming a binary is a stronger statement than the
    # order of a search path they may not control.
    on_path = tmp_path / "bin"
    _fake(on_path, "claude", answer="1.0.0")
    chosen = _fake(tmp_path / "chosen", "claude", answer="7.7.7")
    environment = {"PATH": str(on_path), "HOME": str(tmp_path / "home")}

    found = harnesses.detect(harnesses.DETECTORS[0], environment=environment, explicit=chosen)
    assert [item.version for item in found.installations] == ["7.7.7"]


@pytest.mark.parametrize(
    ("harness_id", "expected_suffix"),
    [
        ("claude-code", ".claude"),
        ("codex", ".codex"),
        ("pi", ".pi/agent"),
        ("grok-build", ".grok"),
    ],
)
def test_each_harness_keeps_configuration_where_its_own_documentation_says(
    harness_id: str, expected_suffix: str, tmp_path: Path
) -> None:
    # The five disagree with each other. Assuming one convention would have
    # produced four confident wrong answers.
    detector = next(item for item in harnesses.DETECTORS if item.harness_id == harness_id)
    root = harnesses.config_root(detector, {"HOME": str(tmp_path)})
    assert root == tmp_path / expected_suffix


def test_opencode_follows_xdg_rather_than_the_home_directory(tmp_path: Path) -> None:
    detector = next(item for item in harnesses.DETECTORS if item.harness_id == "opencode")
    assert harnesses.config_root(detector, {"HOME": str(tmp_path)}) == (
        tmp_path / ".config" / "opencode"
    )
    elsewhere = tmp_path / "xdg"
    assert harnesses.config_root(
        detector, {"HOME": str(tmp_path), "XDG_CONFIG_HOME": str(elsewhere)}
    ) == (elsewhere / "opencode")


@pytest.mark.parametrize(
    ("harness_id", "variable"),
    [
        ("codex", "CODEX_HOME"),
        ("pi", "PI_CODING_AGENT_DIR"),
        ("opencode", "OPENCODE_CONFIG_DIR"),
        ("grok-build", "GROK_HOME"),
    ],
)
def test_an_override_wins_because_that_is_what_it_is_for(
    harness_id: str, variable: str, tmp_path: Path
) -> None:
    detector = next(item for item in harnesses.DETECTORS if item.harness_id == harness_id)
    moved = tmp_path / "moved"
    root = harnesses.config_root(detector, {"HOME": str(tmp_path), variable: str(moved)})
    assert root == moved


def test_detection_changes_nothing_on_the_filesystem(tmp_path: Path) -> None:
    # `REQ-1416`. Obtained by never opening a file for writing rather than by
    # remembering not to.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    binaries = tmp_path / "bin"
    _fake(binaries, "claude")
    environment = {"PATH": str(binaries), "HOME": str(home)}

    before = _snapshot(tmp_path)
    harnesses.detect_all(environment)
    assert _snapshot(tmp_path) == before


def test_the_survey_covers_every_declared_harness_in_order(tmp_path: Path) -> None:
    found = harnesses.detect_all({"PATH": "", "HOME": str(tmp_path)})
    assert [item.harness_id for item in found] == [item.harness_id for item in harnesses.DETECTORS]
    assert all(item.state == "available" for item in found)


def test_the_version_query_is_bounded_and_takes_nothing_from_the_environment(
    tmp_path: Path,
) -> None:
    # `REQ-1409`: argv array, no shell, filtered environment, a time limit and a
    # bound on how much is read.
    binaries = tmp_path / "bin"
    place = binaries / ("claude.cmd" if os.name == "nt" else "claude")
    binaries.mkdir(parents=True)
    if os.name == "nt":
        place.write_text("@echo off\necho secret=absent\n", encoding="utf-8")
    else:
        place.write_text('#!/bin/sh\necho "secret=${A_SECRET:-absent}"\n', encoding="utf-8")
        place.chmod(place.stat().st_mode | stat.S_IXUSR)

    os.environ["A_SECRET"] = "must-not-reach-a-subprocess"
    try:
        version, _reason = harnesses.ask_version(place, ("--version",))
    finally:
        del os.environ["A_SECRET"]
    assert version == "secret=absent"


def test_only_the_first_line_of_a_long_answer_is_kept(tmp_path: Path) -> None:
    binaries = tmp_path / "bin"
    place = binaries / ("claude.cmd" if os.name == "nt" else "claude")
    binaries.mkdir(parents=True)
    if os.name == "nt":
        place.write_text("@echo off\necho 1.0.0\necho and much more\n", encoding="utf-8")
    else:
        place.write_text('#!/bin/sh\necho "1.0.0"\necho "and much more"\n', encoding="utf-8")
        place.chmod(place.stat().st_mode | stat.S_IXUSR)
    version, _reason = harnesses.ask_version(place, ("--version",))
    assert version == "1.0.0"


@pytest.mark.parametrize(
    ("harness_id", "package", "executable"),
    [
        ("claude-code", "@anthropic-ai/claude-code", "claude.cmd"),
        ("codex", "@openai/codex", "codex.cmd"),
        ("opencode", "opencode-ai", "opencode.cmd"),
    ],
)
def test_windows_npm_metadata_recovers_a_version_without_running_the_shim(
    harness_id: str, package: str, executable: str, tmp_path: Path
) -> None:
    detector = next(item for item in harnesses.DETECTORS if item.harness_id == harness_id)
    shim = tmp_path / "npm" / executable
    shim.parent.mkdir(parents=True)
    shim.write_text("@exit /b 134\n", encoding="utf-8")
    manifest = shim.parent / "node_modules" / Path(*package.split("/")) / "package.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"name":"declared","version":"7.8.9"}', encoding="utf-8")

    found = harnesses.detect(detector, explicit=shim, system_name="Windows")

    assert found.state == "installed"
    assert found.installations[0].version == "7.8.9"
    assert found.installations[0].version_source == "package_metadata"
    assert found.installations[0].diagnostic == "version_metadata_fallback"
    assert found.installations[0].surface == "cli"


def test_codex_desktop_uses_bounded_windows_package_metadata(tmp_path: Path) -> None:
    detector = next(item for item in harnesses.DETECTORS if item.harness_id == "codex")
    executable = (
        tmp_path
        / "WindowsApps"
        / "OpenAI.Codex_26.803.5235.0_x64__2p2nqsd0c76g0"
        / "app"
        / "resources"
        / "codex.exe"
    )
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"not executable in this test")

    found = harnesses.detect(detector, explicit=executable, system_name="Windows")

    installation = found.installations[0]
    assert installation.surface == "desktop"
    assert installation.version == "26.803.5235.0"
    assert installation.version_source == "windows_package_metadata"
    assert installation.diagnostic == "version_metadata_fallback"


def test_windows_metadata_is_bounded_and_rejects_links_and_invalid_versions(
    tmp_path: Path,
) -> None:
    detector = next(item for item in harnesses.DETECTORS if item.harness_id == "codex")
    shim = tmp_path / "npm" / "codex.cmd"
    shim.parent.mkdir(parents=True)
    shim.write_text("@exit /b 134\n", encoding="utf-8")
    manifest = shim.parent / "node_modules" / "@openai" / "codex" / "package.json"
    manifest.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text('{"version":"9.9.9"}', encoding="utf-8")
    manifest.symlink_to(outside)

    found = harnesses.detect(detector, explicit=shim, system_name="Windows")

    assert found.state == "unknown_version"
    assert found.installations[0].version == "unknown"
    assert found.installations[0].version_source == "unavailable"

    manifest.unlink()
    os.link(outside, manifest)
    found = harnesses.detect(detector, explicit=shim, system_name="Windows")
    assert found.installations[0].version == "unknown"
    assert found.installations[0].version_source == "unavailable"

    manifest.unlink()
    manifest.write_text(
        '{"version":"9.9.9","padding":"' + "x" * harnesses.METADATA_OUTPUT_LIMIT + '"}',
        encoding="utf-8",
    )
    found = harnesses.detect(detector, explicit=shim, system_name="Windows")
    assert found.installations[0].version == "unknown"
    assert found.installations[0].version_source == "unavailable"


def test_scoop_manifest_is_read_only_for_a_declared_app(tmp_path: Path) -> None:
    detector = next(item for item in harnesses.DETECTORS if item.harness_id == "opencode")
    executable = tmp_path / "scoop" / "shims" / "opencode.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"shim")
    manifest = tmp_path / "scoop" / "apps" / "opencode" / "current" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"version":"1.2.3"}', encoding="utf-8")

    found = harnesses.detect(detector, explicit=executable, system_name="Windows")

    assert found.installations[0].version == "1.2.3"
    assert found.installations[0].version_source == "package_metadata"


def test_cli_installation_is_ordered_before_desktop_for_one_harness() -> None:
    desktop = harnesses.Installation("WindowsApps/codex.exe", "2.0", "metadata", "desktop")
    cli = harnesses.Installation("npm/codex.cmd", "1.0", "metadata", "cli")
    assert sorted(
        (desktop, cli), key=lambda item: (item.surface != "cli", item.path.casefold())
    ) == [
        cli,
        desktop,
    ]


def test_the_command_reports_every_harness_without_the_home_path() -> None:
    from ai_stp_cli.commands import toolchain

    answer = toolchain.harnesses({}).payload
    assert {item.harness_id for item in answer.harnesses} == SUPPORTED
    for item in answer.harnesses:
        assert item.reason
        assert item.support in {"primary", "beta"}
        for installation in item.installations:
            assert str(Path.home()) not in installation.path
