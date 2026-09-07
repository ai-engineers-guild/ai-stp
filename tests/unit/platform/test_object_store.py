"""Unit tests for immutable object writes (SPEC-020 REQ-2005/REQ-2006)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage import ImmutableObjectStore, ObjectConflict, ObjectIntegrityError
from ai_stp_platform.storage.migrate import migrate_legacy_objects
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN
from ai_stp_platform.storage.verify import StorageVerificationError, verify_referenced_objects

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


@pytest.mark.asyncio
async def test_owner_scoped_objects_cannot_collide_across_accounts() -> None:
    payload = b"private artifact"
    client = RecordingObjectClient()
    settings = StorageSettings(
        endpoint="memory://test",
        bucket="legacy",
        artifact_bucket="artifacts",
        asset_bucket="assets",
        access_key_id="test",
        secret_access_key="test-secret",
    )
    store = ImmutableObjectStore(settings=settings, client=client)

    first = await store.put_immutable(
        payload,
        expected_digest=_digest(payload),
        expected_size=len(payload),
        owner_account_id="account_first",
    )
    second = await store.put_immutable(
        payload,
        expected_digest=_digest(payload),
        expected_size=len(payload),
        owner_account_id="account_second",
    )

    assert first.bucket == second.bucket == "artifacts"
    assert first.key != second.key
    assert "/accounts/account_first/" in first.key
    assert "/accounts/account_second/" in second.key
    assert (
        await store.read_by_digest(
            first.digest,
            expected_size=len(payload),
            owner_account_id="account_first",
        )
        == payload
    )
    assert (
        await store.read_by_digest(
            first.digest,
            expected_size=len(payload),
            owner_account_id="account_second",
        )
        == payload
    )
    assert client.put_count == 2


@pytest.mark.asyncio
async def test_restore_verifier_hashes_artifacts_and_uploaded_assets() -> None:
    settings = StorageSettings(
        endpoint="memory://test",
        artifact_bucket="artifacts",
        asset_bucket="assets",
        access_key_id="test",
        secret_access_key="test-secret",
    )
    client = RecordingObjectClient()
    artifact_store = ImmutableObjectStore(settings=settings, client=client)
    asset_store = ImmutableObjectStore(settings=settings, client=client, bucket="assets")
    artifact_payload = b"artifact"
    asset_payload = b"asset"
    artifact = await artifact_store.put_immutable(
        artifact_payload,
        expected_digest=_digest(artifact_payload),
        expected_size=len(artifact_payload),
        owner_account_id="account_owner",
    )
    avatar = await asset_store.put_immutable(
        asset_payload,
        expected_digest=_digest(asset_payload),
        expected_size=len(asset_payload),
        owner_account_id="account_owner",
        namespace="users/avatars",
    )
    media = await asset_store.put_immutable(
        asset_payload,
        expected_digest=_digest(asset_payload),
        expected_size=len(asset_payload),
        owner_account_id="account_owner",
        namespace="components/component_one/media",
    )
    location = SimpleNamespace(
        id=1,
        owner_account_id="account_owner",
        object_key=artifact.key,
        digest=artifact.digest,
        size_bytes=artifact.size_bytes,
        bucket=artifact.bucket,
    )
    metadata = SimpleNamespace(owner_account_id="account_owner")
    avatar_row = SimpleNamespace(
        id="avatar_one",
        account_id="account_owner",
        object_key=avatar.key,
        content_digest=avatar.digest,
        size_bytes=avatar.size_bytes,
    )
    media_row = SimpleNamespace(
        id="media_one",
        stable_id="component_one",
        owner_account_id="account_owner",
        object_key=media.key,
        content_digest=media.digest,
        size_bytes=media.size_bytes,
    )

    def session() -> AsyncSession:
        fake = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(location, metadata)])),
            scalars=AsyncMock(side_effect=[[avatar_row], [media_row]]),
        )
        return cast(AsyncSession, fake)

    counts = await verify_referenced_objects(session(), settings=settings, client=client)
    assert (counts.artifacts, counts.avatars, counts.component_media) == (1, 1, 1)

    client.objects[(media.bucket, media.key)]["body"] = b"tampered"
    with pytest.raises(StorageVerificationError, match="component media"):
        await verify_referenced_objects(session(), settings=settings, client=client)


@pytest.mark.asyncio
async def test_legacy_objects_are_copied_to_owner_scoped_buckets_idempotently() -> None:
    settings = StorageSettings(
        endpoint="memory://test",
        bucket="legacy",
        artifact_bucket="artifacts",
        asset_bucket="assets",
        access_key_id="test",
        secret_access_key="test-secret",
    )
    client = RecordingObjectClient()
    artifact_payload = b"artifact"
    avatar_payload = b"avatar"
    media_payload = b"media"
    for key, payload in (
        ("objects/sha256/artifact", artifact_payload),
        ("objects/sha256/avatar", avatar_payload),
        ("objects/sha256/media", media_payload),
    ):
        client.objects[("legacy", key)] = {
            "body": payload,
            "metadata": {},
            "size_bytes": len(payload),
        }
    location = SimpleNamespace(
        id=1,
        owner_account_id=None,
        object_key="objects/sha256/artifact",
        digest=_digest(artifact_payload),
        size_bytes=len(artifact_payload),
        bucket=None,
    )
    metadata = SimpleNamespace(owner_account_id="account_owner")
    avatar = SimpleNamespace(
        id="avatar_one",
        account_id="account_owner",
        object_key="objects/sha256/avatar",
        content_digest=None,
        size_bytes=len(avatar_payload),
    )
    media = SimpleNamespace(
        id="media_one",
        stable_id="component_one",
        owner_account_id="account_owner",
        object_key="objects/sha256/media",
        content_digest=None,
        size_bytes=len(media_payload),
    )
    fake = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(location, metadata)])),
        scalars=AsyncMock(side_effect=[[avatar], [media], [avatar], [media]]),
        commit=AsyncMock(),
    )
    session = cast(AsyncSession, fake)

    first = await migrate_legacy_objects(session, settings=settings, client=client)
    second = await migrate_legacy_objects(session, settings=settings, client=client)

    assert (first.artifacts, first.avatars, first.component_media) == (1, 1, 1)
    assert (second.artifacts, second.avatars, second.component_media) == (0, 0, 0)
    assert location.bucket == "artifacts"
    assert location.owner_account_id == "account_owner"
    assert "/accounts/account_owner/artifacts/" in location.object_key
    assert "/accounts/account_owner/users/avatars/" in avatar.object_key
    assert "/accounts/account_owner/components/component_one/media/" in media.object_key
    assert fake.commit.await_count == 2
