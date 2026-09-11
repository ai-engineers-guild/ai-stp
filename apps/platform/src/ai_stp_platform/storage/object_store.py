"""Immutable RustFS/S3 object writes (SPEC-020 REQ-2005/REQ-2006)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.settings import StorageSettings

ARTIFACT_DIGEST_DOMAIN = "ai-stp:artifact:v1"


class ObjectIntegrityError(ValueError):
    """Object bytes do not match the caller's declared digest or size."""


class ObjectConflict(RuntimeError):
    """A different object already exists at the content-addressed key."""


@dataclass(frozen=True)
class StoredObject:
    """Result of an immutable object write."""

    bucket: str
    key: str
    digest: str
    content_id: str
    size_bytes: int
    created: bool


class ObjectClient(Protocol):
    """Minimal async S3-compatible operations used by the storage adapter."""

    async def head_object(self, *, bucket: str, key: str) -> dict[str, object] | None: ...

    async def put_object(
        self,
        *,
        bucket: str,
        key: str,
        body: bytes,
        metadata: dict[str, str],
    ) -> None: ...

    async def get_object_bytes(self, *, bucket: str, key: str) -> bytes | None: ...


def content_key(
    settings: StorageSettings,
    digest: str,
    *,
    owner_account_id: str | None = None,
    organization_id: str | None = None,
    namespace: str | None = None,
) -> str:
    """Build an owner-scoped content-addressed key."""
    prefix = settings.key_prefix.strip("/")
    if owner_account_id is not None and organization_id is not None:
        raise ValueError("object key accepts either account or organization scope")
    if organization_id is not None:
        if "/" in organization_id or not organization_id.startswith("organization_"):
            raise ValueError("invalid organization id for object key")
        scope = namespace.strip("/") if namespace else "artifacts"
        parts = scope.split("/")
        if not scope or any(not part or part in {".", ".."} for part in parts):
            raise ValueError("invalid object namespace")
        return (
            f"{prefix}/organizations/{organization_id}/{scope}/sha256/"
            f"{digest.removeprefix('sha256:')}"
        )
    if owner_account_id is None:
        return f"{prefix}/sha256/{digest.removeprefix('sha256:')}"
    if "/" in owner_account_id or not owner_account_id:
        raise ValueError("invalid owner account id for object key")
    scope = namespace.strip("/") if namespace else "artifacts"
    parts = scope.split("/")
    if not scope or any(not part or part in {".", ".."} for part in parts):
        raise ValueError("invalid object namespace")
    return f"{prefix}/accounts/{owner_account_id}/{scope}/sha256/{digest.removeprefix('sha256:')}"


def content_id(digest: str) -> str:
    """Return the storage-layer content identifier without rehashing bytes."""
    return digest


class ImmutableObjectStore:
    """Write bytes once, accepting repeated writes only for identical content."""

    def __init__(
        self,
        *,
        settings: StorageSettings,
        client: ObjectClient,
        bucket: str | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._bucket = bucket or getattr(settings, "artifact_bucket_name", None) or settings.bucket

    @property
    def settings(self) -> StorageSettings:
        return self._settings

    @property
    def client(self) -> ObjectClient:
        return self._client

    @property
    def bucket(self) -> str:
        return self._bucket

    def key_for_digest(
        self,
        digest: str,
        *,
        owner_account_id: str | None = None,
        organization_id: str | None = None,
        namespace: str | None = None,
    ) -> str:
        return content_key(
            self._settings,
            digest,
            owner_account_id=owner_account_id,
            organization_id=organization_id,
            namespace=namespace,
        )

    async def read_by_digest(
        self,
        content_digest: str,
        *,
        expected_size: int | None = None,
        owner_account_id: str | None = None,
        organization_id: str | None = None,
        namespace: str | None = None,
    ) -> bytes | None:
        """Read content-addressed bytes; verify size when known."""
        key = self.key_for_digest(
            content_digest,
            owner_account_id=owner_account_id,
            organization_id=organization_id,
            namespace=namespace,
        )
        if expected_size is not None:
            return await self.read_verified(
                object_key=key,
                expected_digest=content_digest,
                expected_size=expected_size,
            )
        payload = await self._client.get_object_bytes(
            bucket=self._bucket,
            key=key,
        )
        if payload is None:
            return None
        if digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload) != content_digest:
            raise ObjectIntegrityError("stored object digest does not match declared digest")
        return payload

    async def put_immutable(
        self,
        payload: bytes,
        *,
        expected_digest: str,
        expected_size: int,
        owner_account_id: str | None = None,
        organization_id: str | None = None,
        namespace: str | None = None,
    ) -> StoredObject:
        """Write bytes after digest/size verification and conflict checks."""
        actual_size = len(payload)
        actual_digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
        if actual_size != expected_size or actual_digest != expected_digest:
            raise ObjectIntegrityError("object bytes do not match declared digest and size")

        key = self.key_for_digest(
            actual_digest,
            owner_account_id=owner_account_id,
            organization_id=organization_id,
            namespace=namespace,
        )
        metadata = {
            "ai-stp-digest": actual_digest,
            "ai-stp-size-bytes": str(actual_size),
            "ai-stp-content-id": content_id(actual_digest),
        }
        if owner_account_id is not None:
            metadata["ai-stp-owner-account-id"] = owner_account_id
        if organization_id is not None:
            metadata["ai-stp-organization-id"] = organization_id
        existing = await self._client.head_object(bucket=self._bucket, key=key)
        if existing is not None:
            if _metadata_matches(existing, metadata):
                return StoredObject(
                    bucket=self._bucket,
                    key=key,
                    digest=actual_digest,
                    content_id=content_id(actual_digest),
                    size_bytes=actual_size,
                    created=False,
                )
            raise ObjectConflict("different object already exists at content-addressed key")

        await self._client.put_object(
            bucket=self._bucket,
            key=key,
            body=payload,
            metadata=metadata,
        )
        return StoredObject(
            bucket=self._bucket,
            key=key,
            digest=actual_digest,
            content_id=content_id(actual_digest),
            size_bytes=actual_size,
            created=True,
        )

    async def read_verified(
        self,
        *,
        object_key: str,
        expected_digest: str,
        expected_size: int,
        bucket: str | None = None,
        organization_id: str | None = None,
    ) -> bytes | None:
        """Read the complete object and verify integrity before returning bytes."""
        if organization_id is not None:
            expected_prefix = (
                f"{self._settings.key_prefix.strip('/')}/organizations/{organization_id}/"
            )
            if not object_key.startswith(expected_prefix):
                raise ObjectIntegrityError("object key does not belong to organization")
        payload = await self._client.get_object_bytes(
            bucket=bucket or self._bucket,
            key=object_key,
        )
        if payload is None:
            return None
        if len(payload) != expected_size:
            raise ObjectIntegrityError("stored object size does not match declared size")
        if digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload) != expected_digest:
            raise ObjectIntegrityError("stored object digest does not match declared digest")
        return payload


def _metadata_matches(existing: dict[str, object], expected: dict[str, str]) -> bool:
    metadata = existing.get("metadata")
    size = existing.get("size_bytes")
    if not isinstance(metadata, dict):
        return False
    meta = cast(dict[str, object], metadata)
    return (
        all(meta.get(key) == value for key, value in expected.items())
        and str(size) == expected["ai-stp-size-bytes"]
    )
