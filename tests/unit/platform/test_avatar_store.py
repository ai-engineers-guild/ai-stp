"""Avatar object store writes processed bytes (SPEC-028 media)."""

from __future__ import annotations

import pytest

from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage import AvatarObjectStore, MemoryObjectClient


@pytest.mark.asyncio
async def test_put_avatar_stores_bytes_and_public_path() -> None:
    client = MemoryObjectClient()
    settings = StorageSettings(
        endpoint="memory://test",
        bucket="avatars",
        access_key_id="test",
        secret_access_key="test-secret",
        key_prefix="objects",
    )
    store = AvatarObjectStore(settings=settings, client=client)
    payload = b"\x89PNG\r\n\x1a\n" + b"x" * 40
    stored = await store.put_avatar(
        asset_id="avatar_test",
        payload=payload,
        content_type="image/png",
        owner_account_id="account_owner",
        namespace="users/avatars",
    )
    assert stored.public_path == "/v1/media/avatars/avatar_test"
    assert "/accounts/account_owner/users/avatars/" in stored.object_key
    assert client.put_count == 1
    body = await store.read_bytes(
        object_key=stored.object_key,
        expected_digest=stored.content_digest,
        expected_size=stored.size_bytes,
    )
    assert body == payload

    client.objects[(settings.asset_bucket_name, stored.object_key)]["body"] = b"tampered"
    assert (
        await store.read_bytes(
            object_key=stored.object_key,
            expected_digest=stored.content_digest,
            expected_size=stored.size_bytes,
        )
        is None
    )


@pytest.mark.asyncio
async def test_asset_writes_reject_unowned_or_foreign_namespaces() -> None:
    store = AvatarObjectStore(
        settings=StorageSettings(
            endpoint="memory://test",
            artifact_bucket="artifacts",
            asset_bucket="assets",
            access_key_id="test",
            secret_access_key="test-secret",
        ),
        client=MemoryObjectClient(),
    )
    with pytest.raises(ValueError, match="namespace"):
        await store.put_avatar(
            asset_id="asset",
            payload=b"bytes",
            content_type="application/octet-stream",
            owner_account_id="account_owner",
            namespace="other/account",
        )
    with pytest.raises(ValueError, match="owner"):
        await store.put_avatar(
            asset_id="asset",
            payload=b"bytes",
            content_type="application/octet-stream",
            namespace="users/avatars",
        )
