"""Resolve publication artifact bytes for safety validate (download + rehash)."""

from __future__ import annotations

import weakref
from typing import Protocol, cast

from pydantic import ValidationError

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.logging import get_logger
from ai_stp_platform.storage.object_store import (
    ARTIFACT_DIGEST_DOMAIN,
    ImmutableObjectStore,
    ObjectIntegrityError,
)
from ai_stp_platform.storage.s3 import S3ObjectClient

_log = get_logger("artifact_fetch")


class ArtifactBytesSource(Protocol):
    async def fetch_bytes(self, content_digest: str, size_bytes: int | None) -> bytes | None: ...


class StoreArtifactBytesSource:
    """Fetch verified bytes from ImmutableObjectStore."""

    def __init__(
        self,
        store: ImmutableObjectStore,
        *,
        owner_account_id: str | None = None,
        allow_legacy_public: bool = False,
    ) -> None:
        self._store = store
        self._owner_account_id = owner_account_id
        self._allow_legacy_public = allow_legacy_public

    async def fetch_bytes(self, content_digest: str, size_bytes: int | None) -> bytes | None:
        payload = await self._store.read_by_digest(
            content_digest,
            expected_size=size_bytes,
            owner_account_id=self._owner_account_id,
        )
        if payload is None and self._allow_legacy_public:
            return await self._store.read_by_digest(content_digest, expected_size=size_bytes)
        return payload


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


# Keyed by the store object itself, never `id()`: a collected store's id can
# be reused by a new allocation, which would hand the wrong client to close.
# Weak keys mean a store nobody holds any longer stops owning its client.
_OWNED_CLIENTS: weakref.WeakKeyDictionary[ImmutableObjectStore, S3ObjectClient] = (
    weakref.WeakKeyDictionary()
)
_settings_failure_logged = False


async def open_env_object_store() -> ImmutableObjectStore | None:
    """Open store from AI_STP_STORAGE_* env when configured; else None."""
    global _settings_failure_logged
    from ai_stp_platform.settings import StorageSettings

    try:
        # BaseSettings reads AI_STP_STORAGE_* from the environment.
        settings = StorageSettings()  # pyright: ignore[reportCallIssue]
    except ValidationError as exc:
        # Missing env is the routine "not configured" answer; a *broken*
        # configuration must not pass as it. Log the reason once per process —
        # this path runs inside a scan that retries on every artifact.
        if not _settings_failure_logged:
            _settings_failure_logged = True
            _log.warning(
                "object_store_env_invalid",
                error_type=type(exc).__name__,
            )
        return None
    client = S3ObjectClient(settings)
    try:
        await client.__aenter__()
        await client.ensure_buckets()
    except Exception:
        # A half-opened client leaks its session when the caller never learns
        # it exists — `ensure_buckets` raising is exactly that case.
        await client.__aexit__(None, None, None)
        raise
    store = ImmutableObjectStore(settings=settings, client=client)
    _OWNED_CLIENTS[store] = client
    return store


async def close_env_object_store(store: ImmutableObjectStore | None) -> None:
    if store is None:
        return
    client = _OWNED_CLIENTS.pop(store, None)
    if client is not None:
        await client.__aexit__(None, None, None)


def passport_artifact_size(passport: dict[str, object]) -> int | None:
    art = passport.get("artifact")
    if isinstance(art, dict):
        size = cast(dict[str, object], art).get("size_bytes")
        if isinstance(size, int):
            return size
    return None
