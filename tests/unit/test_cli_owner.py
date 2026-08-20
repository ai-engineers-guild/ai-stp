"""Owner commands expose only server-authorized read models."""

import httpx
import pytest

from ai_stp_cli.cloud import owner, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_contracts.owner import (
    CliOwnerObjectDetailView,
    OwnerObjectDetail,
    OwnerObjectListQuery,
)

BASE = "https://platform.example"
ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
STABLE = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DIGEST = "sha256:" + "b" * 64
AT = "2026-08-13T00:00:00.000Z"


def _object() -> dict[str, object]:
    return {
        "schema_version": 1,
        "object_kind": "component",
        "stable_id": STABLE,
        "name": "demo",
        "versions": [
            {
                "schema_version": 1,
                "version": "1.0",
                "content_digest": DIGEST,
                "lifecycle_state": "draft",
                "visibility": "private",
                "trust_lane": "experimental",
                "author_verified": False,
                "component_verified": False,
                "install_eligible": False,
                "published_at": None,
                "can_start_publication": True,
            }
        ],
    }


def _version() -> dict[str, object]:
    return {
        "schema_version": 1,
        "object_kind": "component",
        "stable_id": STABLE,
        "name": "demo",
        "version": "1.0",
        "content_digest": DIGEST,
        "lifecycle_state": "draft",
        "visibility": "private",
        "trust_lane": "experimental",
        "author_verified": False,
        "component_verified": False,
        "install_eligible": False,
        "published_at": None,
        "can_start_publication": True,
        "open_publication_plan_id": "",
        "evidence": [],
        "description": "",
    }


def test_owner_transport_uses_exact_authenticated_paths_and_query() -> None:
    seen: list[tuple[str, str, str, str | None]] = []

    def route(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.method,
                request.url.path,
                request.url.query.decode(),
                request.headers.get("Authorization"),
            )
        )
        if request.url.path == "/v1/owner/objects":
            return httpx.Response(
                200,
                json={
                    "schema_version": 1,
                    "items": [],
                    "page": {"schema_version": 1, "next_cursor": None, "page_size": 7},
                },
            )
        if "/versions/" in request.url.path:
            return httpx.Response(200, json=_version())
        return httpx.Response(200, json=_object())

    endpoint = Endpoint(BASE, transport=httpx.MockTransport(route))
    owner.list_objects(
        endpoint,
        "bearer",
        OwnerObjectListQuery(cursor="opaque-cursor", page_size=7, object_kind="component"),
    )
    owner.object_detail(endpoint, "bearer", "component", STABLE)
    owner.version_detail(endpoint, "bearer", "component", STABLE, "1.0")

    assert [item[1] for item in seen] == [
        "/v1/owner/objects",
        f"/v1/owner/objects/component/{STABLE}",
        f"/v1/owner/objects/component/{STABLE}/versions/1.0",
    ]
    assert seen[0][2] == "cursor=opaque-cursor&page_size=7&object_kind=component"
    assert all(item[3] == "Bearer bearer" for item in seen)


def test_owner_command_converts_wire_detail_to_cli_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.commands import owner as command

    def authenticated(_purpose: str) -> session.Session:
        return session.Session(
            account_id=ACCOUNT,
            device_id=DEVICE,
            access_token="bearer",
            refresh_token="refresh",
            expires_at="2099-01-01T00:00:00.000Z",
        )

    def detail(_endpoint: Endpoint, _token: str, _kind: str, _stable_id: str) -> OwnerObjectDetail:
        return OwnerObjectDetail.model_validate(_object())

    monkeypatch.setattr(command, "_session", authenticated)
    monkeypatch.setattr(owner, "object_detail", detail)

    result = command.show_object({"kind": "component", "id": STABLE}).payload

    assert isinstance(result, CliOwnerObjectDetailView)
    assert result.versions[0].content_digest == DIGEST


def test_owner_registry_declares_three_read_only_commands() -> None:
    from ai_stp_cli.registry import COMMANDS

    found = {item.name: item.descriptor for item in COMMANDS if item.name.startswith("owner ")}
    assert set(found) == {"owner object show", "owner objects", "owner version show"}
    assert all(item.mutability == "read" for item in found.values())
    assert all(item.confirmation == "none" for item in found.values())
