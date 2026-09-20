# pyright: reportUnusedFunction=false

"""Publication journeys: the real CLI transport against the real `/v1` app.

Replaces the `#71`-mock journeys in `tests/unit/test_cli_publication.py`. Plan
create/status/bind/confirm run through the same ASGI app and PostgreSQL the
production server serves; the only patched seam is the object store — an
in-memory client standing in for S3, exactly as the platform tests do.

The session is a real device-bound credential: the test signs in through the
device flow because plan creation requires an active device on the session.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

import pytest
from tests.api.cli.conftest import WebApprover, issue_token
from tests.support.asgi_sync import SyncAsgiServer
from tests.support.publication_artifacts import (
    ARTIFACT_BY_DIGEST,
    CLEAN_ARTIFACT,
    DIGEST,
    PROJECTION_ARTIFACT,
    PROJECTION_DIGEST,
    publication_passport,
)

from ai_stp_cli.cloud import publication, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.publication import (
    PublicationConfirmRequest,
    PublicationPlanCreateRequest,
)
from ai_stp_platform.settings import StorageSettings
from ai_stp_platform.storage.memory import MemoryObjectClient
from ai_stp_platform.storage.object_store import ImmutableObjectStore

ApproverFactory = Callable[[], WebApprover]

STABLE_ID = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"


@pytest.fixture(autouse=True)
def _object_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Content-addressed bytes the plan binds against — S3 is the external seam."""
    client = MemoryObjectClient()
    settings = StorageSettings(
        endpoint="http://memory.test",
        bucket="test",
        access_key_id="test",
        secret_access_key="test",
    )
    store = ImmutableObjectStore(settings=settings, client=client)

    for digest, payload in [
        *ARTIFACT_BY_DIGEST.items(),
        (PROJECTION_DIGEST, PROJECTION_ARTIFACT),
    ]:
        key = store.key_for_digest(digest)
        client.objects[(settings.bucket, key)] = {
            "body": payload,
            "metadata": {
                "ai-stp-digest": digest,
                "ai-stp-size-bytes": str(len(payload)),
                "ai-stp-content-id": digest,
            },
            "size_bytes": len(payload),
        }

    async def _open() -> ImmutableObjectStore:
        return store

    async def _close(_store: ImmutableObjectStore | None) -> None:
        return None

    monkeypatch.setattr(
        "ai_stp_platform.publication_logic.open_env_object_store",
        _open,
    )
    monkeypatch.setattr(
        "ai_stp_platform.publication_logic.close_env_object_store",
        _close,
    )


def _sign_in(
    cli_endpoint: Endpoint,
    approver: WebApprover,
    monkeypatch: pytest.MonkeyPatch,
) -> session.Session:
    """A real device-bound session: begin → web approve → complete."""
    from ai_stp_cli.application import auth

    monkeypatch.setattr(auth, "endpoint", lambda: cli_endpoint)
    approval = auth.begin({"provider": "github"}).payload
    assert approval.user_code
    approved = approver.approve(approval.user_code)
    assert approved.status_code == 200, approved.text
    finished = auth.complete({}).payload
    assert finished.state == "authenticated"

    store, _warning = open_store()
    held = session.load(store)
    assert held is not None
    assert held.account_id == approver.account_id
    return held


def _create_request(
    held: session.Session,
    *,
    idempotency_key: str | None = None,
    extra_projection: bool = False,
) -> PublicationPlanCreateRequest:
    return PublicationPlanCreateRequest(
        object_kind="component",
        stable_id=STABLE_ID,
        version="1.0",
        content_digest=DIGEST,
        artifact_inventory=[],
        visibility="private",
        passport=publication_passport(
            owner_id=held.account_id,
            digest=DIGEST,
            extra_projection=extra_projection,
        ),
        attestations=[],
        idempotency_key=idempotency_key or secrets.token_hex(8),
        device_id=held.device_id,
    )


def test_plan_create_status_and_confirm_against_the_real_app(
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create → bind → status → confirm — the whole journey the corpus faked."""
    held = _sign_in(cli_endpoint, web_approver(), monkeypatch)

    planned = publication.create(cli_endpoint, held.access_token, _create_request(held))
    assert planned.plan_id.startswith("plan_")
    assert planned.state == "ready"

    # Confirm before the artifact bytes land is a typed validation refusal.
    with pytest.raises(CliFailure) as premature:
        publication.confirm(
            cli_endpoint,
            held.access_token,
            planned.plan_id,
            PublicationConfirmRequest(
                plan_hash=planned.plan_hash,
                confirmed=True,
                idempotency_key=secrets.token_hex(8),
            ),
        )
    assert premature.value.code == "AI_STP_VALIDATION_ERROR"

    bound = publication.bind(
        cli_endpoint,
        held.access_token,
        planned.plan_id,
        CLEAN_ARTIFACT,
        pause=lambda _seconds: None,
    )
    assert bound.plan_id == planned.plan_id

    shown = publication.status(cli_endpoint, held.access_token, planned.plan_id)
    assert shown.plan_hash == planned.plan_hash

    confirmed = publication.confirm(
        cli_endpoint,
        held.access_token,
        planned.plan_id,
        PublicationConfirmRequest(
            plan_hash=planned.plan_hash,
            confirmed=True,
            idempotency_key=secrets.token_hex(8),
        ),
    )
    assert confirmed.state == "validating"
    assert confirmed.plan_hash == planned.plan_hash


def test_bind_places_exact_artifact_bytes_the_plan_declared(
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The server re-hashes the bound bytes; the declared digest must match."""
    held = _sign_in(cli_endpoint, web_approver(), monkeypatch)
    planned = publication.create(cli_endpoint, held.access_token, _create_request(held))

    bound = publication.bind(
        cli_endpoint,
        held.access_token,
        planned.plan_id,
        CLEAN_ARTIFACT,
        pause=lambda _seconds: None,
    )
    assert bound.plan_id == planned.plan_id


def test_bind_refuses_bytes_that_do_not_match_the_declared_digest(
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real digest verification: wrong bytes are a typed validation refusal."""
    held = _sign_in(cli_endpoint, web_approver(), monkeypatch)
    planned = publication.create(cli_endpoint, held.access_token, _create_request(held))

    with pytest.raises(CliFailure) as raised:
        publication.bind(
            cli_endpoint,
            held.access_token,
            planned.plan_id,
            b"not-the-declared-artifact",
            pause=lambda _seconds: None,
        )
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_declared_projection_artifacts_bind_to_their_digest(
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A passport declaring a projection requires its bytes before confirm."""
    held = _sign_in(cli_endpoint, web_approver(), monkeypatch)
    planned = publication.create(
        cli_endpoint,
        held.access_token,
        _create_request(held, extra_projection=True),
    )

    bound = publication.bind(
        cli_endpoint,
        held.access_token,
        planned.plan_id,
        CLEAN_ARTIFACT,
        pause=lambda _seconds: None,
    )
    assert bound.plan_id == planned.plan_id

    projected = publication.bind_projection(
        cli_endpoint,
        held.access_token,
        planned.plan_id,
        PROJECTION_DIGEST,
        PROJECTION_ARTIFACT,
        pause=lambda _seconds: None,
    )
    assert projected.plan_id == planned.plan_id

    confirmed = publication.confirm(
        cli_endpoint,
        held.access_token,
        planned.plan_id,
        PublicationConfirmRequest(
            plan_hash=planned.plan_hash,
            confirmed=True,
            idempotency_key=secrets.token_hex(8),
        ),
    )
    assert confirmed.state == "validating"


def test_create_replays_the_same_plan_for_one_idempotency_key(
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server-side dedup: a retried create must not open a second plan."""
    held = _sign_in(cli_endpoint, web_approver(), monkeypatch)
    key = secrets.token_hex(8)

    first = publication.create(
        cli_endpoint, held.access_token, _create_request(held, idempotency_key=key)
    )
    replayed = publication.create(
        cli_endpoint, held.access_token, _create_request(held, idempotency_key=key)
    )

    assert replayed.plan_id == first.plan_id
    assert replayed.plan_hash == first.plan_hash


def test_a_foreign_account_cannot_read_the_plan(
    cli_endpoint: Endpoint,
    cli_server: SyncAsgiServer,
    web_approver: ApproverFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = _sign_in(cli_endpoint, web_approver(), monkeypatch)
    planned = publication.create(cli_endpoint, held.access_token, _create_request(held))

    outsider = web_approver()
    token = issue_token(cli_server, outsider.account_id)

    with pytest.raises(CliFailure) as raised:
        publication.status(cli_endpoint, token, planned.plan_id)
    assert raised.value.code == "AI_STP_NOT_FOUND"
