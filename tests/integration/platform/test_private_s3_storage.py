"""Real RustFS/S3 proof for private bucket and owner isolation."""

from __future__ import annotations

import os
from uuid import uuid4

import httpx
import pytest

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN, ImmutableObjectStore
from ai_stp_platform.storage.s3 import S3ObjectClient

pytestmark = [pytest.mark.platform, pytest.mark.s3]


def _settings() -> StorageSettings:
    names = {
        "endpoint": os.getenv("AI_STP_TEST_S3_ENDPOINT"),
        "artifact_bucket": os.getenv("AI_STP_TEST_S3_ARTIFACT_BUCKET"),
        "asset_bucket": os.getenv("AI_STP_TEST_S3_ASSET_BUCKET"),
        "access_key_id": os.getenv("AI_STP_TEST_S3_ACCESS_KEY_ID"),
        "secret_access_key": os.getenv("AI_STP_TEST_S3_SECRET_ACCESS_KEY"),
    }
    if any(value is None for value in names.values()):
        pytest.skip("dedicated AI_STP_TEST_S3_* settings are required")
    return StorageSettings(**names, key_prefix=f"tests/{uuid4().hex}")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_real_store_keeps_buckets_private_and_owners_separate() -> None:
    settings = _settings()
    payload = b"private component"
    digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
    async with S3ObjectClient(settings) as client:
        await client.ensure_buckets()
        artifacts = ImmutableObjectStore(settings=settings, client=client)
        first = await artifacts.put_immutable(
            payload,
            expected_digest=digest,
            expected_size=len(payload),
            owner_account_id="account_first",
        )
        second = await artifacts.put_immutable(
            payload,
            expected_digest=digest,
            expected_size=len(payload),
            owner_account_id="account_second",
        )
        assert first.key != second.key
        assert (
            await artifacts.read_verified(
                object_key=first.key,
                expected_digest=digest,
                expected_size=len(payload),
            )
            == payload
        )

    async with httpx.AsyncClient() as anonymous:
        response = await anonymous.get(
            f"{settings.endpoint.rstrip('/')}/{settings.artifact_bucket_name}/{first.key}"
        )
    assert response.status_code in {401, 403}
