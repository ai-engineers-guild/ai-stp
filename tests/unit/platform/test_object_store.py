"""Unit tests for immutable object writes (SPEC-020 REQ-2005/REQ-2006)."""

from __future__ import annotations

import pytest

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage import ImmutableObjectStore, ObjectConflict, ObjectIntegrityError
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN

pytestmark = pytest.mark.platform


class RecordingObjectClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}
        self.put_count = 0

    async def head_object(self, *, bucket: str, key: str) -> dict[str, object] | None:
        return self.objects.get((bucket, key))

    async def put_object(
        self,
        *,
        bucket: str,
        key: str,
        body: bytes,
        metadata: dict[str, str],
    ) -> None:
        self.put_count += 1
        self.objects[(bucket, key)] = {
            "body": body,
            "metadata": metadata,
            "size_bytes": len(body),
        }

    async def get_object_bytes(self, *, bucket: str, key: str) -> bytes | None:
        stored = self.objects.get((bucket, key))
        if stored is None:
            return None
        body = stored.get("body")
        return body if isinstance(body, bytes) else None


class FailingOnceObjectClient(RecordingObjectClient):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_put = True

    async def put_object(
        self,
        *,
        bucket: str,
        key: str,
        body: bytes,
        metadata: dict[str, str],
    ) -> None:
        if self.fail_next_put:
            self.fail_next_put = False
            raise RuntimeError("interrupted upload")
        await super().put_object(bucket=bucket, key=key, body=body, metadata=metadata)


def _settings() -> StorageSettings:
    return StorageSettings(
        endpoint="http://127.0.0.1:9000",
        bucket="ai-stp-test",
        access_key_id="test-access",
        secret_access_key="test-secret",
    )


def _digest(payload: bytes) -> str:
    return digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)


@pytest.mark.asyncio
async def test_put_immutable_identical_payload_is_idempotent() -> None:
    payload = b'{"kind":"component"}'
    client = RecordingObjectClient()
    store = ImmutableObjectStore(settings=_settings(), client=client)

    first = await store.put_immutable(
        payload,
        expected_digest=_digest(payload),
        expected_size=len(payload),
    )
    second = await store.put_immutable(
        payload,
        expected_digest=_digest(payload),
        expected_size=len(payload),
    )

    assert first.created is True
    assert second.created is False
    assert first.key == second.key
    assert first.digest == _digest(payload)
    assert client.put_count == 1


@pytest.mark.asyncio
async def test_put_immutable_rejects_digest_or_size_mismatch() -> None:
    payload = b"artifact"
    store = ImmutableObjectStore(settings=_settings(), client=RecordingObjectClient())

    with pytest.raises(ObjectIntegrityError):
        await store.put_immutable(
            payload,
            expected_digest=_digest(b"different"),
            expected_size=len(payload),
        )

    with pytest.raises(ObjectIntegrityError):
        await store.put_immutable(
            payload,
            expected_digest=_digest(payload),
            expected_size=len(payload) + 1,
        )


@pytest.mark.asyncio
async def test_put_immutable_conflicts_when_existing_metadata_differs() -> None:
    payload = b"artifact"
    client = RecordingObjectClient()
    store = ImmutableObjectStore(settings=_settings(), client=client)
    created = await store.put_immutable(
        payload,
        expected_digest=_digest(payload),
        expected_size=len(payload),
    )
    client.objects[(created.bucket, created.key)]["metadata"] = {
        "ai-stp-digest": _digest(b"different"),
        "ai-stp-size-bytes": str(len(payload)),
        "ai-stp-content-id": _digest(b"different"),
    }

    with pytest.raises(ObjectConflict):
        await store.put_immutable(
            payload,
            expected_digest=_digest(payload),
            expected_size=len(payload),
        )


@pytest.mark.asyncio
async def test_put_immutable_interrupted_upload_can_be_retried() -> None:
    payload = b"artifact"
    client = FailingOnceObjectClient()
    store = ImmutableObjectStore(settings=_settings(), client=client)

    with pytest.raises(RuntimeError, match="interrupted upload"):
        await store.put_immutable(
            payload,
            expected_digest=_digest(payload),
            expected_size=len(payload),
        )

    assert client.objects == {}

    retried = await store.put_immutable(
        payload,
        expected_digest=_digest(payload),
        expected_size=len(payload),
    )

    assert retried.created is True
    assert client.objects[(retried.bucket, retried.key)]["body"] == payload


@pytest.mark.asyncio
async def test_read_by_digest_verifies_optional_size_and_integrity() -> None:
    # Breakage: corrupted or missing objects returned without integrity checks.
    payload = b'{"kind":"component"}'
    client = RecordingObjectClient()
    store = ImmutableObjectStore(settings=_settings(), client=client)
    created = await store.put_immutable(
        payload,
        expected_digest=_digest(payload),
        expected_size=len(payload),
    )

    assert await store.read_by_digest(created.digest) == payload
    assert await store.read_by_digest(created.digest, expected_size=len(payload)) == payload
    assert await store.read_by_digest(_digest(b"missing")) is None

    with pytest.raises(ObjectIntegrityError, match="size"):
        await store.read_by_digest(created.digest, expected_size=len(payload) + 1)

    # Corrupt stored body while keeping the key; digest check must fail closed.
    client.objects[(created.bucket, created.key)]["body"] = b"tampered"
    with pytest.raises(ObjectIntegrityError, match="digest"):
        await store.read_by_digest(created.digest)


@pytest.mark.asyncio
async def test_read_verified_rejects_size_and_digest_mismatches() -> None:
    payload = b"artifact-bytes"
    client = RecordingObjectClient()
    store = ImmutableObjectStore(settings=_settings(), client=client)
    created = await store.put_immutable(
        payload,
        expected_digest=_digest(payload),
        expected_size=len(payload),
    )

    assert (
        await store.read_verified(
            object_key=created.key,
            expected_digest=created.digest,
            expected_size=len(payload),
        )
        == payload
    )
    assert (
        await store.read_verified(
            object_key="missing-key",
            expected_digest=created.digest,
            expected_size=len(payload),
        )
        is None
    )

    client.objects[(created.bucket, created.key)]["body"] = payload + b"x"
    with pytest.raises(ObjectIntegrityError, match="size"):
        await store.read_verified(
            object_key=created.key,
            expected_digest=created.digest,
            expected_size=len(payload),
        )
