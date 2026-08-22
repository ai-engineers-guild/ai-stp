"""Pinned just bootstrap retries only failures that another attempt may fix."""

import hashlib
import io
import urllib.error
from email.message import Message
from pathlib import Path

import pytest
from docs_scripts import bootstrap_just


def test_download_retries_transport_failures_with_visible_backoff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    archive = tmp_path / "just.tar.gz"
    payload = b"exact pinned asset"
    attempts = 0
    delays: list[float] = []

    def download(_url: str, target: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionResetError("connection reset")
        target.write_bytes(payload)

    bootstrap_just.download_verified(
        "https://example.test/just.tar.gz",
        archive,
        hashlib.sha256(payload).hexdigest(),
        download=download,
        sleep=delays.append,
    )

    assert attempts == 3
    assert delays == [5, 15]
    log = capsys.readouterr().err
    assert "attempt 1/4" in log
    assert "attempt 2/4" in log
    assert "retrying in 5s" in log
    assert "retrying in 15s" in log


def test_download_does_not_retry_a_not_found_response(tmp_path: Path) -> None:
    attempts = 0
    delays: list[float] = []

    def download(url: str, _target: Path) -> None:
        nonlocal attempts
        attempts += 1
        raise urllib.error.HTTPError(url, 404, "Not Found", Message(), io.BytesIO())

    with pytest.raises(urllib.error.HTTPError) as raised:
        bootstrap_just.download_verified(
            "https://example.test/missing.tar.gz",
            tmp_path / "missing.tar.gz",
            "0" * 64,
            download=download,
            sleep=delays.append,
        )

    assert raised.value.code == 404
    assert attempts == 1
    assert delays == []


def test_download_retries_a_server_error(tmp_path: Path) -> None:
    archive = tmp_path / "just.tar.gz"
    payload = b"exact pinned asset"
    attempts = 0

    def download(url: str, target: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise urllib.error.HTTPError(url, 503, "Unavailable", Message(), io.BytesIO())
        target.write_bytes(payload)

    bootstrap_just.download_verified(
        "https://example.test/just.tar.gz",
        archive,
        hashlib.sha256(payload).hexdigest(),
        download=download,
        sleep=lambda _delay: None,
    )

    assert attempts == 2


def test_download_never_accepts_bytes_that_miss_the_pin(tmp_path: Path) -> None:
    attempts = 0

    def download(_url: str, target: Path) -> None:
        nonlocal attempts
        attempts += 1
        target.write_bytes(b"wrong asset")

    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        bootstrap_just.download_verified(
            "https://example.test/just.tar.gz",
            tmp_path / "just.tar.gz",
            hashlib.sha256(b"exact pinned asset").hexdigest(),
            download=download,
            sleep=lambda _delay: None,
        )

    assert attempts == 1


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Linux", "x86_64", "just-1.43.0-x86_64-unknown-linux-musl.tar.gz"),
        ("Linux", "aarch64", "just-1.43.0-aarch64-unknown-linux-musl.tar.gz"),
        ("Darwin", "arm64", "just-1.43.0-aarch64-apple-darwin.tar.gz"),
        ("Darwin", "x86_64", "just-1.43.0-x86_64-apple-darwin.tar.gz"),
        ("Windows", "AMD64", "just-1.43.0-x86_64-pc-windows-msvc.zip"),
        ("Windows", "ARM64", "just-1.43.0-aarch64-pc-windows-msvc.zip"),
    ],
)
def test_every_supported_platform_resolves_to_a_pinned_asset(
    monkeypatch: pytest.MonkeyPatch, system: str, machine: str, expected: str
) -> None:
    """Windows is here because its absence was paid for once.

    The public cross-platform job used to take `just` from Chocolatey, a
    community feed with nothing pinned, and the step failed having printed
    nothing because its output was redirected away. Resolving to a release
    archive means the same checksum comparison on all three systems.
    """
    monkeypatch.setattr(bootstrap_just.platform, "system", lambda: system)
    monkeypatch.setattr(bootstrap_just.platform, "machine", lambda: machine)

    asset = bootstrap_just.target_asset()

    assert asset == expected
    # A mapping entry without a pin is worse than a missing entry: it resolves
    # and then downloads something nothing compared.
    assert bootstrap_just.SHA256[asset]
    assert not bootstrap_just.SHA256[asset].startswith("REPLACE_")


def test_an_unsupported_platform_refuses_rather_than_guessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap_just.platform, "system", lambda: "Plan9")
    monkeypatch.setattr(bootstrap_just.platform, "machine", lambda: "sparc")

    with pytest.raises(RuntimeError, match="unsupported platform for just bootstrap: Plan9 sparc"):
        bootstrap_just.target_asset()
