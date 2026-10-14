"""Native explicit visibility over published synthetic versions and the real API."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import httpx
from release_scripts._evidence import without_credentials
from release_scripts._native_client import NativeClient

if TYPE_CHECKING:
    from release_scripts.verify_native_publication import _Server

ROOT = "/v1/access/visibility/plans"
APPLY = ("publication", "visibility", "apply")


def prove(
    native: NativeClient,
    root: Path,
    server: _Server,
    component: dict[str, Any],
    setup: dict[str, Any],
) -> None:
    def plan(
        document: dict[str, Any], visibility: str, key: str, *, ok: bool = True
    ) -> dict[str, Any]:
        request = root / "visibility-request.json"
        request.write_text(
            json.dumps(
                {
                    "object_kind": "component" if document is component else "setup",
                    "stable_id": document["stable_id"],
                    "version": document["version"],
                    "visibility": visibility,
                    "idempotency_key": key,
                }
            )
        )
        result = native.invoke(
            root,
            "publication",
            "visibility",
            "plan",
            "--state-dir",
            root,
            "--request",
            request,
            ok=ok,
        )
        without_credentials(result)
        return result

    def apply(prepared: dict[str, Any], *, ok: bool = True) -> dict[str, Any]:
        result = native.apply(root, prepared, APPLY, extra=("--confirm",), ok=ok)
        without_credentials(result)
        return result

    def read(document: dict[str, Any], visibility: str) -> None:
        plural = "components" if document is component else "setups"
        path = f"/v1/catalog/{plural}/{document['stable_id']}/versions/{document['version']}"
        with httpx.Client(base_url=server.origin, trust_env=False) as client:
            response = client.get(path)
        assert response.status_code == (200 if visibility == "public" else 404)
        if visibility == "public":
            body = response.json()
            assert body["passport"] == document
            assert body["distribution_visibility"] == "public"

    read(component, "public")
    read(setup, "public")
    close_setup = plan(setup, "private", "native-visibility-close-setup")
    count = len(server.requests)
    native.apply(root, close_setup, APPLY, ok=False)
    assert len(server.requests) == count
    assert apply(close_setup)["response"]["state"] == "applied"
    read(setup, "private")
    assert (
        apply(plan(component, "private", "native-visibility-close-component"))["response"]["state"]
        == "applied"
    )
    read(component, "private")
    open_setup = plan(setup, "public", "native-visibility-open-setup")
    apply(open_setup, ok=False)
    read(setup, "private")
    native.scenarios["visibility_requires_confirmation_and_public_setup_pins"] = "passed"

    server.drop_visibility = ROOT
    plan(component, "public", "native-visibility-open-component", ok=False)
    assert not server.drop_visibility
    first = plan(component, "public", "native-visibility-open-component")
    stale = plan(component, "public", "native-visibility-stale-component")
    original = first["plan"]["remote"]
    server.drop_visibility = ROOT + "/" + original["plan_id"] + "/confirm"
    apply(first, ok=False)
    assert not server.drop_visibility
    read(component, "public")
    assert native.account(root, "refresh")["outcome"] == "authorized"
    count = len(server.requests)
    apply(first, ok=False)
    assert len(server.requests) == count
    refreshed = plan(component, "public", "native-visibility-open-component")
    assert refreshed["plan"]["request"] == first["plan"]["request"]
    assert refreshed["plan"]["remote"] == {**original, "state": "applied"}
    confirmations = len(server.visibility_confirms)
    assert apply(refreshed)["response"]["state"] == "applied"
    assert len(server.visibility_confirms) == confirmations
    stale = plan(component, "public", "native-visibility-stale-component")
    assert apply(stale)["response"]["state"] == "refused"
    native.scenarios["visibility_lost_create_confirm_refresh_and_stale_refusal"] = "passed"

    assert (
        apply(plan(component, "private", "native-visibility-inverse-component"))["response"][
            "state"
        ]
        == "applied"
    )
    confirmations = len(server.visibility_confirms)
    assert apply(refreshed)["response"]["state"] == "applied"
    status = native.invoke(
        root,
        "publication",
        "visibility",
        "status",
        "--state-dir",
        root,
        "--plan-id",
        original["plan_id"],
    )
    assert status["response"]["state"] == "applied"
    assert len(server.visibility_confirms) == confirmations
    read(component, "private")
    native.scenarios["visibility_historical_replay_does_not_reverse_newer_decision"] = "passed"

    with patch("ai_stp_api.slices.visibility.service.PLAN_TTL", timedelta(seconds=-1)):
        expired = plan(component, "public", "native-visibility-expired-component")
    confirmations = len(server.visibility_confirms)
    assert apply(expired)["response"]["state"] == "expired"
    assert len(server.visibility_confirms) == confirmations
    read(component, "private")
    assert (
        apply(plan(component, "public", "native-visibility-reopen-component"))["response"]["state"]
        == "applied"
    )
    open_setup = plan(setup, "public", "native-visibility-open-setup")
    assert apply(open_setup)["response"]["state"] == "applied"
    read(component, "public")
    read(setup, "public")
    native.scenarios["visibility_expiry_and_reopening_preserve_exact_passports"] = "passed"
