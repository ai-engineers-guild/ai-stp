"""Focused coverage for publication support ports and worker boundaries."""

from __future__ import annotations

import base64
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.grants.service import (
    _ts as grant_timestamp,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_api.slices.publish.service import (
    _require_active_device,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_api.slices.reports.service import (  # pyright: ignore[reportPrivateUsage]
    _scan_forbidden,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_api.slices.reports.service import (
    _ts as report_timestamp,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_assurance import AuthorAttestation, attestation_digest
from ai_stp_foundation.ids import new_id
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_platform.mail import RecordingMailPort, ResendMailPort
from ai_stp_platform.publication_logic import (
    AttestationBindingContext,
    bind_author_attestations,
    execute_publish,
    execute_reevaluate_eligibility,
    execute_validate,
    passport_digest,
    plan_to_wire,
    run_platform_checks,
    snapshot_outcome,
    validate_passport_completeness,
)
from ai_stp_platform.storage.object_store import ImmutableObjectStore
from ai_stp_worker.handlers import resolve
from ai_stp_worker.handlers.deliver_invitation import handle_deliver_invitation
from ai_stp_worker.handlers.publish import handle_publish
from ai_stp_worker.handlers.reevaluate import handle_reevaluate
from ai_stp_worker.handlers.upload import InvalidJobPayload, handle_upload
from ai_stp_worker.handlers.validate import handle_validate

pytestmark = pytest.mark.platform


DIGEST = "sha256:" + "a" * 64
ACCOUNT_ID = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"
COMPONENT_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _object_key(digest: str) -> str:
    return f"objects/{digest}"


def _passport(**overrides: object) -> dict[str, object]:
    passport: dict[str, object] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": COMPONENT_ID,
        "revision_id": "revision_" + "0" * 64,
        "parent_revision_ids": [],
        "owner_id": ACCOUNT_ID,
        "created_at": "2026-08-10T00:00:00.000Z",
        "visibility": "public",
        "facts": {},
        "name": "demo",
        "description": "Demo component.",
        "version": "1.0",
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
        "tags": ["test"],
        "source": {"repository": "https://example.test/repo", "commit": "a" * 40, "path": "."},
        "artifact": {"digest": DIGEST, "size_bytes": 1},
        "harness_id": "claude-code",
        "harness_ids": [],
        "supported_os": [],
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "compatibility_evidence_refs": [],
        "component_type": "skill",
        "projection_kind": "native_files",
        "variant_id": None,
        "provides_capabilities": [],
        "requires_components": [],
        "requires_capabilities": [],
        "conflicts": {
            "paths": [],
            "commands": [],
            "hooks": [],
            "mcp": [],
            "agents": [],
            "plugins": [],
        },
        "managed_paths": [],
        "native_ids": [],
    }
    passport.update(overrides)
    passport["revision_id"] = derive_revision_id(passport)  # type: ignore[arg-type]
    return passport


def test_passport_and_check_policy_reject_each_nested_missing_field() -> None:
    assert "source.repository" in validate_passport_completeness(
        _passport(source={"commit": "a" * 40, "path": "."})
    )
    assert "source.commit" in validate_passport_completeness(
        _passport(source={"repository": "https://example.test/repo", "path": "."})
    )
    assert "source.path" in validate_passport_completeness(
        _passport(source={"repository": "https://example.test/repo", "commit": "a" * 40})
    )
    assert "license.spdx_id" in validate_passport_completeness(_passport(license={}))
    assert "tags" in validate_passport_completeness(_passport(tags=[]))

    checks = run_platform_checks(passport=_passport(artifact={}), content_digest=DIGEST)
    assert {item["check_id"] for item in checks} == {
        "structure",
        "digest",
        "license",
        "tags",
        "source_repo",
    }
    assert next(item for item in checks if item["check_id"] == "digest")["result"] == "failed"


def _signed_attestation(
    *,
    device_id: str,
    account_id: str = ACCOUNT_ID,
    content_digest: str = DIGEST,
    policy_version: str = "1",
    tool_versions: dict[str, str] | None = None,
    check_id: str = "credentials",
) -> tuple[str, dict[str, object]]:
    private = Ed25519PrivateKey.generate()
    public_key = base64.b64encode(
        private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")
    subject_digest = passport_digest(ComponentVersionPassport.model_validate(_passport()))
    unsigned = AuthorAttestation.model_validate(
        {
            "object_digest": content_digest,
            "subject": {
                "stable_id": COMPONENT_ID,
                "version": "1.0",
                "passport_digest": subject_digest,
            },
            "check_id": check_id,
            "policy_version": policy_version,
            "tool_versions": tool_versions or {"runner": "1"},
            "harness_id": "claude-code",
            "harness_version": "1.0",
            "provider_version": "1.0",
            "test_case_ids": ["cred-basic"],
            "result": "passed",
            "account_id": account_id,
            "device_id": device_id,
            "attested_at": "2026-08-15T00:00:00.000Z",
            "signature": base64.b64encode(b"\x00" * 64).decode("ascii"),
        }
    )
    signed = unsigned.model_copy(
        update={
            "signature": base64.b64encode(
                private.sign(attestation_digest(unsigned).encode("utf-8"))
            ).decode("ascii")
        }
    )
    return public_key, signed.model_dump(mode="json")


def _bind_context(
    *,
    public_key: str,
    device_id: str,
    **overrides: object,
) -> AttestationBindingContext:
    values: dict[str, object] = {
        "content_digest": DIGEST,
        "policy_version": "1",
        "account_id": ACCOUNT_ID,
        "device_id": device_id,
        "subject_stable_id": COMPONENT_ID,
        "subject_version": "1.0",
        "passport_digest": passport_digest(ComponentVersionPassport.model_validate(_passport())),
        "public_key": public_key,
        "device_revoked": False,
    }
    values.update(overrides)
    return AttestationBindingContext(**values)  # type: ignore[arg-type]


def test_bind_author_attestation_accepts_device_signed_record() -> None:
    device_id = new_id("device")
    public_key, record = _signed_attestation(device_id=device_id)
    bound = bind_author_attestations(
        [record],
        context=_bind_context(public_key=public_key, device_id=device_id),
    )
    assert bound == [
        {
            "check_id": "credentials",
            "result": "passed",
            "source": "author_attested",
            "mandatory": True,
        }
    ]


def test_bind_author_attestation_rejects_sixteen_s_signature() -> None:
    device_id = new_id("device")
    public_key, record = _signed_attestation(device_id=device_id)
    record["signature"] = "s" * 16
    bound = bind_author_attestations(
        [record],
        context=_bind_context(public_key=public_key, device_id=device_id),
    )
    assert bound == []


def test_bind_author_attestation_rejects_revoked_or_foreign_device() -> None:
    device_id = new_id("device")
    public_key, record = _signed_attestation(device_id=device_id)
    revoked = bind_author_attestations(
        [record],
        context=_bind_context(public_key=public_key, device_id=device_id, device_revoked=True),
    )
    foreign = bind_author_attestations(
        [record],
        context=_bind_context(public_key=public_key, device_id=new_id("device")),
    )
    other_key, _other = _signed_attestation(device_id=device_id)
    wrong_key = bind_author_attestations(
        [record],
        context=_bind_context(public_key=other_key, device_id=device_id),
    )
    assert revoked == []
    assert foreign == []
    assert wrong_key == []


def test_bind_author_attestation_rejects_shifted_digest() -> None:
    device_id = new_id("device")
    public_key, record = _signed_attestation(device_id=device_id)
    bound = bind_author_attestations(
        [record],
        context=_bind_context(
            public_key=public_key,
            device_id=device_id,
            content_digest="sha256:" + "b" * 64,
        ),
    )
    assert bound == []


def test_attestations_and_snapshot_outcomes_cover_policy_edges() -> None:
    assert snapshot_outcome([]) == ("failed", False)
    assert snapshot_outcome([{"mandatory": True, "result": "warning"}]) == ("warning", False)
    assert snapshot_outcome([{"mandatory": True, "result": "expired"}]) == ("failed", False)
    assert snapshot_outcome([{"mandatory": False, "result": "failed"}]) == ("failed", False)
    assert snapshot_outcome([{"mandatory": True, "result": "passed"}]) == ("passed", True)
    assert snapshot_outcome([{"mandatory": True, "result": "unknown"}]) == ("failed", False)


def test_recording_mail_port_failures_are_transient_and_redacted() -> None:
    port = RecordingMailPort(fail_times=1)
    with pytest.raises(RuntimeError, match="transient mail failure"):
        port.send_invitation(
            to_email="owner@example.test",
            invitation_id="invite_1",
            object_stable_id="component_1",
            major=1,
            accept_token="secret-token",
        )
    port.arm_failures(0)
    port.send_invitation(
        to_email="owner@example.test",
        invitation_id="invite_1",
        object_stable_id="component_1",
        major=1,
        accept_token="secret-token",
    )
    assert port.sent == [
        {
            "to_email": "owner@example.test",
            "invitation_id": "invite_1",
            "object_stable_id": "component_1",
            "major": 1,
            "token_present": True,
        }
    ]
    assert "secret-token" not in str(port.sent)


def test_resend_port_dry_run_and_http_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    ResendMailPort(api_key="").send_invitation(
        to_email="owner@example.test",
        invitation_id="invite_1",
        object_stable_id="component_1",
        major=1,
        accept_token="secret-token",
    )

    class Response:
        status = 202

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    captured: list[urllib.request.Request] = []

    def success(request: urllib.request.Request, *, timeout: int) -> Response:
        captured.append(request)
        assert timeout == 15
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", success)
    ResendMailPort(api_key="key", api_base="https://mail.example.test/").send_invitation(
        to_email="owner@example.test",
        invitation_id="invite_1",
        object_stable_id="component_1",
        major=1,
        accept_token="secret-token",
    )
    assert captured
    body_data = captured[0].data
    assert isinstance(body_data, bytes)
    assert b"secret-token" not in body_data

    class BadResponse(Response):
        status = 500

    def bad_response(*_args: object, **_kwargs: object) -> BadResponse:
        return BadResponse()

    monkeypatch.setattr(urllib.request, "urlopen", bad_response)
    with pytest.raises(RuntimeError, match="resend status 500"):
        ResendMailPort(api_key="key").send_invitation(
            to_email="owner@example.test",
            invitation_id="invite_1",
            object_stable_id="component_1",
            major=1,
            accept_token="secret-token",
        )

    def transport_failure(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", transport_failure)
    with pytest.raises(RuntimeError, match="resend transport failure"):
        ResendMailPort(api_key="key").send_invitation(
            to_email="owner@example.test",
            invitation_id="invite_1",
            object_stable_id="component_1",
            major=1,
            accept_token="secret-token",
        )


@pytest.mark.asyncio
async def test_worker_handlers_validate_payloads_and_delegate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    validate_call = AsyncMock()
    publish_call = AsyncMock()
    reevaluate_call = AsyncMock()
    monkeypatch.setattr("ai_stp_worker.handlers.validate.execute_validate", validate_call)
    monkeypatch.setattr("ai_stp_worker.handlers.publish.execute_publish", publish_call)
    monkeypatch.setattr(
        "ai_stp_worker.handlers.reevaluate.execute_reevaluate_eligibility", reevaluate_call
    )
    with pytest.raises(ValueError, match="invitation_id"):
        await handle_deliver_invitation(session, {})
    with pytest.raises(ValueError, match="object_stable_id"):
        await handle_deliver_invitation(
            session, {"invitation_id": "invite_1", "to_email": "a@b.test"}
        )
    with pytest.raises(ValueError, match="accept_token"):
        await handle_deliver_invitation(
            session,
            {
                "invitation_id": "invite_1",
                "to_email": "a@b.test",
                "object_stable_id": "component_1",
                "major": 1,
            },
        )

    with pytest.raises(ValueError, match="plan_id"):
        await handle_validate(session, {})
    with pytest.raises(ValueError, match="plan_id"):
        await handle_publish(session, {"plan_id": ""})
    with pytest.raises(ValueError, match="object_kind"):
        await handle_reevaluate(session, {})
    await handle_validate(session, {"plan_id": "plan_1"})
    await handle_publish(session, {"plan_id": "plan_1"})
    await handle_reevaluate(
        session,
        {"object_kind": "component", "stable_id": "component_1", "version": "1.0"},
    )
    validate_call.assert_awaited_once_with(session, plan_id="plan_1", release_read_transaction=True)
    publish_call.assert_awaited_once_with(session, plan_id="plan_1", store=None)
    reevaluate_call.assert_awaited_once_with(
        session, object_kind="component", stable_id="component_1", version="1.0"
    )
    with pytest.raises(InvalidJobPayload, match="visibility"):
        await handle_upload({})
    with pytest.raises(InvalidJobPayload, match="public or private"):
        await handle_upload({"visibility": "internal"})
    await handle_upload({"visibility": "public"})

    assert resolve("not-a-job") is None
    upload_handler = resolve("upload")
    update_handler = resolve("update")
    assert upload_handler is not None
    assert update_handler is not None
    await upload_handler(session, {"visibility": "private"})
    await update_handler(session, {})


@pytest.mark.asyncio
async def test_publication_database_guards_and_reevaluation_edges() -> None:
    session = AsyncMock()
    session.get.return_value = None
    with pytest.raises(ValueError, match="unknown plan"):
        await execute_validate(session, plan_id="plan_missing")
    with pytest.raises(ValueError, match="unknown plan"):
        await execute_publish(session, plan_id="plan_missing")

    plan = SimpleNamespace(
        id="plan_1",
        object_kind="component",
        stable_id=COMPONENT_ID,
        version="1.0",
        content_digest=DIGEST,
        state="publish_planned",
        component_verified=False,
        actor_account_id=ACCOUNT_ID,
        passport=_passport(),
    )
    existing_snapshot = SimpleNamespace(id="snapshot_1")
    session.get.return_value = plan
    session.scalar.return_value = existing_snapshot
    assert await execute_validate(session, plan_id=plan.id) is existing_snapshot

    valid_passport = ComponentVersionPassport.model_validate(plan.passport)
    existing_catalog = SimpleNamespace(passport_digest=passport_digest(valid_passport))
    session.scalar.return_value = existing_catalog
    session.execute.return_value = SimpleNamespace(scalar_one=lambda: SimpleNamespace(id="job_seo"))
    store = cast(
        ImmutableObjectStore,
        SimpleNamespace(
            read_by_digest=AsyncMock(return_value=b"x"),
            key_for_digest=_object_key,
        ),
    )
    assert await execute_publish(session, plan_id=plan.id, store=store) is existing_catalog
    assert plan.state == "published"

    session.scalar.side_effect = [None, None]
    with pytest.raises(ValueError, match="successful validation"):
        await execute_publish(session, plan_id=plan.id, store=store)

    with pytest.raises(ValueError, match="object store"):
        await execute_publish(session, plan_id=plan.id)

    missing_store = cast(
        ImmutableObjectStore,
        SimpleNamespace(
            read_by_digest=AsyncMock(return_value=None),
            key_for_digest=_object_key,
        ),
    )
    with pytest.raises(ValueError, match="durable verified artifact bytes"):
        await execute_publish(session, plan_id=plan.id, store=missing_store)

    row = SimpleNamespace(component_verified=True, trust_lane="authoritative")
    published_plan = SimpleNamespace(id="plan_2", component_verified=True)
    snapshot = SimpleNamespace(id="snapshot_2")
    binding = SimpleNamespace(
        mandatory=True,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        result="passed",
    )
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [binding]))
    session.scalar.side_effect = [row, published_plan, snapshot]
    session.execute.return_value = result
    reevaluated = await execute_reevaluate_eligibility(
        session,
        object_kind="component",
        stable_id="component_1",
        version="1.0",
    )
    assert reevaluated is row
    assert row.component_verified is False
    assert row.trust_lane == "experimental"
    assert published_plan.component_verified is False

    session.scalar.side_effect = [None]
    assert (
        await execute_reevaluate_eligibility(
            session, object_kind="component", stable_id="missing", version="1.0"
        )
        is None
    )
    session.scalar.side_effect = [row, None]
    assert (
        await execute_reevaluate_eligibility(
            session, object_kind="component", stable_id="component_1", version="1.0"
        )
        is row
    )
    session.scalar.side_effect = [row, published_plan, None]
    assert (
        await execute_reevaluate_eligibility(
            session, object_kind="component", stable_id="component_1", version="1.0"
        )
        is row
    )

    wire_plan = SimpleNamespace(
        id="plan_3",
        plan_hash="plan_hash",
        state="ready",
        object_kind="component",
        stable_id="component_1",
        version="1.0",
        content_digest=DIGEST,
        policy_version="1",
        actor_account_id="account_1",
        device_id="device_1",
        expires_at=datetime.now(UTC).replace(tzinfo=None),
        component_verified=False,
        effects=None,
    )
    assert plan_to_wire(cast(Any, wire_plan))["schema_version"] == 1


@pytest.mark.asyncio
async def test_api_timestamp_and_device_guard_edges() -> None:
    naive = datetime(2026, 1, 1)
    assert grant_timestamp(naive).endswith("Z")
    assert report_timestamp(naive).endswith("Z")
    ctx = AuthContext(
        account_id="account_1",
        account_status="active",
        session_id="session_1",
        device_id="device_1",
        is_admin=False,
        via_cookie=False,
    )
    db = AsyncMock()
    db.get.return_value = None
    with pytest.raises(Exception, match="device not found"):
        await _require_active_device(db, ctx=ctx, device_id="device_1")
    db.get.return_value = SimpleNamespace(account_id="account_1", state="revoked")
    with pytest.raises(Exception, match="device is revoked"):
        await _require_active_device(db, ctx=ctx, device_id="device_1")


def test_report_forbidden_payload_guard() -> None:
    with pytest.raises(Exception, match="forbidden content"):
        _scan_forbidden("diagnostic contains a secret")
