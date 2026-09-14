"""Applying a project sync plan keeps the effect and the receipt together.

The command sends one remote mutation and then writes what came back. The order
and the transaction boundaries are the contract: a successful remote effect must
survive anything that happens afterwards, an unknown effect must be named as
unknown and retried as the same operation, and no request may run while this
process holds the local write lock.
"""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from ai_stp_cli.cloud import session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands import project as project_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import project_links
from ai_stp_cli.local.database import open_registry, transaction
from ai_stp_contracts.context import ProjectLinkResponse, ProjectSyncPlanResponse
from ai_stp_foundation.ids import new_id

AT = "2026-08-13T00:00:00.000Z"
LATER = "2099-01-01T00:00:00.000Z"
DIGEST = "sha256:" + "a" * 64
KEY = "sync-apply-idem-0001"
ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7A"

LOCAL_PROJECT = new_id("project")
LINK = new_id("project_link")
PLAN = new_id("sync_plan")
ORGANIZATION = new_id("organization")
REMOTE_PROJECT = new_id("remote_project")


def _link(revision: int = 1) -> ProjectLinkResponse:
    return ProjectLinkResponse(
        link_id=LINK,
        plan_id=new_id("link_plan"),
        plan_digest=DIGEST,
        organization_id=ORGANIZATION,
        local_project_id=LOCAL_PROJECT,
        remote_project_id=REMOTE_PROJECT,
        provider_project_id=None,
        state="linked",
        local_revision="initial",
        remote_revision="initial",
        provider_revision=None,
        revision=revision,
        updated_at=AT,
    )


def _plan(state: str = "ready") -> ProjectSyncPlanResponse:
    return ProjectSyncPlanResponse(
        plan_id=PLAN,
        link_id=LINK,
        state=state,  # pyright: ignore[reportArgumentType]
        action="noop",
        expected_link_revision=1,
        local_revision="initial",
        remote_revision="initial",
        provider_revision=None,
        remote_identity_revision=1,
        provider_identity_revision=None,
        conflict_code=None,
        plan_digest=DIGEST,
        expires_at=LATER,
    )


def _registry(path: Path) -> None:
    with closing(open_registry(path)) as connection, transaction(connection):
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'project', ?)",
            (LOCAL_PROJECT, AT),
        )
        project_links.cache_link(connection, _link())
        project_links.cache_sync_plan(
            connection,
            local_project_id=LOCAL_PROJECT,
            plan=_plan(),
            idempotency_key="sync-plan-idem-0001",
            created_at=AT,
        )


def _parameters() -> dict[str, object]:
    return {
        "organization-id": ORGANIZATION,
        "link-id": LINK,
        "plan-id": PLAN,
        "local-project-id": LOCAL_PROJECT,
        "plan-digest": DIGEST,
        "expected-link-revision": "1",
        "authorization-revision": f"personal:{ORGANIZATION}:1:1",
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


def _stored(registry_path: Path) -> project_links.CachedSyncPlan:
    with closing(open_registry(registry_path)) as connection:
        found = project_links.cached_sync_plan(
            connection, local_project_id=LOCAL_PROJECT, plan_id=PLAN
        )
    assert found is not None
    return found


def _applied_body() -> dict[str, object]:
    return _plan(state="applied").model_dump(mode="json")


def test_a_lost_link_refresh_cannot_take_back_a_confirmed_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The receipt is the point of the command; the link view is enrichment.

    The refresh used to run inside the same write transaction as the receipt, so
    a failure there rolled back the record of a mutation the server had already
    performed. The device then believed nothing had happened.
    """
    registry_path = tmp_path / "registry.sqlite"
    _registry(registry_path)
    seen: list[str] = []

    def route(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json=_applied_body())
        return httpx.Response(503, json={"error": {"code": "AI_STP_DEPENDENCY_UNAVAILABLE"}})

    _wired(monkeypatch, registry_path, route)
    answer = project_commands.sync_apply(_parameters())

    assert answer.payload.state == "applied"
    assert answer.warnings, "a stale local link view must be visible to the caller"
    stored = _stored(registry_path)
    assert stored.apply_state == "applied"
    assert stored.receipt is not None and stored.receipt.plan_id == PLAN
    assert seen == ["POST", "GET"]


def test_an_unknown_effect_is_named_and_retried_as_the_same_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost answer is not a failed operation, and a new key would be a second one."""
    registry_path = tmp_path / "registry.sqlite"
    _registry(registry_path)
    sent: list[str] = []
    lose = True

    def route(request: httpx.Request) -> httpx.Response:
        nonlocal lose
        if request.method != "POST":
            return httpx.Response(200, json=_link(revision=2).model_dump(mode="json"))
        sent.append(request.read().decode("utf-8"))
        if lose:
            lose = False
            raise httpx.ReadError("the response was lost", request=request)
        return httpx.Response(200, json=_applied_body())

    _wired(monkeypatch, registry_path, route)
    with pytest.raises(CliFailure) as raised:
        project_commands.sync_apply(_parameters())

    assert raised.value.details["effect"] == "unknown"
    assert any(KEY in action for action in raised.value.next_actions)
    assert any("project link show" in action for action in raised.value.next_actions)
    assert _stored(registry_path).apply_state == "unknown"

    answer = project_commands.sync_apply(_parameters())
    assert answer.payload.state == "applied"
    assert _stored(registry_path).apply_state == "applied"
    # One operation, asked twice: the server sees the same key both times and
    # answers the second from its own receipt.
    assert len(sent) == 2
    assert sent[0] == sent[1]
    assert KEY in sent[0]


def test_a_decided_refusal_is_not_reported_as_an_unknown_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A server that answered is a server that decided; nothing was applied."""
    registry_path = tmp_path / "registry.sqlite"
    _registry(registry_path)

    def route(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(
            412,
            json={
                "schema_version": 1,
                "ok": False,
                "error": {"code": "AI_STP_PRECONDITION_FAILED", "message": "stale"},
            },
        )

    _wired(monkeypatch, registry_path, route)
    with pytest.raises(CliFailure) as raised:
        project_commands.sync_apply(_parameters())

    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert "effect" not in raised.value.details
    assert _stored(registry_path).apply_state == "failed"


def test_a_contract_violation_on_a_successful_status_leaves_the_effect_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server answered `200` with a body nobody agreed to.

    It may well have applied the plan. Calling that a caller mistake would send
    an agent to fix a request that was correct.
    """
    registry_path = tmp_path / "registry.sqlite"
    _registry(registry_path)

    def route(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(200, json={"schema_version": 1, "not": "a sync plan"})

    _wired(monkeypatch, registry_path, route)
    with pytest.raises(CliFailure) as raised:
        project_commands.sync_apply(_parameters())

    assert raised.value.details["effect"] == "unknown"
    assert _stored(registry_path).apply_state == "unknown"


def test_no_request_is_made_while_this_process_holds_the_local_write_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another local writer must not queue behind the network.

    `BEGIN IMMEDIATE` takes the write lock for the whole block, so a request
    inside one makes every other process on this machine wait for a server.
    """
    registry_path = tmp_path / "registry.sqlite"
    _registry(registry_path)
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
            return httpx.Response(200, json=_applied_body())
        return httpx.Response(200, json=_link(revision=2).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, route)
    project_commands.sync_apply(_parameters())
    assert contended == ["free", "free"]


def test_a_repeat_with_the_same_key_is_answered_from_the_durable_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    _registry(registry_path)
    posts = 0

    def route(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        if request.method == "POST":
            posts += 1
            return httpx.Response(200, json=_applied_body())
        return httpx.Response(200, json=_link(revision=2).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, route)
    first = project_commands.sync_apply(_parameters())
    second = project_commands.sync_apply(_parameters())

    assert first.payload == second.payload
    assert posts == 1


def test_a_second_key_on_a_plan_that_already_has_one_is_refused_before_sending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two keys on one plan are two operations, and the plan allows one."""
    registry_path = tmp_path / "registry.sqlite"
    _registry(registry_path)

    def route(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json=_applied_body())
        return httpx.Response(200, json=_link(revision=2).model_dump(mode="json"))

    _wired(monkeypatch, registry_path, route)
    project_commands.sync_apply(_parameters())

    def refuses(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a second key must not reach the server")

    _wired(monkeypatch, registry_path, refuses)
    with pytest.raises(CliFailure) as raised:
        project_commands.sync_apply({**_parameters(), "idempotency-key": "sync-apply-idem-0002"})
    assert raised.value.code == "AI_STP_CONFLICT"


def test_a_plan_this_device_never_cached_is_refused_without_a_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "registry.sqlite"
    _registry(registry_path)

    def refuses(request: httpx.Request) -> httpx.Response:
        raise AssertionError("an unknown plan must not reach the server")

    _wired(monkeypatch, registry_path, refuses)
    with pytest.raises(CliFailure) as raised:
        project_commands.sync_apply({**_parameters(), "plan-id": new_id("sync_plan")})
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


def test_a_plan_from_another_link_is_refused_before_anything_is_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The local project id was the whole key of this cache.

    Nothing recorded which server link or organization the cached rows came
    from, so a plan created for one link could be applied under another link's
    identifiers with no local disagreement.
    """
    registry_path = tmp_path / "registry.sqlite"
    _registry(registry_path)

    def refuses(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a mismatched link must not reach the server")

    _wired(monkeypatch, registry_path, refuses)
    with pytest.raises(CliFailure) as other_link:
        project_commands.sync_apply({**_parameters(), "link-id": new_id("project_link")})
    assert other_link.value.code == "AI_STP_CONFLICT"

    with pytest.raises(CliFailure) as other_organization:
        project_commands.sync_apply({**_parameters(), "organization-id": new_id("organization")})
    assert other_organization.value.code == "AI_STP_CONFLICT"
