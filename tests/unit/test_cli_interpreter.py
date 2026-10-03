"""A spawned child needs a real interpreter, and a frozen build has none.

`sys.executable` under PyInstaller is the CLI binary — a click application
that answers `-c` and `-m` with a usage error. Every child the CLI spawns
through it (sandbox probes, provenance verification, scheduled wakeups)
then fails wearing the wrong reason. These tests pin the rule: normal
builds answer `sys.executable`; frozen builds ask PATH or refuse.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ai_stp_cli import interpreter
from ai_stp_cli.provider import network_launcher


@pytest.fixture(autouse=True)
def _uncached() -> None:
    # Both helpers memoize; a patched `frozen` must see a fresh answer.
    interpreter.python.cache_clear()
    interpreter.uv.cache_clear()


def test_a_normal_build_children_its_own_interpreter() -> None:
    assert interpreter.python() == sys.executable
    assert interpreter.uv() == [sys.executable, "-m", "uv"]


def _on_path(name: str) -> str:
    return f"/usr/bin/{name}"


def _only_python(name: str) -> str | None:
    return "/usr/bin/python" if name == "python" else None


def _nothing(_name: str) -> None:
    return None


def _only_uv(name: str) -> str | None:
    return "/usr/local/bin/uv" if name == "uv" else None


def _noop(*_args: object) -> None:
    return None


def test_a_frozen_build_asks_path_for_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(shutil, "which", _on_path)
    assert interpreter.python() == "/usr/bin/python3"
    interpreter.python.cache_clear()
    monkeypatch.setattr(shutil, "which", _only_python)
    assert interpreter.python() == "/usr/bin/python"


def test_a_frozen_build_without_python_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(shutil, "which", _nothing)
    assert interpreter.python() is None
    assert interpreter.uv() is None


def test_a_frozen_build_uses_a_uv_binary_not_dash_m(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `-m uv` needs the installed package; a frozen binary cannot be an
    # interpreter at all, so it looks for the standalone executable instead.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(shutil, "which", _only_uv)
    assert interpreter.uv() == ["/usr/local/bin/uv"]


def test_the_probe_prefers_a_path_python_over_the_frozen_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The positive-control probe's argv must name the resolved interpreter,
    # not `sys.executable` — under PyInstaller the latter is the CLI itself
    # and the "sandbox" would appear to fail on a click usage error.
    monkeypatch.setattr(interpreter, "python", lambda: "/usr/bin/python3")
    monkeypatch.setattr(network_launcher, "positive_control", _noop)
    seen: list[str] = []

    def captured(argv: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.extend(argv)
        return subprocess.CompletedProcess(
            argv, 0, '{"dns_udp":"denied","ipv4":"denied","ipv6":"denied"}', ""
        )

    monkeypatch.setattr(subprocess, "run", captured)
    passed, _evidence = network_launcher._probe_bubblewrap(Path("/usr/bin/bwrap"))  # pyright: ignore[reportPrivateUsage]
    assert passed
    assert "/usr/bin/python3" in seen
    assert sys.executable not in seen


def test_the_probe_refuses_clearly_when_frozen_finds_no_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `None` is the refusal, not a fallback: spawning the CLI binary as the
    # child would produce a click error that reads as a sandbox defect.
    monkeypatch.setattr(interpreter, "python", lambda: None)
    monkeypatch.setattr(network_launcher, "positive_control", _noop)
    passed, evidence = network_launcher._probe_bubblewrap(Path("/usr/bin/bwrap"))  # pyright: ignore[reportPrivateUsage]
    assert not passed
    assert "no python3/python on PATH" in evidence[0]
