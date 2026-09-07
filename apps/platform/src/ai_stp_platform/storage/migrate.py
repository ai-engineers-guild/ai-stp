"""Copy legacy objects into owner-scoped buckets without deleting rollback data."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.db import make_engine, make_sessionmaker
from ai_stp_platform.models import AvatarAsset, CatalogMetadata, ComponentMedia, ObjectLocation
from ai_stp_platform.settings import DatabaseSettings, StorageSettings
from ai_stp_platform.storage.object_store import (
    ARTIFACT_DIGEST_DOMAIN,
    ImmutableObjectStore,
    ObjectClient,
    ObjectIntegrityError,
)
from ai_stp_platform.storage.s3 import S3ObjectClient


class StorageMigrationError(RuntimeError):
    """Legacy bytes cannot be copied safely."""


@dataclass(frozen=True)
class MigratedObjectCounts:
    artifacts: int = 0
    avatars: int = 0
    component_media: int = 0


async def _legacy_bytes(
    store: ImmutableObjectStore,
    *,
    bucket: str,
    key: str,
    digest: str,
    size: int,
    label: str,
) -> bytes:
    try:
        payload = await store.read_verified(
            object_key=key,
            expected_digest=digest,
            expected_size=size,
            bucket=bucket,
        )
    except ObjectIntegrityError as error:
        raise StorageMigrationError(f"{label} failed integrity verification") from error
    if payload is None:
        raise StorageMigrationError(f"{label} is missing")
    return payload


async def migrate_legacy_objects(
    session: AsyncSession,
    *,
    settings: StorageSettings,
    client: ObjectClient,
) -> MigratedObjectCounts:
    """Idempotently copy legacy keys, then atomically bind their new locations."""
    artifact_store = ImmutableObjectStore(settings=settings, client=client)
    asset_store = ImmutableObjectStore(
        settings=settings,
        client=client,
        bucket=settings.asset_bucket_name,
    )
    legacy_bucket = settings.bucket or settings.artifact_bucket_name
    artifact_count = avatar_count = media_count = 0

    artifact_rows = (
        await session.execute(
            select(ObjectLocation, CatalogMetadata)
            .join(CatalogMetadata, CatalogMetadata.id == ObjectLocation.catalog_metadata_id)
            .where(ObjectLocation.purpose == "artifact")
        )
    ).all()
    for location, metadata in artifact_rows:
        owner = metadata.owner_account_id
        if location.owner_account_id not in {None, owner}:
            raise StorageMigrationError(f"artifact {location.id} has the wrong owner")
        target = artifact_store.key_for_digest(location.digest, owner_account_id=owner)
        if location.bucket == settings.artifact_bucket_name and location.object_key == target:
            try:
                current = await artifact_store.read_verified(
                    object_key=target,
                    expected_digest=location.digest,
                    expected_size=location.size_bytes,
                )
            except ObjectIntegrityError:
                current = None
            if current is not None:
                continue
        payload = await _legacy_bytes(
            artifact_store,
            bucket=location.bucket or legacy_bucket,
            key=location.object_key,
            digest=location.digest,
            size=location.size_bytes,
            label=f"artifact {location.id}",
        )
        stored = await artifact_store.put_immutable(
            payload,
            expected_digest=location.digest,
            expected_size=location.size_bytes,
            owner_account_id=owner,
        )
        location.bucket = stored.bucket
        location.owner_account_id = owner
        location.object_key = stored.key
        artifact_count += 1

    avatars = list(
        await session.scalars(
            select(AvatarAsset).where(
                AvatarAsset.object_key.is_not(None),
                AvatarAsset.state == "ready",
            )
        )
    )
    for avatar in avatars:
        assert avatar.object_key is not None
        digest = avatar.content_digest
        if digest is None:
            raw = await client.get_object_bytes(bucket=legacy_bucket, key=avatar.object_key)
            if raw is None or len(raw) != avatar.size_bytes:
                raise StorageMigrationError(f"avatar {avatar.id} is missing or has the wrong size")
            digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, raw)
        target = asset_store.key_for_digest(
            digest,
            owner_account_id=avatar.account_id,
            namespace="users/avatars",
        )
        if avatar.content_digest == digest and avatar.object_key == target:
            try:
                current = await asset_store.read_verified(
                    object_key=target,
                    expected_digest=digest,
                    expected_size=avatar.size_bytes,
                )
            except ObjectIntegrityError:
                current = None
            if current is not None:
                continue
        payload = await _legacy_bytes(
            asset_store,
            bucket=legacy_bucket,
            key=avatar.object_key,
            digest=digest,
            size=avatar.size_bytes,
            label=f"avatar {avatar.id}",
        )
        stored = await asset_store.put_immutable(
            payload,
            expected_digest=digest,
            expected_size=avatar.size_bytes,
            owner_account_id=avatar.account_id,
            namespace="users/avatars",
        )
        avatar.object_key = stored.key
        avatar.content_digest = stored.digest
        avatar_count += 1

    media = list(
        await session.scalars(
            select(ComponentMedia).where(
                ComponentMedia.object_key.is_not(None),
                ComponentMedia.source_type == "upload",
                ComponentMedia.state == "ready",
            )
        )
    )
    for item in media:
        assert item.object_key is not None
        if item.size_bytes is None:
            raise StorageMigrationError(f"component media {item.id} has no size")
        size = item.size_bytes
        if item.content_digest is not None:
            target = asset_store.key_for_digest(
                item.content_digest,
                owner_account_id=item.owner_account_id,
                namespace=f"components/{item.stable_id}/media",
            )
            if item.object_key == target:
                try:
                    current = await asset_store.read_verified(
                        object_key=target,
                        expected_digest=item.content_digest,
                        expected_size=size,
                    )
                except ObjectIntegrityError:
                    current = None
                if current is not None:
                    continue
        raw = await client.get_object_bytes(bucket=legacy_bucket, key=item.object_key)
        if raw is None or len(raw) != size:
            raise StorageMigrationError(
                f"component media {item.id} is missing or has the wrong size"
            )
        digest = item.content_digest or digest_bytes(ARTIFACT_DIGEST_DOMAIN, raw)
        if digest_bytes(ARTIFACT_DIGEST_DOMAIN, raw) != digest:
            raise StorageMigrationError(f"component media {item.id} failed integrity verification")
        stored = await asset_store.put_immutable(
            raw,
            expected_digest=digest,
            expected_size=size,
            owner_account_id=item.owner_account_id,
            namespace=f"components/{item.stable_id}/media",
        )
        item.object_key = stored.key
        item.content_digest = stored.digest
        media_count += 1

    await session.commit()
    return MigratedObjectCounts(artifact_count, avatar_count, media_count)


async def _main() -> None:
    database = DatabaseSettings()  # pyright: ignore[reportCallIssue]
    storage = StorageSettings()  # pyright: ignore[reportCallIssue]
    engine = make_engine(database)
    try:
        async with S3ObjectClient(storage) as client, make_sessionmaker(engine)() as session:
            await client.ensure_buckets()
            counts = await migrate_legacy_objects(session, settings=storage, client=client)
        print(json.dumps(asdict(counts), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
