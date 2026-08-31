"""The macOS profile bounds writes the way Linux and Windows do.

`SandboxExecLauncher.run` took a `writable` tuple and ran `del writable` on it,
under a profile that was `(allow default)` plus `(deny network*)`. So a provider
local phase on macOS could write anywhere the invoking user could — every other
harness's configuration, source trees, caches — while the same call on Linux saw
a read-only root with two binds and on Windows saw two grants.

These check the policy text rather than the sandbox, because the sandbox is
macOS-only and the profile is the part that was wrong. `just check` runs on
Linux, and a rule that can only be asserted where it already worked is the kind
of coverage `ADR-0133` was written about.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ai_stp_cli.provider import macos_launcher
from ai_stp_cli.provider.protocol_v2 import NetworkCapability, NetworkEnforcement

pytestmark = pytest.mark.cli


def test_writes_are_denied_before_anything_is_allowed(tmp_path: Path) -> None:
    """SBPL takes the last matching rule, so the deny has to come first."""
    profile = macos_launcher.profile_for(tmp_path, ())

    assert profile.index("(deny file-write*)") < profile.index("(allow file-write*")
    assert "(deny network*)" in profile


def test_the_target_and_every_named_path_are_writable(tmp_path: Path) -> None:
    target = tmp_path / "target"
    prefix = tmp_path / "prefix"
    target.mkdir()
    prefix.mkdir()

    profile = macos_launcher.profile_for(target, (prefix,))

    # POSIX rendering, not `str(path)`. SBPL is a macOS language and the
    # launcher writes `as_posix()`; on a Windows runner `str()` gives
    # backslashes and this compared the profile against a spelling nothing
    # produces. The subject is macOS either way — what runs everywhere is the
    # rule, and asserting it in the platform's own spelling is the point.
    assert f'(subpath "{target.resolve().as_posix()}")' in profile
    assert f'(subpath "{prefix.resolve().as_posix()}")' in profile


def test_nothing_else_is_writable(tmp_path: Path) -> None:
    """The falsification: a sibling the caller did not name must not appear."""
    target = tmp_path / "target"
    sibling = tmp_path / "somebody-elses-config"
    target.mkdir()
    sibling.mkdir()

    profile = macos_launcher.profile_for(target, ())

    assert sibling.resolve().as_posix() not in profile


def test_the_writable_tuple_reaches_the_argv(tmp_path: Path) -> None:
    """`run` used to discard it, so the argv is where that has to be visible."""
    target = tmp_path / "target"
    prefix = tmp_path / "prefix"
    target.mkdir()
    prefix.mkdir()
    launcher = macos_launcher.SandboxExecLauncher(
        executable=macos_launcher.EXECUTABLE,
        capability=_enforced(),
    )

    # `sys.executable` rather than `/bin/echo`: `wrap` requires an absolute
    # provider path, and `/bin/echo` is not absolute on Windows, where this
    # suite also runs. Nothing is executed — only the argv is read.
    argv = launcher.wrap((sys.executable, "hi"), target=target, writable=(prefix,))

    assert f'(subpath "{prefix.resolve().as_posix()}")' in argv[2]


def test_a_path_that_could_end_the_literal_is_refused(tmp_path: Path) -> None:
    """A quote in a filename would close the string and leave the rest as policy.

    Not created on disk: Windows refuses the name outright, and `profile_for`
    resolves rather than opens, so the rule is asserted without needing a
    filesystem that tolerates the character.
    """
    hostile = tmp_path / 'a"b'

    with pytest.raises(ValueError, match="quote or a backslash"):
        macos_launcher.profile_for(hostile, ())


def _enforced() -> NetworkCapability:
    return NetworkCapability(
        enforcement=NetworkEnforcement.ENFORCED,
        os_name="darwin",
        launcher_id=f"sandbox-exec:{macos_launcher.EXECUTABLE.as_posix()}",
        evidence=("test",),
    )
