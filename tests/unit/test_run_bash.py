"""The back-regress helper must pick Git bash on Windows, never WSL."""

from __future__ import annotations

from pathlib import Path

import pytest
from release_scripts import run_bash
from release_scripts.run_bash import BashNotFoundError, locate_bash, main


def test_ai_stp_bash_override_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bash = tmp_path / "bash.exe"
    bash.write_bytes(b"")
    monkeypatch.setenv("AI_STP_BASH", str(bash))
    assert locate_bash() == bash


def test_ai_stp_bash_rejects_a_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_STP_BASH", str(Path("C:/definitely-not-a-bash.exe")))
    with pytest.raises(BashNotFoundError, match="not a file"):
        locate_bash()


def test_ai_stp_bash_rejects_wsl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The real WSL binary lives under System32; a path with that part is enough
    # to prove the guard without depending on WSL being installed.
    wsl_root = tmp_path / "Windows" / "System32"
    wsl_root.mkdir(parents=True)
    wsl = wsl_root / "bash.exe"
    wsl.write_bytes(b"")
    monkeypatch.setattr(run_bash, "_on_windows", lambda: True)
    monkeypatch.setenv("AI_STP_BASH", str(wsl))
    with pytest.raises(BashNotFoundError, match="WSL"):
        locate_bash()


def test_main_refuses_without_a_script() -> None:
    assert main([]) == 2


def test_locate_bash_returns_an_existing_file() -> None:
    located = locate_bash()
    assert located.is_file()
