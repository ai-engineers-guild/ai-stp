# pyright: reportUnusedFunction=false

"""Artifact fetch journeys: verified bytes from the real `/v1` catalog route.

Replaces the `#71`-mock journeys in `tests/unit/test_cli_artifact.py`. The
bytes come out of the app's real object store — a `MemoryObjectClient` in the
test environment — behind the same metadata, location and digest verification
the production route performs. The passport document is the shared schema-valid
`publication_passport`, because the version route validates it before answering.

What stays in the unit file is client-local: truncation limits, stream
timeouts, cache poisoning and refusal mapping.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.api.cli.conftest import issue_token
from tests.support.asgi_sync import SyncAsgiServer
from tests.support.publication_artifacts import (
    CLEAN_ARTIFACT,
    DIGEST,
    publication_passport,
)

from ai_stp_cli.cloud import catalog
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.ids import new_id
from ai_stp_passports.versions import ArtifactRef, ComponentVersionPassport
from ai_stp_platform.models import Account, CatalogMetadata, ObjectLocation
from ai_stp_platform.publication_logic import passport_digest as platform_passport_digest
from ai_stp_platform.storage.memory import MemoryObjectClient
from ai_stp_platform.storage.object_store import ImmutableObjectStore

REF = ArtifactRef(digest=DIGEST, size_bytes=len(CLEAN_ARTIFACT))


def _published_object(cli_server: SyncAsgiServer, *, visibility: str = "public") -> tuple[str, str]:
    """A published catalog row whose artifact bytes sit in the app's memory store."""
    settings = cli_server.app.state.settings.storage
    client = cli_server.app.state.object_client
    assert isinstance(client, MemoryObjectClient)
    store = ImmutableObjectStore(settings=settings, client=client)
    owner = new_id("account")
    # The row carries the validated model dump, exactly as publication wrote
    # it: the served document and its catalogued digest share one canonical
    # form.
    passport = ComponentVersionPassport.model_validate(
        publication_passport(owner_id=owner)
    ).model_dump(mode="json")
    stable_id = str(passport["stable_id"])
    key = store.key_for_digest(DIGEST, owner_account_id=owner)
    client.objects[(store.bucket, key)] = {
        "body": CLEAN_ARTIFACT,
        "metadata": {
            "ai-stp-digest": DIGEST,
            "ai-stp-size-bytes": str(len(CLEAN_ARTIFACT)),
            "ai-stp-content-id": DIGEST,
        },
        "size_bytes": len(CLEAN_ARTIFACT),
    }
    sessionmaker = cli_server.app.state.sessionmaker

    async def seed() -> None:
        async with sessionmaker() as db:
            db.add(Account(id=owner))
            metadata = CatalogMetadata(
                owner_account_id=owner,
                object_kind="component",
                stable_id=stable_id,
                version=str(passport["version"]),
                current_revision_id=str(passport["revision_id"]),
                visibility=visibility,
                lifecycle_state="active",
                name="artifact-fixture",
                published_at=datetime.now(UTC),
                trust_lane="authoritative",
                passport_digest=platform_passport_digest(
                    ComponentVersionPassport.model_validate(passport)
                ),
                passport_document=passport,
            )
            db.add(metadata)
            await db.flush()
            db.add(
                ObjectLocation(
                    catalog_metadata_id=metadata.id,
                    purpose="artifact",
                    bucket=store.bucket,
                    owner_account_id=owner,
                    object_key=key,
                    digest=DIGEST,
                    content_id=DIGEST,
                    size_bytes=len(CLEAN_ARTIFACT),
                )
            )
            await db.commit()

    cli_server.call(seed)
    return owner, stable_id


def test_the_versioned_surface_serves_verified_bytes(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
) -> None:
    """Fetch verifies the bytes against the declared digest, then caches them."""
    _owner, stable_id = _published_object(cli_server)

    path = catalog.fetch_artifact(cli_endpoint, "component", stable_id, "1.0", REF)
    assert path.read_bytes() == CLEAN_ARTIFACT

    # A second fetch is the content-addressed cache, not the network.
    cached = catalog.fetch_artifact(cli_endpoint, "component", stable_id, "1.0", REF)
    assert cached == path


def test_a_private_artifact_answers_the_owners_bearer(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
) -> None:
    """Private objects are invisible anonymously and readable by their owner."""
    owner, stable_id = _published_object(cli_server, visibility="private")

    with pytest.raises(CliFailure) as refused:
        catalog.fetch_artifact(cli_endpoint, "component", stable_id, "1.0", REF)
    assert refused.value.code == "AI_STP_NOT_FOUND"

    token = issue_token(cli_server, owner)
    path = catalog.fetch_artifact(
        cli_endpoint, "component", stable_id, "1.0", REF, access_token=token
    )
    assert path.read_bytes() == CLEAN_ARTIFACT


def test_the_fetch_command_reports_the_verified_path_then_cache(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`catalog fetch` end to end: version view → verified bytes → `cache`."""
    from ai_stp_cli.application import catalog as registry_commands

    _owner, stable_id = _published_object(cli_server)
    monkeypatch.setattr(registry_commands, "endpoint", lambda: cli_endpoint)

    asked = {"kind": "component", "id": stable_id, "version": "1.0"}
    first = registry_commands.fetch(asked).payload
    assert first.source == "online"
    assert first.digest == DIGEST
    assert first.size_bytes == len(CLEAN_ARTIFACT)
    assert first.path and not first.path.startswith("/home")

    second = registry_commands.fetch(asked).payload
    assert second.source == "cache"
