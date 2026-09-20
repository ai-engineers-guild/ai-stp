"""Grant client boundary: retry semantics and the local command gates.

The journeys — direct grant, invitation accept with the delivered token,
foreign-account refusal, and the wire→view conversion — moved to
`tests/api/cli/test_grants.py` against the real `/v1/grants` routes. What
remains here never needed a server: a dropped connection must re-send the
caller's exact idempotency key, and the commands must demand confirmation
before any transport exists.
"""

import json

import httpx
import pytest

from ai_stp_cli.cloud import grants, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.grants import GrantInvitationCreateRequest

BASE = "https://platform.example"
ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
STABLE = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
INVITATION = "invitation_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
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
