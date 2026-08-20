"""Resolve publication artifact bytes for safety validate (download + rehash)."""

from __future__ import annotations

from typing import Protocol, cast

from pydantic import ValidationError

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.storage.object_store import (
    ARTIFACT_DIGEST_DOMAIN,
    ImmutableObjectStore,
    ObjectIntegrityError,
)
from ai_stp_platform.storage.s3 import S3ObjectClient


class ArtifactBytesSource(Protocol):
    async def fetch_bytes(self, content_digest: str, size_bytes: int | None) -> bytes | None: ...


class StoreArtifactBytesSource:
    """Fetch verified bytes from ImmutableObjectStore."""

    def __init__(self, store: ImmutableObjectStore) -> None:
        self._store = store

    async def fetch_bytes(self, content_digest: str, size_bytes: int | None) -> bytes | None:
        return await self._store.read_by_digest(content_digest, expected_size=size_bytes)


class BytesArtifactBytesSource:
    """Injected bytes (tests); re-verifies digest on fetch."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def fetch_bytes(self, content_digest: str, size_bytes: int | None) -> bytes | None:
        del size_bytes
        actual = digest_bytes(ARTIFACT_DIGEST_DOMAIN, self._payload)
        if actual != content_digest:
            raise ObjectIntegrityError(
                f"injected artifact digest mismatch: expected {content_digest}, got {actual}"
            )
        return self._payload


_OWNED_CLIENTS: dict[int, S3ObjectClient] = {}


async def open_env_object_store() -> ImmutableObjectStore | None:
    """Open store from AI_STP_STORAGE_* env when configured; else None."""
    try:
        from ai_stp_platform.settings import StorageSettings
    except Exception:
        return None
    try:
        # BaseSettings reads AI_STP_STORAGE_* from the environment.
        settings = StorageSettings()  # pyright: ignore[reportCallIssue]
    except (ValidationError, Exception):
        return None
    client = S3ObjectClient(settings)
    await client.__aenter__()
    store = ImmutableObjectStore(settings=settings, client=client)
    _OWNED_CLIENTS[id(store)] = client
    return store


async def close_env_object_store(store: ImmutableObjectStore | None) -> None:
    if store is None:
        return
    client = _OWNED_CLIENTS.pop(id(store), None)
    if client is not None:
        await client.__aexit__(None, None, None)


def passport_artifact_size(passport: dict[str, object]) -> int | None:
    art = passport.get("artifact")
    if isinstance(art, dict):
        size = cast(dict[str, object], art).get("size_bytes")
        if isinstance(size, int):
            return size
    return None
