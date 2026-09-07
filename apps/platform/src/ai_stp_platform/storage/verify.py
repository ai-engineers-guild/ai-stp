"""Verify every database-referenced object without exposing keys or bytes."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.models import AvatarAsset, CatalogMetadata, ComponentMedia, ObjectLocation
from ai_stp_platform.settings import DatabaseSettings, StorageSettings
from ai_stp_platform.storage.object_store import (
    ImmutableObjectStore,
    ObjectClient,
    ObjectIntegrityError,
)
from ai_stp_platform.storage.s3 import S3ObjectClient


class StorageVerificationError(RuntimeError):
    """A referenced object is absent, corrupt, or bound to the wrong owner."""


@dataclass(frozen=True)
class VerifiedObjectCounts:
    artifacts: int = 0
    avatars: int = 0
    component_media: int = 0


async def _verify(
    store: ImmutableObjectStore,
    *,
    object_key: str,
    digest: str | None,
    size: int | None,
    label: str,
    bucket: str | None = None,
) -> None:
    if not digest or size is None:
        raise StorageVerificationError(f"{label} has no digest or size")
    try:
        payload = await store.read_verified(
            object_key=object_key,
            expected_digest=digest,
            expected_size=size,
            bucket=bucket,
        )
    except ObjectIntegrityError as exc:
        raise StorageVerificationError(f"{label} failed integrity verification") from exc
    if payload is None:
        raise StorageVerificationError(f"{label} is missing")


async def verify_referenced_objects(
    session: AsyncSession,
    *,
    settings: StorageSettings,
    client: ObjectClient,
) -> VerifiedObjectCounts:
    """Read and hash every committed artifact and uploaded ready asset."""
    artifact_store = ImmutableObjectStore(settings=settings, client=client)
    asset_store = ImmutableObjectStore(
        settings=settings,
        client=client,
        bucket=settings.asset_bucket_name,
    )
    artifact_rows = (
        await session.execute(
            select(ObjectLocation, CatalogMetadata)
            .join(CatalogMetadata, CatalogMetadata.id == ObjectLocation.catalog_metadata_id)
            .where(ObjectLocation.purpose == "artifact")
        )
    ).all()
    for location, metadata in artifact_rows:
        if location.owner_account_id != metadata.owner_account_id:
            raise StorageVerificationError(f"artifact {location.id} has the wrong owner")
        expected_key = artifact_store.key_for_digest(
            location.digest, owner_account_id=metadata.owner_account_id
        )
        if location.bucket != settings.artifact_bucket_name or location.object_key != expected_key:
            raise StorageVerificationError(f"artifact {location.id} has a legacy location")
        await _verify(
            artifact_store,
            object_key=location.object_key,
            digest=location.digest,
            size=location.size_bytes,
            bucket=settings.artifact_bucket_name,
            label=f"artifact {location.id}",
        )

    avatars = list(
        await session.scalars(
            select(AvatarAsset).where(
                AvatarAsset.state == "ready",
                AvatarAsset.object_key.is_not(None),
            )
        )
    )
    for avatar in avatars:
        assert avatar.object_key is not None
        if not avatar.content_digest:
            raise StorageVerificationError(f"avatar {avatar.id} has no digest or size")
        expected_key = asset_store.key_for_digest(
            avatar.content_digest,
            owner_account_id=avatar.account_id,
            namespace="users/avatars",
        )
        if avatar.object_key != expected_key:
            raise StorageVerificationError(f"avatar {avatar.id} has a legacy location")
        await _verify(
            asset_store,
            object_key=avatar.object_key,
            digest=avatar.content_digest,
            size=avatar.size_bytes,
            label=f"avatar {avatar.id}",
        )

    media = list(
        await session.scalars(
            select(ComponentMedia).where(
                ComponentMedia.state == "ready",
                ComponentMedia.source_type == "upload",
                ComponentMedia.object_key.is_not(None),
            )
        )
    )
    for item in media:
        assert item.object_key is not None
        if not item.content_digest or item.size_bytes is None:
            raise StorageVerificationError(f"component media {item.id} has no digest or size")
        expected_key = asset_store.key_for_digest(
            item.content_digest,
            owner_account_id=item.owner_account_id,
            namespace=f"components/{item.stable_id}/media",
        )
        if item.object_key != expected_key:
            raise StorageVerificationError(f"component media {item.id} has a legacy location")
        await _verify(
            asset_store,
            object_key=item.object_key,
            digest=item.content_digest,
            size=item.size_bytes,
            label=f"component media {item.id}",
        )
    return VerifiedObjectCounts(
        artifacts=len(artifact_rows),
        avatars=len(avatars),
        component_media=len(media),
    )


async def _main() -> None:
    database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
    storage = StorageSettings()  # pyright: ignore[reportCallIssue]
    engine = make_engine(database)
    try:
        async with (
            S3ObjectClient(storage) as client,
            make_sessionmaker(engine)() as session,
        ):
            counts = await verify_referenced_objects(
                session,
                settings=storage,
                client=client,
            )
        print(json.dumps(asdict(counts), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
