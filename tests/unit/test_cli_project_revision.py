"""CLI transport for the organization project ledger.

Sync planning refuses a revision the organization has not seen. These commands
are the missing push and pull: they project only allowlisted passport facts,
address them with the same digest domain the API recomputes, and keep a durable
attempt so a lost answer is the same operation rather than a second one.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import cast

import httpx
import pytest

from ai_stp_cli.cloud import session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands import project as project_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import project_ledger, project_links, project_passport, revisions
from ai_stp_cli.local.database import open_registry, transaction
from ai_stp_contracts.context import (
    ProjectLinkResponse,
    ProjectRevisionPushResponse,
    ProjectRevisionView,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id

AT = "2026-08-13T00:00:00.000Z"
LATER = "2099-01-01T00:00:00.000Z"
DIGEST = "sha256:" + "a" * 64
KEY = "revision-push-0001"
EVENT = "rev-event-01"
ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7A"

ORGANIZATION = new_id("organization")
LINK = new_id("project_link")
REMOTE_PROJECT = new_id("remote_project")


def _project_root(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    (root / "src").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "src" / "app.py").write_text("def main() -> None: ...\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "work"\n', encoding="utf-8")
    (root / "README.md").write_text("# work", encoding="utf-8")
    return root


def _link(local_project_id: str, *, remote_revision: str = "initial") -> ProjectLinkResponse:
    return ProjectLinkResponse(
        link_id=LINK,
        plan_id=new_id("link_plan"),
        plan_digest=DIGEST,
        organization_id=ORGANIZATION,
        local_project_id=local_project_id,
        remote_project_id=REMOTE_PROJECT,
        provider_project_id=None,
        state="linked",
        local_revision="initial",
        remote_revision=remote_revision,
        provider_revision=None,
        revision=1,
        updated_at=AT,
    )


def _registry(path: Path, project: Path) -> str:
    with closing(open_registry(path, create=True)) as connection:
        found = project_passport.scan(connection, project)
        stored = project_passport.record(connection, found, device_id=DEVICE)
        with transaction(connection):
            project_links.cache_link(connection, _link(stored.stable_id))
        return stored.stable_id


def _drop_passport(path: Path, local_project_id: str) -> None:
    with closing(open_registry(path)) as connection, transaction(connection):
        connection.execute("DELETE FROM head WHERE stable_id = ?", (local_project_id,))
    with closing(open_registry(path)) as connection:
        assert revisions.head(connection, local_project_id) is None


def _parameters(local_project_id: str) -> dict[str, object]:
    return {
        "organization-id": ORGANIZATION,
        "link-id": LINK,
        "local-project-id": local_project_id,
        "authorization-revision": f"personal:{ORGANIZATION}:1:1",
        "event-id": EVENT,
        "idempotency-key": KEY,
        "confirm": True,
    }


def _wired(
    monkeypatch: pytest.MonkeyPatch,
    registry_path: Path,
    route: Callable[[httpx.Request], httpx.Response],
) -> None:
    held = session.Session(
        account_id=ACCOUNT,
        device_id=DEVICE,
        access_token="token",
        refresh_token="refresh",
        expires_at=LATER,
    )

    def required(_purpose: str) -> session.Session:
        return held

    def where() -> Endpoint:
        return Endpoint(
            "https://platform.example",
            max_attempts=1,
            transport=httpx.MockTransport(route),
        )

    monkeypatch.setattr(cloud_auth, "required", required)
    monkeypatch.setattr(project_commands, "configured_path", lambda: registry_path)
    monkeypatch.setattr(project_commands, "endpoint", where)


def _accepted(body: dict[str, object]) -> dict[str, object]:
    revision_id = str(body["revision_id"])
    expected = body.get("expected_head_revision_id")
    return {
        "schema_version": 1,
        "receipt": {
            "schema_version": 1,
            "event_id": body["event_id"],
            "state": "accepted",
            "revision_id": revision_id,
            "server_head_revision_id": revision_id,
            "client_head_revision_id": expected,
            "common_ancestor_revision_id": None,
            "error_code": None,
        },
    }


def test_projection_from_a_passport_is_path_free_and_matches_the_server_domain(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    with closing(open_registry(registry_path)) as connection:
        stored = revisions.head(connection, local_project_id)
        assert stored is not None
        projection = project_ledger.projection_from_passport(
            stored, remote_project_id=REMOTE_PROJECT
        )
    assert "root" not in projection
    assert projection["remote_project_id"] == REMOTE_PROJECT
    revision_id, content_digest = project_ledger.signed_revision(
        remote_project_id=REMOTE_PROJECT,
        parent_revision_ids=[],
        operation="upsert",
        projection=projection,
    )
    assert revision_id.startswith("sha256:")
    assert content_digest.startswith("sha256:")
    assert revision_id != content_digest
    document: dict[str, JsonValue] = {
        "schema_version": 1,
        "remote_project_id": REMOTE_PROJECT,
        "parent_revision_ids": [],
        "operation": "upsert",
        "projection": cast(JsonValue, projection),
    }
    assert revision_id == digest_canonical("ai-stp:revision:v1", document)
    assert content_digest == digest_canonical("ai-stp:revision:v1", cast(JsonValue, projection))


def test_a_push_publishes_the_passport_projection_and_keeps_the_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    sent: list[dict[str, object]] = []

    def route(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content.decode("utf-8"))
            sent.append(body)
            return httpx.Response(200, json=_accepted(body))
        return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, route)
    answer = project_commands.revision_push(_parameters(local_project_id))

    assert answer.payload.receipt.state == "accepted"
    assert sent and sent[0]["parent_revision_ids"] == []
    assert sent[0]["expected_head_revision_id"] is None
    projection = sent[0]["projection"]
    assert isinstance(projection, dict)
    assert "root" not in projection
    with closing(open_registry(registry_path)) as connection:
        cached = project_ledger.cached_push(
            connection, local_project_id=local_project_id, idempotency_key=KEY
        )
        viewed = project_ledger.cached_revision(
            connection,
            local_project_id=local_project_id,
            revision_id=str(answer.payload.receipt.revision_id),
        )
    assert cached is not None and cached.state == "accepted"
    assert viewed is not None and viewed.revision_id == answer.payload.receipt.revision_id


def test_a_repeat_push_with_the_same_key_is_answered_from_the_durable_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    posts = 0

    def route(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        if request.method == "POST":
            posts += 1
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_accepted(body))
        return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, route)
    first = project_commands.revision_push(_parameters(local_project_id))
    second = project_commands.revision_push(_parameters(local_project_id))
    assert first.payload == second.payload
    assert posts == 1


def test_an_unknown_push_is_named_and_retried_as_the_same_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    lose = True
    sent: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        nonlocal lose
        if request.method != "POST":
            return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))
        sent.append(request.read().decode("utf-8"))
        if lose:
            lose = False
            raise httpx.ReadError("the response was lost", request=request)
        body = json.loads(sent[-1])
        return httpx.Response(200, json=_accepted(body))

    _wired(monkeypatch, registry_path, route)
    with pytest.raises(CliFailure) as raised:
        project_commands.revision_push(_parameters(local_project_id))
    assert raised.value.details["effect"] == "unknown"
    assert KEY in "".join(raised.value.next_actions)
    assert "..." not in "".join(raised.value.next_actions)

    answer = project_commands.revision_push(_parameters(local_project_id))
    assert answer.payload.receipt.state == "accepted"
    assert len(sent) == 2
    assert sent[0] == sent[1]


def test_a_second_key_body_under_an_existing_key_is_refused_before_sending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))

    def route(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_accepted(body))
        return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, route)
    project_commands.revision_push(_parameters(local_project_id))

    def refuses(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a different body under the same key must not be sent")

    _wired(monkeypatch, registry_path, refuses)
    with pytest.raises(CliFailure) as raised:
        project_commands.revision_push(
            {**_parameters(local_project_id), "event-id": "rev-event-02"}
        )
    assert raised.value.code == "AI_STP_CONFLICT"

    with pytest.raises(CliFailure) as other_link:
        project_commands.revision_push(
            {**_parameters(local_project_id), "link-id": new_id("project_link")}
        )
    assert other_link.value.code == "AI_STP_CONFLICT"

    with pytest.raises(CliFailure) as other_organization:
        project_commands.revision_push(
            {**_parameters(local_project_id), "organization-id": new_id("organization")}
        )
    assert other_organization.value.code == "AI_STP_CONFLICT"


def test_a_follow_on_push_parents_the_remote_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    first_id = "sha256:" + "c" * 64
    with closing(open_registry(registry_path)) as connection, transaction(connection):
        project_links.cache_link(connection, _link(local_project_id, remote_revision=first_id))
    sent: list[dict[str, object]] = []

    def route(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content.decode("utf-8"))
            sent.append(body)
            return httpx.Response(200, json=_accepted(body))
        return httpx.Response(
            200, json=_link(local_project_id, remote_revision=first_id).model_dump(mode="json")
        )

    _wired(monkeypatch, registry_path, route)
    project_commands.revision_push(_parameters(local_project_id))
    assert sent[0]["parent_revision_ids"] == [first_id]
    assert sent[0]["expected_head_revision_id"] == first_id


def test_pull_caches_each_redacted_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    revision_id = "sha256:" + "d" * 64
    item = ProjectRevisionView(
        revision_id=revision_id,
        parent_revision_ids=[],
        operation="upsert",
        content_digest="sha256:" + "e" * 64,
        projection={"schema_version": 1, "kind": "project"},
        actor_account_id=ACCOUNT,
        device_id=DEVICE,
        created_at=AT,
    )

    def route(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers["X-AI-STP-Authorization-Revision"] == (
            f"personal:{ORGANIZATION}:1:1"
        )
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "head_revision_id": revision_id,
                "items": [item.model_dump(mode="json")],
            },
        )

    _wired(monkeypatch, registry_path, route)
    answer = project_commands.revision_pull(
        {
            "organization-id": ORGANIZATION,
            "link-id": LINK,
            "local-project-id": local_project_id,
            "authorization-revision": f"personal:{ORGANIZATION}:1:1",
        }
    )
    assert answer.payload.head_revision_id == revision_id
    with closing(open_registry(registry_path)) as connection:
        cached = project_ledger.cached_revision(
            connection, local_project_id=local_project_id, revision_id=revision_id
        )
    assert cached is not None
    assert cached.revision_id == revision_id


def test_a_repeat_pull_of_an_identical_node_does_not_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    revision_id = "sha256:" + "d" * 64
    item = ProjectRevisionView(
        revision_id=revision_id,
        parent_revision_ids=[],
        operation="upsert",
        content_digest="sha256:" + "e" * 64,
        projection={"schema_version": 1, "kind": "project"},
        actor_account_id=ACCOUNT,
        device_id=DEVICE,
        created_at=AT,
    )
    writes: list[str] = []
    real = project_ledger.cache_revision

    def counted(
        connection: sqlite3.Connection,
        *,
        local_project_id: str,
        link_id: str,
        item: ProjectRevisionView,
        origin: str,
    ) -> None:
        writes.append(origin)
        real(
            connection,
            local_project_id=local_project_id,
            link_id=link_id,
            item=item,
            origin=origin,
        )

    monkeypatch.setattr(project_ledger, "cache_revision", counted)

    def route(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "head_revision_id": revision_id,
                "items": [item.model_dump(mode="json")],
            },
        )

    _wired(monkeypatch, registry_path, route)
    parameters = {
        "organization-id": ORGANIZATION,
        "link-id": LINK,
        "local-project-id": local_project_id,
        "authorization-revision": f"personal:{ORGANIZATION}:1:1",
    }
    project_commands.revision_pull(parameters)
    project_commands.revision_pull(parameters)
    assert writes == ["pulled"]


def test_push_without_a_passport_is_refused_without_a_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = new_id("project")
    with closing(open_registry(registry_path, create=True)) as connection, transaction(connection):
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'project', ?)",
            (local_project_id, AT),
        )
        project_links.cache_link(connection, _link(local_project_id))

    def refuses(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a missing passport must not be pushed")

    _wired(monkeypatch, registry_path, refuses)
    with pytest.raises(CliFailure) as raised:
        project_commands.revision_push(_parameters(local_project_id))
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert any("project passport" in action for action in raised.value.next_actions)


def test_a_spent_key_replays_without_re_deriving_a_passport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The receipt is the operation. The passport is only how it was first built."""
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))

    def route(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_accepted(body))
        return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, route)
    first = project_commands.revision_push(_parameters(local_project_id))
    _drop_passport(registry_path, local_project_id)

    def refuses_a_second_send(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            raise AssertionError("a spent key must not re-derive a missing passport")
        return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, refuses_a_second_send)
    second = project_commands.revision_push(_parameters(local_project_id))
    assert first.payload == second.payload


def test_an_unknown_push_retries_the_stored_body_without_a_passport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    lose = True
    sent: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        nonlocal lose
        if request.method != "POST":
            return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))
        sent.append(request.read().decode("utf-8"))
        if lose:
            lose = False
            raise httpx.ReadError("the response was lost", request=request)
        body = json.loads(sent[-1])
        return httpx.Response(200, json=_accepted(body))

    _wired(monkeypatch, registry_path, route)
    with pytest.raises(CliFailure) as raised:
        project_commands.revision_push(_parameters(local_project_id))
    assert raised.value.details["effect"] == "unknown"
    _drop_passport(registry_path, local_project_id)

    answer = project_commands.revision_push(_parameters(local_project_id))
    assert answer.payload.receipt.state == "accepted"
    assert len(sent) == 2
    assert sent[0] == sent[1]


def test_no_push_request_is_made_while_this_process_holds_the_local_write_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    contended: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        other = sqlite3.connect(registry_path, timeout=0.1)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
            contended.append("free")
        except sqlite3.OperationalError:
            contended.append("locked")
        finally:
            other.close()
        if request.method == "POST":
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_accepted(body))
        return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, route)
    project_commands.revision_push(_parameters(local_project_id))
    assert contended == ["free", "free"]


def test_an_unbound_migrated_cache_row_is_rebound_from_the_server_before_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    with closing(open_registry(registry_path)) as connection, transaction(connection):
        connection.execute("UPDATE project_link SET link_id = ''")
    seen: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.method == "GET" and request.url.path.endswith(f"/links/{LINK}"):
            return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))
        if request.method == "POST":
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_accepted(body))
        return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, route)
    answer = project_commands.revision_push(_parameters(local_project_id))
    assert answer.payload.receipt.state == "accepted"
    assert seen[0].startswith("GET ")
    assert any(item.startswith("POST ") for item in seen)
    with closing(open_registry(registry_path)) as connection:
        held = project_links.cached_link(connection, local_project_id=local_project_id)
    assert held is not None and held.link_id == LINK


def test_an_unbound_push_is_refused_when_the_server_link_names_another_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    with closing(open_registry(registry_path)) as connection, transaction(connection):
        connection.execute("UPDATE project_link SET link_id = ''")

    def route(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            raise AssertionError("a mismatched re-observation must not push")
        foreign = _link(local_project_id).model_dump(mode="json")
        foreign["local_project_id"] = new_id("project")
        return httpx.Response(200, json=foreign)

    _wired(monkeypatch, registry_path, route)
    with pytest.raises(CliFailure) as raised:
        project_commands.revision_push(_parameters(local_project_id))
    assert raised.value.code == "AI_STP_CONFLICT"
    assert "..." not in "".join(raised.value.next_actions)


def test_ledger_tables_reject_unknown_origin_and_state(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = new_id("project")
    with closing(open_registry(registry_path, create=True)) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO project_ledger_revision "
                "(revision_id, local_project_id, link_id, origin, view_json) "
                "VALUES (?, ?, ?, 'invented', '{}')",
                (DIGEST, local_project_id, LINK),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO project_ledger_push "
                "(local_project_id, link_id, organization_id, event_id, idempotency_key, "
                "request_json, state, receipt_json) "
                "VALUES (?, ?, ?, ?, ?, '{}', 'sent', NULL)",
                (local_project_id, LINK, ORGANIZATION, EVENT, KEY),
            )


def test_a_second_device_pulls_the_node_the_first_one_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_path = tmp_path / "first.sqlite"
    second_path = tmp_path / "second.sqlite"
    first_id = _registry(first_path, _project_root(tmp_path))
    second_id = new_id("project")
    with closing(open_registry(second_path, create=True)) as connection, transaction(connection):
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'project', ?)",
            (second_id, AT),
        )
        project_links.cache_link(connection, _link(second_id))

    def publish(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_accepted(body))
        return httpx.Response(200, json=_link(first_id).model_dump(mode="json"))

    _wired(monkeypatch, first_path, publish)
    pushed = project_commands.revision_push(_parameters(first_id))
    revision_id = str(pushed.payload.receipt.revision_id)
    with closing(open_registry(first_path)) as connection:
        published = project_ledger.cached_revision(
            connection, local_project_id=first_id, revision_id=revision_id
        )
    assert published is not None

    def receive(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "head_revision_id": revision_id,
                "items": [published.model_dump(mode="json")],
            },
        )

    _wired(monkeypatch, second_path, receive)
    answer = project_commands.revision_pull(
        {
            "organization-id": ORGANIZATION,
            "link-id": LINK,
            "local-project-id": second_id,
            "authorization-revision": f"personal:{ORGANIZATION}:1:1",
        }
    )
    assert answer.payload.head_revision_id == revision_id
    with closing(open_registry(second_path)) as connection:
        pulled = project_ledger.cached_revision(
            connection, local_project_id=second_id, revision_id=revision_id
        )
    assert pulled is not None
    assert pulled.revision_id == published.revision_id
    assert pulled.projection == published.projection


def test_an_unbound_migrated_cache_row_is_rebound_from_the_server_before_pull(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    with closing(open_registry(registry_path)) as connection, transaction(connection):
        connection.execute("UPDATE project_link SET link_id = ''")
    revision_id = "sha256:" + "d" * 64
    item = ProjectRevisionView(
        revision_id=revision_id,
        parent_revision_ids=[],
        operation="upsert",
        content_digest="sha256:" + "e" * 64,
        projection={"schema_version": 1, "kind": "project"},
        actor_account_id=ACCOUNT,
        device_id=DEVICE,
        created_at=AT,
    )
    seen: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.method == "GET" and request.url.path.endswith(f"/links/{LINK}"):
            return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "head_revision_id": revision_id,
                "items": [item.model_dump(mode="json")],
            },
        )

    _wired(monkeypatch, registry_path, route)
    project_commands.revision_pull(
        {
            "organization-id": ORGANIZATION,
            "link-id": LINK,
            "local-project-id": local_project_id,
            "authorization-revision": f"personal:{ORGANIZATION}:1:1",
        }
    )
    assert seen[0].startswith("GET ")
    assert any(path.endswith("/revisions") for path in seen)
    with closing(open_registry(registry_path)) as connection:
        held = project_links.cached_link(connection, local_project_id=local_project_id)
    assert held is not None and held.link_id == LINK


def test_no_pull_request_is_made_while_this_process_holds_the_local_write_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    contended: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        other = sqlite3.connect(registry_path, timeout=0.1)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
            contended.append("free")
        except sqlite3.OperationalError:
            contended.append("locked")
        finally:
            other.close()
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={"schema_version": 1, "head_revision_id": None, "items": []},
        )

    _wired(monkeypatch, registry_path, route)
    project_commands.revision_pull(
        {
            "organization-id": ORGANIZATION,
            "link-id": LINK,
            "local-project-id": local_project_id,
            "authorization-revision": f"personal:{ORGANIZATION}:1:1",
        }
    )
    assert contended == ["free"]


def test_a_receipt_write_failure_after_a_remote_success_is_unknown_and_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    posts = 0
    original = project_ledger.record_push

    def boom(
        connection: sqlite3.Connection,
        *,
        local_project_id: str,
        idempotency_key: str,
        receipt: ProjectRevisionPushResponse,
    ) -> None:
        if posts == 1:
            raise sqlite3.OperationalError("disk I/O error")
        original(
            connection,
            local_project_id=local_project_id,
            idempotency_key=idempotency_key,
            receipt=receipt,
        )

    def route(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        if request.method == "POST":
            posts += 1
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_accepted(body))
        return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, route)
    monkeypatch.setattr(project_ledger, "record_push", boom)
    with pytest.raises(CliFailure) as raised:
        project_commands.revision_push(_parameters(local_project_id))
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert raised.value.details["effect"] == "unknown"
    assert raised.value.retryable is True
    with closing(open_registry(registry_path)) as connection:
        cached = project_ledger.cached_push(
            connection, local_project_id=local_project_id, idempotency_key=KEY
        )
    assert cached is not None
    assert cached.state == "pending"
    assert cached.receipt is None
    assert KEY in "".join(raised.value.next_actions)

    answer = project_commands.revision_push(_parameters(local_project_id))
    assert answer.payload.receipt.state == "accepted"
    assert posts == 2


def test_a_pending_push_without_a_receipt_is_the_same_operation_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    local_project_id = _registry(registry_path, _project_root(tmp_path))
    posts = 0

    def route(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        if request.method == "POST":
            posts += 1
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_accepted(body))
        return httpx.Response(200, json=_link(local_project_id).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, route)
    project_commands.revision_push(_parameters(local_project_id))
    with closing(open_registry(registry_path)) as connection, transaction(connection):
        connection.execute(
            "UPDATE project_ledger_push SET state = 'pending', receipt_json = NULL "
            "WHERE local_project_id = ? AND idempotency_key = ?",
            (local_project_id, KEY),
        )
    posts = 0
    answer = project_commands.revision_push(_parameters(local_project_id))
    assert answer.payload.receipt.state == "accepted"
    assert posts == 1
