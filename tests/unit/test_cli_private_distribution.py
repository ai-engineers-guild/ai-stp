"""Private distribution: the refusal halves that stay client-local.

The success journeys — `publication plan` defaulting to private and
`visibility plan`/`confirm` opening and closing an exact published version —
moved to `tests/api/cli/test_private_distribution.py` against the real `/v1`
app. What remains here is what a mock legitimately owns: a response missing a
contract field must be refused as off-contract, and a confirm carrying a
different plan hash must be refused before any wire call.
"""

import json
from contextlib import closing
from pathlib import Path

import httpx
import pytest
from tests.unit.test_cli_install_commands import _confirmed  # pyright: ignore[reportPrivateUsage]

from ai_stp_cli.application import publication as publication_service
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


def test_a_legacy_plan_response_missing_visibility_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plan answer without `visibility` is off-contract, not a private plan."""
    with closing(open_registry(configured_path(), create=True)) as connection:
        proposal = _confirmed(connection, tmp_path, "8")
        selected = selection.held(connection, proposal)
        assert selected is not None
        component_id = selected.members[0].stable_id
    held = _login()

    def serve(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/v1/publications/plans"
        body = json.loads(request.content)
        assert body["visibility"] == "private"
        return httpx.Response(
            201,
            json={
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
            },
        )

    where = Endpoint("https://private.example.test", transport=httpx.MockTransport(serve))
    monkeypatch.setattr(publication_service, "endpoint", lambda: where)
    monkeypatch.setattr(publication_service, "_session", lambda: held)

    with pytest.raises(CliFailure, match="published contract"):
        publication.plan({"id": component_id, "version": "1.0"})


def test_confirm_refuses_a_changed_plan_hash_before_the_wire(
    monkeypatch: pytest.MonkeyPatch,
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
    parameters["plan-hash"] = digest_canonical("ai-stp:plan:v1", {"wrong": stable_id})
    with pytest.raises(CliFailure, match="changed after review"):
        visibility.confirm(parameters)
    assert not any(path.endswith("/confirm") for path in paths)
