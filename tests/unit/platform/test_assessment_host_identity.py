"""Assessment platform identity must describe the actual scan host."""

from __future__ import annotations

import platform
import sys

import pytest

from ai_stp_platform.catalog_assessments import AssessmentError, scan_host_platform


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("linux", "x86_64", ("linux", "x86_64")),
        ("linux", "aarch64", ("linux", "arm64")),
        ("darwin", "arm64", ("macos", "arm64")),
        ("win32", "AMD64", ("windows", "x86_64")),
    ],
)
def test_supported_host_identity(
    monkeypatch: pytest.MonkeyPatch, system: str, machine: str, expected: tuple[str, str]
) -> None:
    monkeypatch.setattr(sys, "platform", system)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    assert scan_host_platform() == expected


@pytest.mark.parametrize(("system", "machine"), [("freebsd14", "x86_64"), ("linux", "riscv64")])
def test_unknown_host_cannot_issue_another_platforms_evidence(
    monkeypatch: pytest.MonkeyPatch, system: str, machine: str
) -> None:
    monkeypatch.setattr(sys, "platform", system)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    with pytest.raises(AssessmentError, match="unsupported"):
        scan_host_platform()
