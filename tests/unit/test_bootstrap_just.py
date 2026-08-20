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
