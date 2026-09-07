"""Private defaults and explicit owner opening at the authenticated HTTP boundary."""

import json
from contextlib import closing
from pathlib import Path

import httpx
import pytest
from tests.unit.test_cli_install_commands import _confirmed  # pyright: ignore[reportPrivateUsage]

from ai_stp_cli.cloud import session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.commands import publication, visibility
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports, selection
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.secrets import open_store
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id


def _login() -> session.Session:
    held = session.Session(
        passports.owner().account_id,
        new_id("device"),
        "private-session-fixture",
        "private-refresh-fixture",
        session.expiry(3600),
    )
    store, _warning = open_store()
    session.save(store, held)
    return held


@pytest.mark.parametrize("legacy_response", [False, True])
def test_component_upload_defaults_private_and_refuses_a_legacy_public_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    legacy_response: bool,
) -> None:
    with closing(open_registry(configured_path(), create=True)) as connection:
        proposal = _confirmed(connection, tmp_path, "8")
        selected = selection.held(connection, proposal)
        assert selected is not None
        component_id = selected.members[0].stable_id
    held = _login()
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST" and request.url.path == "/v1/publications/plans"
        body = json.loads(request.content)
        assert body["visibility"] == "private"
        response = {
            "plan_id": new_id("operation"),
            "plan_hash": digest_canonical("ai-stp:plan:v1", body),
            "state": "ready",
            "object_kind": body["object_kind"],
            "stable_id": body["stable_id"],
            "version": body["version"],
            "content_digest": body["content_digest"],
            "policy_version": body["policy_version"],
            "actor_id": held.account_id,
            "device_id": held.device_id,
            "expires_at": session.expiry(600),
        }
        if not legacy_response:
            response["visibility"] = "private"
        return httpx.Response(201, json=response)

    where = Endpoint("https://private.example.test", transport=httpx.MockTransport(serve))
    monkeypatch.setattr(publication, "endpoint", lambda: where)
    parameters = {
        "id": component_id,
        "version": "1.0",
        "component-root": str(tmp_path),
    }
    if legacy_response:
        with pytest.raises(CliFailure, match="published contract"):
            publication.plan(parameters)
    else:
        result = publication.plan(parameters).payload
        assert result.visibility == "private"
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == f"Bearer {held.access_token}"


@pytest.mark.parametrize("wrong_hash", [False, True])
def test_visibility_requires_exact_explicit_owner_confirmation_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    wrong_hash: bool,
) -> None:
    held = _login()
    stable_id = new_id("component")
    response: dict[str, object] = {
        "plan_id": new_id("operation"),
        "plan_hash": digest_canonical("ai-stp:plan:v1", stable_id),
        "state": "planned",
        "object_kind": "component",
        "stable_id": stable_id,
        "version": "1.0",
        "passport_digest": digest_canonical("ai-stp:passport:v1", stable_id),
        "previous_visibility": "private",
        "visibility": "public",
        "actor_id": held.account_id,
        "device_id": held.device_id,
        "expires_at": session.expiry(600),
        "effects": ["make this exact version publicly readable"],
    }
    paths: list[str] = []

    def serve(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.headers["Authorization"] == f"Bearer {held.access_token}"
        if request.url.path.endswith("/confirm"):
            assert json.loads(request.content)["plan_hash"] == response["plan_hash"]
            response["state"] = "applied"
        return httpx.Response(200, json=response)

    where = Endpoint("https://private.example.test", transport=httpx.MockTransport(serve))
    monkeypatch.setattr(visibility, "endpoint", lambda: where)
    planned = visibility.plan(
        {"kind": "component", "id": stable_id, "version": "1.0", "visibility": "public"}
    ).payload
    parameters: dict[str, object] = {"plan-id": planned.plan_id, "plan-hash": planned.plan_hash}
    with pytest.raises(CliFailure, match="explicit confirmation"):
        visibility.confirm(parameters)
    assert len(paths) == 1
    parameters["confirm"] = True
    if wrong_hash:
        parameters["plan-hash"] = digest_canonical("ai-stp:plan:v1", {"wrong": stable_id})
        with pytest.raises(CliFailure, match="changed after review"):
            visibility.confirm(parameters)
        assert not any(path.endswith("/confirm") for path in paths)
    else:
        completed = visibility.confirm(parameters).payload
        assert completed.state == "applied"
        assert completed.passport_digest == planned.passport_digest
        assert visibility.confirm(parameters).payload == completed
        assert sum(path.endswith("/confirm") for path in paths) == 1
