"""The length bound neither the compiler nor the provider can decide alone.

A bundle carrying a 300-character relative path passes `validate-bundle`,
installs on Linux and macOS, and fails on Windows partway through `apply` —
because `MAX_PATH` counts the whole path and validation has never seen the root.

Both halves belong to this side: the compiler builds the bundle and the consumer
chooses the target, so the arithmetic is only possible here, at plan time. The
provider deliberately does not enforce it — a provider stricter than the
compiler refuses bundles the platform has already blessed, and it would be
guessing at a home directory besides.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_stp_cli.local import windows_paths

pytestmark = pytest.mark.cli


def test_nothing_is_refused_on_a_platform_with_no_such_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Called unconditionally, so it must be silent where it does not apply.

    Inventing the limit on Linux and macOS would refuse installs that work,
    which is the more expensive of the two ways to be wrong here.
    """
    monkeypatch.setattr(windows_paths, "on_windows", lambda: False)
    assert windows_paths.too_long_for_windows(Path("/home/someone/.codex"), ["x" * 4000]) == []
    assert windows_paths.long_paths_enabled() is False


def test_the_root_is_counted_with_the_relative_path_and_the_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point: neither half is over the limit, and the sum is.

    A check on the relative path alone passes this, and a check on the root
    alone passes it too — which is exactly how a bundle that validates cleanly
    fails at apply time.
    """
    monkeypatch.setattr(windows_paths, "on_windows", lambda: True)
    monkeypatch.setattr(windows_paths, "long_paths_enabled", lambda: False)
    root = Path("C:/Users/a-fairly-long-account-name/AppData/Roaming/SomeProduct")
    fits = "s" * (windows_paths.MAX_PATH_CHARACTERS - len(str(root)) - 1)
    assert windows_paths.too_long_for_windows(root, [fits]) == []
    assert windows_paths.too_long_for_windows(root, [fits + "s"]) == [fits + "s"]


def test_a_machine_that_opted_out_of_the_limit_is_not_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LongPathsEnabled` is a real answer, and refusing anyway would be wrong."""
    monkeypatch.setattr(windows_paths, "on_windows", lambda: True)
    monkeypatch.setattr(windows_paths, "long_paths_enabled", lambda: True)
    assert windows_paths.too_long_for_windows(Path("C:/x"), ["y" * 4000]) == []


def test_a_machine_that_cannot_be_asked_is_treated_as_not_opted_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No registry here, so the import fails and the answer is the safe one.

    Being wrong this way costs a refusal the operator can act on. Being wrong
    the other way costs a half-applied install.
    """
    monkeypatch.setattr(windows_paths, "on_windows", lambda: True)
    assert windows_paths.long_paths_enabled() is False


def test_the_limit_is_the_documented_one_rather_than_a_round_number() -> None:
    """260 includes the terminating NUL, so 259 characters is the path."""
    assert windows_paths.MAX_PATH_CHARACTERS == 259
