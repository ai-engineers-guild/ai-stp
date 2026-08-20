"""Fetching artifact bytes: verified against the passport, cached by content."""

import hashlib
import os
from pathlib import Path

import httpx
import pytest

from ai_stp_cli.cloud import catalog
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache
from ai_stp_contracts.machine_help import CatalogKind
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.versions import ArtifactRef

BYTES = b"the exact bytes of one published version"
DIGEST = digest_bytes(cache.ARTIFACT_DOMAIN, BYTES)
REF = ArtifactRef(digest=DIGEST, size_bytes=len(BYTES))
OBJECT = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
MOCK = Endpoint("https://ai-stp.example/v1")


def _serving(payload: bytes, status: int = 200) -> httpx.MockTransport:
    def answer(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, json={"error": {"code": "AI_STP_NOT_FOUND"}})
        return httpx.Response(200, content=payload)

    return httpx.MockTransport(answer)


def test_version_and_raw_artifact_identities_are_not_interchangeable() -> None:
    raw_digest = f"sha256:{hashlib.sha256(BYTES).hexdigest()}"

    assert raw_digest != DIGEST
    assert cache.version_artifact_path(DIGEST).parent != cache.raw_artifact_path(raw_digest).parent
    raw_path = cache.store_raw_artifact_bytes(BYTES, raw_digest)
    assert cache.stored_version_artifact(raw_digest) is None
    assert raw_path.exists(), "a lookup in another digest domain deleted valid raw bytes"


def test_a_raw_sha_from_an_artifact_ref_is_refused_for_the_same_bytes() -> None:
    raw_digest = f"sha256:{hashlib.sha256(BYTES).hexdigest()}"
    wrong_domain = ArtifactRef(digest=raw_digest, size_bytes=len(BYTES))

    with pytest.raises(CliFailure, match="does not hash to what its passport declares"):
        catalog.fetch_artifact(
            MOCK,
            "component",
            OBJECT,
            "1.0",
            wrong_domain,
            transport=_serving(BYTES),
        )
    assert not cache.version_artifact_path(raw_digest).exists()


def test_the_bytes_are_verified_and_kept_under_their_digest() -> None:
    path = catalog.fetch_artifact(MOCK, "component", OBJECT, "1.0", REF, transport=_serving(BYTES))
    assert path.read_bytes() == BYTES
    assert path == cache.version_artifact_path(DIGEST)


def test_a_second_fetch_does_not_use_the_network() -> None:
    catalog.fetch_artifact(MOCK, "component", OBJECT, "1.0", REF, transport=_serving(BYTES))

    def refuse(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("a cached artifact must not be fetched again")

    again = catalog.fetch_artifact(
        MOCK, "component", OBJECT, "1.0", REF, transport=httpx.MockTransport(refuse)
    )
    assert again.read_bytes() == BYTES


def test_bytes_that_do_not_hash_to_the_passport_are_refused_and_not_kept() -> None:
    # Verified against the passport, not against the response: headers from the
    # server that sent the bytes cannot attest to them.
    with pytest.raises(CliFailure, match="does not hash to what its passport declares"):
        catalog.fetch_artifact(
            MOCK,
            "component",
            OBJECT,
            "1.0",
            REF,
            # The right length and the wrong content, so this is the digest
            # check and not the size check.
            transport=_serving(b"X" * len(BYTES)),
        )
    assert not cache.version_artifact_path(DIGEST).exists()
    # And nothing partial left behind under a scratch name either.
    leftovers = cache.version_artifact_path(DIGEST).parent
    assert not leftovers.exists() or list(leftovers.glob("*")) == []


def test_a_short_artifact_is_refused_as_a_size_mismatch() -> None:
    with pytest.raises(CliFailure, match="not the size its passport declares"):
        catalog.fetch_artifact(
            MOCK, "component", OBJECT, "1.0", REF, transport=_serving(BYTES[:-5])
        )
    assert not cache.version_artifact_path(DIGEST).exists()


def test_a_stream_longer_than_declared_stops_rather_than_being_read_whole() -> None:
    # An artifact is the one payload with no modelled upper bound. Without this
    # a server — or anything between — could answer with as much as it liked.
    flood = BYTES + b"x" * (10 * 1024 * 1024)
    with pytest.raises(CliFailure, match="larger than its passport declares"):
        catalog.fetch_artifact(MOCK, "component", OBJECT, "1.0", REF, transport=_serving(flood))
    assert not cache.version_artifact_path(DIGEST).exists()


def test_a_refusal_from_the_platform_is_a_typed_failure() -> None:
    with pytest.raises(CliFailure) as raised:
        catalog.fetch_artifact(
            MOCK, "component", OBJECT, "1.0", REF, transport=_serving(b"", status=404)
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_a_cached_file_that_stopped_hashing_correctly_is_not_served(tmp_path: Path) -> None:
    # A full disk truncates; anything with write access can edit. Returning it
    # unchecked would make the cache the one place the guarantee stops holding.
    path = catalog.fetch_artifact(MOCK, "component", OBJECT, "1.0", REF, transport=_serving(BYTES))
    path.write_bytes(b"tampered")

    assert cache.stored_version_artifact(DIGEST) is None
    assert not path.exists(), "a file that failed its own digest was left in place"


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes are not the Windows ACL model")
def test_a_cached_private_bundle_widened_to_other_users_is_not_served() -> None:
    raw_digest = f"sha256:{hashlib.sha256(BYTES).hexdigest()}"
    path = cache.store_raw_artifact_bytes(BYTES, raw_digest)
    path.chmod(0o644)

    assert cache.stored_raw_artifact(raw_digest) is None
    assert not path.exists()


def test_complete_in_memory_raw_artifact_bytes_are_verified_and_cached() -> None:
    raw_digest = f"sha256:{hashlib.sha256(BYTES).hexdigest()}"
    path = cache.store_raw_artifact_bytes(BYTES, raw_digest)
    assert path == cache.raw_artifact_path(raw_digest)
    assert path.read_bytes() == BYTES
    assert cache.store_raw_artifact_bytes(BYTES, raw_digest) == path


def test_in_memory_raw_artifact_refuses_a_wrong_or_noncanonical_digest() -> None:
    with pytest.raises(CliFailure, match="do not match"):
        cache.store_raw_artifact_bytes(BYTES, "sha256:" + "0" * 64)
    with pytest.raises(CliFailure, match="canonical SHA-256"):
        cache.store_raw_artifact_bytes(BYTES, "../../outside")


def test_an_artifact_the_passport_does_not_declare_is_named_rather_than_downloaded() -> None:
    from ai_stp_cli.commands import registry as registry_commands
    from ai_stp_contracts.catalog import CatalogTrust
    from ai_stp_contracts.machine_help import CatalogVersionView

    view = CatalogVersionView(
        kind="component",
        source="online",
        checked_at="2026-08-06T00:00:00.000Z",
        passport_digest="sha256:" + "0" * 64,
        lifecycle="active",
        trust=CatalogTrust(
            trust_lane="authoritative", author_verified=True, component_verified=True
        ),
        published_at="2026-08-06T00:00:00.000Z",
        passport={"kind": "component"},
    )
    with pytest.raises(CliFailure, match="declares no artifact"):
        registry_commands._artifact_of(view)  # pyright: ignore[reportPrivateUsage]

    view = view.model_copy(update={"passport": {"artifact": {"digest": "nonsense"}}})
    with pytest.raises(CliFailure, match="cannot read"):
        registry_commands._artifact_of(view)  # pyright: ignore[reportPrivateUsage]


def test_the_fetch_command_reports_where_the_verified_bytes_are(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command end of the same path, including the second call.

    `source` is what an offline caller needs: it says whether the network was
    involved, and the second call must say `cache` without one.
    """
    from ai_stp_cli.commands import registry as registry_commands
    from ai_stp_contracts.catalog import CatalogTrust
    from ai_stp_contracts.machine_help import CatalogVersionView

    view = CatalogVersionView(
        kind="component",
        source="online",
        checked_at="2026-08-06T00:00:00.000Z",
        passport_digest="sha256:" + "0" * 64,
        lifecycle="active",
        trust=CatalogTrust(
            trust_lane="authoritative", author_verified=True, component_verified=True
        ),
        published_at="2026-08-06T00:00:00.000Z",
        passport={"artifact": {"digest": DIGEST, "size_bytes": len(BYTES)}},
    )
    monkeypatch.setattr(registry_commands, "endpoint", lambda: MOCK)

    def one_version(
        endpoint: Endpoint, kind: str, stable_id: str, number: str
    ) -> CatalogVersionView:
        return view

    # Captured before the patch: the stub calls the real one, and taking it
    # afterwards would be the stub calling itself.
    real_fetch = catalog.fetch_artifact

    def served(
        endpoint: Endpoint,
        kind: CatalogKind,
        stable_id: str,
        version_number: str,
        expected: ArtifactRef,
    ) -> Path:
        return real_fetch(
            endpoint, kind, stable_id, version_number, expected, transport=_serving(BYTES)
        )

    monkeypatch.setattr(catalog, "version", one_version)
    monkeypatch.setattr(catalog, "fetch_artifact", served)

    asked = {"kind": "component", "id": OBJECT, "version": "1.0"}
    first = registry_commands.fetch(asked).payload
    assert first.source == "online"
    assert first.digest == DIGEST
    assert first.size_bytes == len(BYTES)
    # Rendered with the home directory folded away, like every other path.
    assert not first.path.startswith(str(Path.home()))

    second = registry_commands.fetch(asked).payload
    assert second.source == "cache"

    with pytest.raises(CliFailure, match="identifier and a version are both required"):
        registry_commands.fetch({"kind": "component"})
