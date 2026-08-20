"""Verified, non-enumerating artifact reads for the public catalog."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.logging import get_logger
from ai_stp_platform.models import CatalogMetadata, ObjectLocation
from ai_stp_platform.storage.object_store import ImmutableObjectStore, ObjectIntegrityError

_log = get_logger("catalog")


class ArtifactNotFound(LookupError):
    """No public artifact is reachable under this exact version."""


class ArtifactCorrupt(RuntimeError):
    """The version is reachable, but its bytes fail their integrity boundary.

    Separate from ArtifactNotFound for the reason ADR-0079 gives for metadata:
    the object exists and is public, and answering a miss sends the caller
    looking elsewhere for something that is right there. REQ-2108 requires the
    conflict to be refused by a typed error, and "does not exist" is the wrong
    type for bytes that do exist and disagree with their passport.
    """


def _corrupt(reason: str, *, object_kind: str, stable_id: str, version: str) -> ArtifactCorrupt:
    """Record the integrity failure, then hand back the error to raise."""
    _log.error(
        "catalog_artifact_integrity_failed",
        reason=reason,
        object_kind=object_kind,
        stable_id=stable_id,
        version=version,
    )
    return ArtifactCorrupt(reason)


async def read_public_artifact(
    session: AsyncSession,
    *,
    store: ImmutableObjectStore,
    object_kind: str,
    stable_id: str,
    version: str,
) -> bytes:
    """Authorize metadata first, then read and verify all bytes before response."""
    result = await session.execute(
        select(CatalogMetadata, ObjectLocation)
        .join(ObjectLocation, ObjectLocation.catalog_metadata_id == CatalogMetadata.id)
        .where(
            CatalogMetadata.object_kind == object_kind,
            CatalogMetadata.stable_id == stable_id,
            CatalogMetadata.version == version,
            CatalogMetadata.visibility == "public",
            CatalogMetadata.lifecycle_state == "active",
            CatalogMetadata.published_at.is_not(None),
            ObjectLocation.purpose == "artifact",
        )
    )
    row = result.one_or_none()
    if row is None:
        raise ArtifactNotFound
    metadata, location = row
    fail = partial(_corrupt, object_kind=object_kind, stable_id=stable_id, version=version)
    passport = metadata.passport_document
    if not isinstance(passport, Mapping):
        raise fail("passport document is not an object")
    document = cast(Mapping[str, object], passport)
    artifact = document.get("artifact")
    if not isinstance(artifact, Mapping):
        raise fail("passport declares no artifact")
    declared = cast(Mapping[str, object], artifact)
    if (
        declared.get("digest") != location.digest
        or declared.get("size_bytes") != location.size_bytes
    ):
        raise fail("stored object disagrees with the declared artifact")
    try:
        payload = await store.read_verified(
            object_key=location.object_key,
            expected_digest=location.digest,
            expected_size=location.size_bytes,
        )
    except ObjectIntegrityError as exc:
        raise fail("stored bytes failed verification") from exc
    if payload is None:
        # Metadata promises bytes the store does not hold. The version is still
        # reachable, so this is a dangling reference, not a miss.
        raise fail("stored object is missing for a reachable version")
    return payload
