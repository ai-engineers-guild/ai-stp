"""Owner workspace journeys: the real `/v1/owner` read surface.

Replaces the `/v1`-mock journeys in `tests/unit/test_cli_owner.py`. The seed
corpus assigns its objects to `SEED_OWNER_ACCOUNT_ID`, so a session issued for
that account exercises the ownership join for real — including the foreign
account seeing nothing. What stays in the unit file is the command registry
declaration, which never needed a server.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tests.api.cli.conftest import WebApprover, issue_token
from tests.support.asgi_sync import SyncAsgiServer
from tests.support.catalog_seed import FIXTURE_COMPONENT_ID, SEED_OWNER_ACCOUNT_ID

from ai_stp_cli.cloud import owner, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.owner import (
    CliOwnerObjectDetailView,
    OwnerObjectDetail,
    OwnerObjectListQuery,
    OwnerVersionDetail,
)


def test_the_owner_sees_its_seeded_objects(
    cli_server: SyncAsgiServer, cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    token = issue_token(cli_server, SEED_OWNER_ACCOUNT_ID)

    result = owner.list_objects(cli_endpoint, token, OwnerObjectListQuery(object_kind="component"))

    stable_ids = {item.stable_id for item in result.items}
    assert FIXTURE_COMPONENT_ID in stable_ids
    assert all(item.object_kind == "component" for item in result.items)


def test_object_and_version_detail_round_trip(
    cli_server: SyncAsgiServer, cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    token = issue_token(cli_server, SEED_OWNER_ACCOUNT_ID)

    detail = owner.object_detail(cli_endpoint, token, "component", FIXTURE_COMPONENT_ID)
    assert isinstance(detail, OwnerObjectDetail)
    assert {item.version for item in detail.versions} >= {"1.0", "1.2"}

    version = owner.version_detail(cli_endpoint, token, "component", FIXTURE_COMPONENT_ID, "1.2")
    assert isinstance(version, OwnerVersionDetail)
    assert version.version == "1.2"
    assert version.content_digest is not None


def test_a_foreign_account_sees_nothing(
    cli_endpoint: Endpoint,
    seeded_catalog: None,
    web_approver: Callable[[], WebApprover],
) -> None:
    """Ownership is server-side: another account gets an empty list, not data."""
    approver = web_approver()

    result = owner.list_objects(cli_endpoint, approver.token, OwnerObjectListQuery())
    assert result.items == []

    with pytest.raises(CliFailure) as raised:
        owner.object_detail(cli_endpoint, approver.token, "component", FIXTURE_COMPONENT_ID)
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_the_owner_command_converts_the_real_wire_view(
    cli_server: SyncAsgiServer,
    cli_endpoint: Endpoint,
    seeded_catalog: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command layer's wire→view conversion, fed by the real response."""
    from ai_stp_cli.commands import owner as command

    token = issue_token(cli_server, SEED_OWNER_ACCOUNT_ID)

    def authenticated(_purpose: str) -> session.Session:
        return session.Session(
            account_id=SEED_OWNER_ACCOUNT_ID,
            device_id="device_test",
            access_token=token,
            refresh_token="",
            expires_at="2099-01-01T00:00:00.000Z",
        )

    monkeypatch.setattr(command, "_session", authenticated)
    monkeypatch.setattr(command, "endpoint", lambda: cli_endpoint)

    result = command.show_object({"kind": "component", "id": FIXTURE_COMPONENT_ID}).payload

    assert isinstance(result, CliOwnerObjectDetailView)
    assert result.stable_id == FIXTURE_COMPONENT_ID
    assert {item.version for item in result.versions} >= {"1.0", "1.2"}
