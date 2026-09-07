"""Verified, non-enumerating artifact reads for the public catalog."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from typing import Final, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.catalog_read import ObjectKind, get_visible_metadata
from ai_stp_platform.logging import get_logger
from ai_stp_platform.models import ObjectLocation
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


#: The lifecycle states whose bytes a caller may still fetch.
#:
#: `deprecated` is here and it is the whole point of the state. A published
#: `X.Y` is immutable and consumers pin exact versions — a setup passport pins
#: its components by exact digest — so refusing the bytes of a deprecated
#: version breaks every pin that already resolved, which is a far larger act
#: than an author saying "do not choose this next time". Deprecation is a
#: signal; `blocked` and `hidden` are the restrictions, and they stay out.
#:
#: Measured 2026-08-29 on the live catalogue before this changed: the read
#: surface already listed `deprecated` as public (`catalog_read.PUBLIC_LIFECYCLES`)
#: while this query required `active`, so metadata was readable and the bytes
#: were not. Two independent decisions about what one state means, neither
#: written down as a requirement. `SPEC-007` `REQ-730` now says which one holds.
INSTALLABLE_LIFECYCLES: Final[tuple[str, ...]] = ("active", "deprecated")


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
    account_id: str | None = None,
) -> bytes:
    """Authorize metadata first, then read and verify all bytes before response."""
    if object_kind not in {"component", "setup"}:
        raise ArtifactNotFound
    metadata = await get_visible_metadata(
        session,
        object_kind=cast(ObjectKind, object_kind),
        stable_id=stable_id,
        version=version,
        account_id=account_id,
    )
    if (
        metadata is None
        or metadata.lifecycle_state not in INSTALLABLE_LIFECYCLES
        or metadata.published_at is None
    ):
        raise ArtifactNotFound
    location = await session.scalar(
        select(ObjectLocation).where(
            ObjectLocation.catalog_metadata_id == metadata.id,
            ObjectLocation.purpose == "artifact",
        )
    )
    if location is None:
        raise _corrupt(
            "reachable version has no artifact location",
            object_kind=object_kind,
            stable_id=stable_id,
            version=version,
        )
    if location.owner_account_id is not None and (
        location.owner_account_id != metadata.owner_account_id
        or location.bucket != store.bucket
        or location.object_key
        != store.key_for_digest(
            location.digest,
            owner_account_id=metadata.owner_account_id,
        )
    ):
        raise _corrupt(
            "stored object location is not bound to its owner",
            object_kind=object_kind,
            stable_id=stable_id,
            version=version,
        )
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
            bucket=location.bucket or store.bucket,
        )
    except ObjectIntegrityError as exc:
        raise fail("stored bytes failed verification") from exc
    if payload is None:
        # Metadata promises bytes the store does not hold. The version is still
        # reachable, so this is a dangling reference, not a miss.
        raise fail("stored object is missing for a reachable version")
    return payload
