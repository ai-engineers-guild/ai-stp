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
    )
    assert stored.public_path == "/v1/media/avatars/avatar_test"
    assert stored.object_key.startswith("objects/sha256/")
    assert client.put_count == 1
    body = await store.read_bytes(object_key=stored.object_key)
    assert body == payload
