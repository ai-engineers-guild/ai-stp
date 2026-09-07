"""Avatar media writes: normalize metadata and put immutable object bytes."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage.object_store import (
    ARTIFACT_DIGEST_DOMAIN,
    ImmutableObjectStore,
    ObjectClient,
    ObjectIntegrityError,
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
        self._store = ImmutableObjectStore(
            settings=settings, client=client, bucket=settings.asset_bucket_name
        )
        self._public_path_prefix = public_path_prefix.rstrip("/")

    async def put_avatar(
        self,
        *,
        asset_id: str,
        payload: bytes,
        content_type: str,
        owner_account_id: str | None = None,
        namespace: str = "avatars",
    ) -> StoredAvatar:
        _validate_asset_namespace(namespace, owner_account_id)
        digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
        stored: StoredObject = await self._store.put_immutable(
            payload,
            expected_digest=digest,
            expected_size=len(payload),
            owner_account_id=owner_account_id,
            namespace=namespace,
        )
        return StoredAvatar(
            asset_id=asset_id,
            object_key=stored.key,
            content_digest=stored.digest,
            size_bytes=stored.size_bytes,
            content_type=content_type,
            public_path=f"{self._public_path_prefix}/{asset_id}",
        )

    async def read_bytes(
        self,
        *,
        object_key: str,
        expected_digest: str | None = None,
        expected_size: int | None = None,
    ) -> bytes | None:
        if expected_digest is not None and expected_size is not None:
            try:
                return await self._store.read_verified(
                    object_key=object_key,
                    expected_digest=expected_digest,
                    expected_size=expected_size,
                )
            except ObjectIntegrityError:
                return None
        get = getattr(self._client, "get_object_bytes", None)
        if get is None:
            return None
        return await get(bucket=self._store.bucket, key=object_key)


_COMPONENT_NAMESPACE = re.compile(r"^components/[A-Za-z0-9_-]+/media$")


def _validate_asset_namespace(namespace: str, owner_account_id: str | None) -> None:
    """Keep asset writes inside the three server-owned namespace families."""
    if namespace == "users/avatars" or _COMPONENT_NAMESPACE.fullmatch(namespace):
        if not owner_account_id:
            raise ValueError("owner account is required for user or component assets")
        return
    if namespace.startswith("platform/") and namespace != "platform/":
        if owner_account_id is not None:
            raise ValueError("platform assets cannot be owned by an account")
        return
    raise ValueError("asset namespace is not allowed")
