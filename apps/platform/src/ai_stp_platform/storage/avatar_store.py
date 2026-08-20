"""Avatar media writes: normalize metadata and put immutable object bytes."""

from __future__ import annotations

from dataclasses import dataclass

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage.object_store import (
    ARTIFACT_DIGEST_DOMAIN,
    ImmutableObjectStore,
    ObjectClient,
    StoredObject,
)


@dataclass(frozen=True)
class StoredAvatar:
    """Processed avatar stored under content-addressed object key."""

    asset_id: str
    object_key: str
    content_digest: str
    size_bytes: int
    content_type: str
    public_path: str


class AvatarObjectStore:
    """Writes avatar bytes via ImmutableObjectStore and builds public paths."""

    def __init__(
        self,
        *,
        settings: StorageSettings,
        client: ObjectClient,
        public_path_prefix: str = "/v1/media/avatars",
    ) -> None:
        self._settings = settings
        self._client = client
        self._store = ImmutableObjectStore(settings=settings, client=client)
        self._public_path_prefix = public_path_prefix.rstrip("/")

    async def put_avatar(
        self,
        *,
        asset_id: str,
        payload: bytes,
        content_type: str,
    ) -> StoredAvatar:
        digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
        stored: StoredObject = await self._store.put_immutable(
            payload,
            expected_digest=digest,
            expected_size=len(payload),
        )
        return StoredAvatar(
            asset_id=asset_id,
            object_key=stored.key,
            content_digest=stored.digest,
            size_bytes=stored.size_bytes,
            content_type=content_type,
            public_path=f"{self._public_path_prefix}/{asset_id}",
        )

    async def read_bytes(self, *, object_key: str) -> bytes | None:
        get = getattr(self._client, "get_object_bytes", None)
        if get is None:
            return None
        return await get(bucket=self._settings.bucket, key=object_key)
