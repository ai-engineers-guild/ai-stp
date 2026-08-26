"""Fetching program bytes whose identity a plan already fixed."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import software_fetch
from ai_stp_cli.provider.operation_v3 import SoftwareArtifact
from ai_stp_cli.toolchain import install

BODY = b"program bytes that stand for an archive"
DIGEST = "sha256:" + hashlib.sha256(BODY).hexdigest()
URL = "https://registry.example.invalid/thing-1.0.tgz"


def _artifact(**overrides: object) -> SoftwareArtifact:
    fields: dict[str, object] = {
        "platform": "linux/x86_64",
        "url": URL,
        "sha256": DIGEST,
        "byte_length": len(BODY),
        "entry_point": "bin/thing",
    }
    fields.update(overrides)
    return SoftwareArtifact(**fields)  # pyright: ignore[reportArgumentType]


def _serving(body: bytes) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(200, content=body))


def test_a_matching_artifact_lands_in_the_verified_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_STP_DATA_DIR", str(tmp_path))

    stored = software_fetch.fetch(_artifact(), transport=_serving(BODY))

    assert stored.read_bytes() == BODY
    assert stored.parent == install.cache_dir()


def test_a_second_fetch_reads_the_cache_and_never_the_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_STP_DATA_DIR", str(tmp_path))
    software_fetch.fetch(_artifact(), transport=_serving(BODY))

    def refuse(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("a cached artifact was fetched again")

    assert (
        software_fetch.fetch(_artifact(), transport=httpx.MockTransport(refuse)).read_bytes()
        == BODY
    )


def test_bytes_that_do_not_match_the_plan_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The digest is the anchor; the host that served them is not."""
    monkeypatch.setenv("AI_STP_DATA_DIR", str(tmp_path))
    # Same length by construction, so the digest is the only thing that can
    # reject it — a hand-counted literal proved the point badly once already.
    other = b"x" * len(BODY)
    assert other != BODY

    with pytest.raises(CliFailure):
        software_fetch.fetch(_artifact(), transport=_serving(other))

    assert not any(install.cache_dir().iterdir()) if install.cache_dir().exists() else True


def test_a_truncated_response_is_refused_by_length(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reported as a length, not a digest: a prefix is a shorter thing, not a wrong one."""
    monkeypatch.setenv("AI_STP_DATA_DIR", str(tmp_path))

    with pytest.raises(CliFailure) as raised:
        software_fetch.fetch(_artifact(), transport=_serving(BODY[:10]))

    assert "length" in raised.value.message


def test_the_deadline_grows_with_the_stated_length() -> None:
    """A flat timeout is a size limit wearing a clock.

    Measured against the shipped providers: opencode is 60 MB and grok is
    167 MB, so one fixed deadline passes the smaller and fails the larger on the
    same connection — and the failure reads as the larger vendor's fault.
    """
    small = install.download_deadline(60_167_326)
    large = install.download_deadline(166_854_368)

    assert large > small >= install.DOWNLOAD_TIMEOUT_SECONDS
    # The same floor still applies to something tiny.
    assert install.download_deadline(0) == install.DOWNLOAD_TIMEOUT_SECONDS
