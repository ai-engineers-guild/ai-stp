"""Grant commands cover the complete authenticated contract without leaking tokens."""

import json

import httpx
import pytest

from ai_stp_cli.cloud import grants, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.grants import (
    DirectGrantCreateRequest,
    GrantAcceptRequest,
    GrantInvitationCreateRequest,
    GrantRevokeRequest,
)

BASE = "https://platform.example"
ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
STABLE = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
INVITATION = "invitation_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
GRANT = "grant_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
AT = "2026-08-13T00:00:00.000Z"
KEY = "stable-intent-012345"


def _invitation() -> dict[str, object]:
    return {
        "schema_version": 1,
        "invitation_id": INVITATION,
        "object_kind": "component",
        "stable_id": STABLE,
        "major": 1,
        "state": "pending",
        "expires_at": "2026-08-20T00:00:00.000Z",
        "created_at": AT,
    }


def _grant() -> dict[str, object]:
    return {
        "schema_version": 1,
        "grant_id": GRANT,
        "object_kind": "component",
        "stable_id": STABLE,
        "major": 1,
        "grantee_account_id": ACCOUNT,
        "owner_account_id": ACCOUNT,
        "state": "active",
        "created_at": AT,
        "revoked_at": None,
        "recipient_kind": "user_id",
        "recipient": ACCOUNT,
    }


def test_every_grant_route_uses_auth_and_the_typed_body() -> None:
    seen: list[tuple[str, str, str | None, dict[str, object] | None]] = []

    def route(request: httpx.Request) -> httpx.Response:
        body = None if not request.content else json.loads(request.content)
        seen.append((request.method, request.url.path, request.headers.get("Authorization"), body))
        if request.method == "GET":
            return httpx.Response(200, json={"schema_version": 1, "invitations": [], "grants": []})
        if request.url.path.endswith("/revoke"):
            return httpx.Response(
                200, json={"schema_version": 1, "revoked": True, "local_bytes_retained": True}
            )
        if request.url.path.endswith("/invitations"):
            return httpx.Response(201, json=_invitation())
        return httpx.Response(201, json=_grant())

    endpoint = Endpoint(BASE, transport=httpx.MockTransport(route))
    invite = GrantInvitationCreateRequest(
        object_kind="component",
        stable_id=STABLE,
        major=1,
        recipient_email="owner@example.test",
        idempotency_key=KEY,
    )
    direct = DirectGrantCreateRequest(
        object_kind="component",
        stable_id=STABLE,
        major=1,
        recipient_kind="user_id",
        recipient=ACCOUNT,
        idempotency_key=KEY,
    )
    accept = GrantAcceptRequest(token="invitation-secret-token", idempotency_key=KEY)
    revoke = GrantRevokeRequest(reason="done", idempotency_key=KEY)

    grants.invite(endpoint, "bearer", invite)
    grants.list_all(endpoint, "bearer")
    grants.direct(endpoint, "bearer", direct)
    grants.accept(endpoint, "bearer", INVITATION, accept)
    grants.revoke_invitation(endpoint, "bearer", INVITATION, revoke)
    grants.revoke_grant(endpoint, "bearer", GRANT, revoke)

    assert [item[:2] for item in seen] == [
        ("POST", "/v1/grants/invitations"),
        ("GET", "/v1/grants"),
        ("POST", "/v1/grants/direct"),
        ("POST", f"/v1/grants/invitations/{INVITATION}/accept"),
        ("POST", f"/v1/grants/invitations/{INVITATION}/revoke"),
        ("POST", f"/v1/grants/{GRANT}/revoke"),
    ]
    assert all(item[2] == "Bearer bearer" for item in seen)
    assert seen[3][3] is not None and seen[3][3]["token"] == "invitation-secret-token"
    assert "invitation-secret-token" not in seen[3][1]


def test_grant_commands_require_confirmation_and_never_take_a_token_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.commands import grants as command
    from ai_stp_cli.registry import COMMANDS

    def authenticated(_purpose: str) -> session.Session:
        return session.Session(
            account_id=ACCOUNT,
            device_id=DEVICE,
            access_token="bearer",
            refresh_token="refresh",
            expires_at="2099-01-01T00:00:00.000Z",
        )

    monkeypatch.setattr(
        command,
        "_session",
        authenticated,
    )
    with pytest.raises(CliFailure) as raised:
        command.invite(
            {
                "kind": "component",
                "id": STABLE,
                "major": 1,
                "email": "a@example.test",
                "idempotency-key": KEY,
            }
        )
    assert raised.value.code == "AI_STP_USER_DECISION_REQUIRED"

    descriptors = {
        item.name: item.descriptor for item in COMMANDS if item.name.startswith("grant ")
    }
    assert set(descriptors) == {
        "grant accept",
        "grant direct",
        "grant invitation revoke",
        "grant invite",
        "grant list",
        "grant revoke",
    }
    assert all(
        parameter.name != "token"
        for descriptor in descriptors.values()
        for parameter in descriptor.parameters
    )
    assert descriptors["grant accept"].confirmation == "explicit_flag"


def test_grant_retry_preserves_the_callers_exact_idempotency_key() -> None:
    seen: list[str] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["idempotency_key"])
        if len(seen) == 1:
            raise httpx.ConnectError("lost response", request=request)
        return httpx.Response(201, json=_invitation())

    request = GrantInvitationCreateRequest(
        object_kind="component",
        stable_id=STABLE,
        major=1,
        recipient_email="owner@example.test",
        idempotency_key=KEY,
    )

    result = grants.invite(Endpoint(BASE, transport=httpx.MockTransport(flaky)), "bearer", request)

    assert result.invitation_id == INVITATION
    assert seen == [KEY, KEY]


def test_grant_permission_failure_remains_a_typed_server_decision() -> None:
    def forbidden(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"error": {"code": "AI_STP_PERMISSION_DENIED"}},
        )

    with pytest.raises(CliFailure) as raised:
        grants.list_all(Endpoint(BASE, transport=httpx.MockTransport(forbidden)), "bearer")

    assert raised.value.code == "AI_STP_PERMISSION_DENIED"


def test_grant_command_converts_the_http_model_to_the_declared_cli_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.commands import grants as command
    from ai_stp_contracts.grants import AccessGrantResponse, CliGrantAccessView

    def authenticated(_purpose: str) -> session.Session:
        return session.Session(
            account_id=ACCOUNT,
            device_id=DEVICE,
            access_token="bearer",
            refresh_token="refresh",
            expires_at="2099-01-01T00:00:00.000Z",
        )

    def direct_result(
        _endpoint: Endpoint, _token: str, _request: DirectGrantCreateRequest
    ) -> AccessGrantResponse:
        return AccessGrantResponse.model_validate(_grant())

    monkeypatch.setattr(command, "_session", authenticated)
    monkeypatch.setattr(grants, "direct", direct_result)

    result = command.direct(
        {
            "kind": "component",
            "id": STABLE,
            "major": 1,
            "recipient-kind": "user_id",
            "recipient": ACCOUNT,
            "idempotency-key": KEY,
            "confirm": True,
        }
    ).payload

    assert isinstance(result, CliGrantAccessView)
    assert result.grant_id == GRANT
