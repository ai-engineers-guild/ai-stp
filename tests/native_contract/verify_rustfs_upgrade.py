"""Rehearse a RustFS image upgrade on one owned data volume before production uses it.

The old pinned image writes private artifact and asset objects; the new image starts
on the same volume and must return every object byte-identical and digest-verified,
keep both buckets private, keep owners apart and accept new writes. Production
volumes are never touched: the run owns its volume and removes it afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN, ImmutableObjectStore
from ai_stp_platform.storage.s3 import S3ObjectClient

PINNED = re.compile(r"rustfs/rustfs:[0-9][0-9A-Za-z.-]*@sha256:[0-9a-f]{64}")


def docker(*arguments: str) -> str:
    return subprocess.run(
        ["docker", *arguments], check=True, capture_output=True, text=True, timeout=300
    ).stdout.strip()


def start(image: str, volume: str, port: int, keys: tuple[str, str]) -> str:
    container = docker(
        "run",
        "--detach",
        "--publish",
        f"127.0.0.1:{port}:9000",
        "--env",
        f"RUSTFS_ACCESS_KEY={keys[0]}",
        "--env",
        f"RUSTFS_SECRET_KEY={keys[1]}",
        "--env",
        "RUSTFS_CONSOLE_ENABLE=false",
        "--volume",
        f"{volume}:/data",
        image,
    )
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=2).status_code == 200:
                return container
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise TimeoutError(f"{image} did not report storage readiness")


def stop(container: str) -> None:
    docker("stop", "--time", "30", container)
    docker("rm", container)


def settings(port: int, keys: tuple[str, str]) -> StorageSettings:
    return StorageSettings(
        endpoint=f"http://127.0.0.1:{port}",
        artifact_bucket="ai-stp-artifacts",
        asset_bucket="ai-stp-assets",
        access_key_id=keys[0],
        secret_access_key=keys[1],
        key_prefix="rehearsal",
    )


async def seed(config: StorageSettings) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    async with S3ObjectClient(config) as client:
        await client.ensure_buckets()
        for bucket in [config.artifact_bucket_name, config.asset_bucket_name]:
            store = ImmutableObjectStore(settings=config, client=client, bucket=bucket)
            for owner in ["account_first", "account_second"]:
                for size in [1, 4096, 5 * 1024 * 1024 + 7]:
                    payload = (bucket + owner).encode() * (size // 16 + 1)
                    payload = payload[:size]
                    digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, payload)
                    stored = await store.put_immutable(
                        payload,
                        expected_digest=digest,
                        expected_size=size,
                        owner_account_id=owner,
                    )
                    records.append(
                        {"bucket": bucket, "key": stored.key, "digest": digest, "size": size}
                    )
    assert len({(record["bucket"], record["key"]) for record in records}) == len(records)
    return records


async def verify(config: StorageSettings, records: list[dict[str, Any]]) -> None:
    async with S3ObjectClient(config) as client:
        for record in records:
            store = ImmutableObjectStore(settings=config, client=client, bucket=record["bucket"])
            payload = await store.read_verified(
                object_key=record["key"],
                expected_digest=record["digest"],
                expected_size=record["size"],
            )
            assert payload is not None and len(payload) == record["size"]
        # A new write after the upgrade succeeds and reads back.
        store = ImmutableObjectStore(settings=config, client=client)
        fresh = b"written after the upgrade"
        digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, fresh)
        stored = await store.put_immutable(
            fresh, expected_digest=digest, expected_size=len(fresh), owner_account_id="account_new"
        )
        assert (
            await store.read_verified(
                object_key=stored.key, expected_digest=digest, expected_size=len(fresh)
            )
            == fresh
        )
    async with httpx.AsyncClient() as anonymous:
        for record in records[:: len(records) // 4]:
            response = await anonymous.get(f"{config.endpoint}/{record['bucket']}/{record['key']}")
            assert response.status_code in {401, 403}, response.status_code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", required=True, help="currently pinned image reference")
    parser.add_argument("--new", required=True, help="candidate image reference")
    parser.add_argument("--proof", type=Path, required=True)
    arguments = parser.parse_args()
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Use a disposable CI runner"
    for image in [arguments.old, arguments.new]:
        assert PINNED.fullmatch(image), "Images must be pinned by tag and digest"
    keys = ("rehearsal" + secrets.token_hex(8), secrets.token_hex(24))
    volume = "ai-stp-rustfs-rehearsal-" + secrets.token_hex(6)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = settings(port, keys)
    docker("volume", "create", volume)
    container = None
    try:
        container = start(arguments.old, volume, port, keys)
        records = asyncio.run(seed(config))
        asyncio.run(verify(config, records))
        stop(container)
        container = start(arguments.new, volume, port, keys)
        asyncio.run(verify(config, records))
        stop(container)
        container = None
    finally:
        if container is not None:
            subprocess.run(["docker", "rm", "--force", container], check=False, timeout=120)
        subprocess.run(["docker", "volume", "rm", volume], check=False, timeout=120)
    proof = {
        "schema_version": 1,
        "evidence_kind": "rustfs_existing_volume_upgrade",
        "old_image": arguments.old,
        "new_image": arguments.new,
        "objects": len(records),
        "buckets": 2,
        "owners_per_bucket": 2,
        "largest_object_bytes": max(record["size"] for record in records),
        "objects_digest_verified_after_upgrade": True,
        "anonymous_reads_refused_after_upgrade": True,
        "new_writes_after_upgrade": True,
        "production_volume_used": False,
    }
    arguments.proof.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
