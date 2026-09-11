"""Focused contract checks for the B2B-00 context boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_stp_api.slices.context.service import projection_for
from ai_stp_contracts.context import (
    CapabilityProjection,
    ProjectRevisionPushRequest,
    ProjectUnlinkPlanRequest,
    ProjectUnlinkRequest,
    validate_public_project_data,
)


def projection(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "mode": "local",
        "context_kind": "local",
        "organization_id": None,
        "authorization_revision": "local:1",
        "issued_at": "2026-09-10T00:00:00.000Z",
        "generated_at": "2026-09-10T00:00:00.000Z",
        "expires_at": "2026-09-10T00:15:00.000Z",
        "capabilities": ["project.list", "project.read"],
        "unavailable": {},
    }
    value.update(overrides)
    return value


def test_capabilities_are_closed_sorted_and_duplicate_free() -> None:
    with pytest.raises(ValidationError):
        CapabilityProjection.model_validate(
            projection(capabilities=["project.read", "project.list"])
        )
    with pytest.raises(ValidationError):
        CapabilityProjection.model_validate(
            projection(capabilities=["project.read", "project.read"])
        )
    with pytest.raises(ValidationError):
        CapabilityProjection.model_validate(projection(capabilities=["unknown.read"]))


def test_projection_cannot_claim_a_different_context_or_overlap_unavailable() -> None:
    with pytest.raises(ValidationError):
        CapabilityProjection.model_validate(projection(mode="personal"))
    with pytest.raises(ValidationError):
        CapabilityProjection.model_validate(projection(unavailable={"project.read": "forbidden"}))


def test_server_projection_is_role_scoped_and_local_stays_corporate_free() -> None:
    local = projection_for(mode="local", organization_id=None)
    personal = projection_for(
        mode="personal",
        organization_id="organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    )
    member = projection_for(
        mode="corporate",
        organization_id="organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        role="member",
    )

    assert "organization.manage" not in local.capabilities
    assert local.unavailable["organization.read"] == "unsupported"
    assert local.unavailable["project.create"] == "unsupported"
    assert personal.unavailable["organization.manage"] == "unsupported"
    assert member.unavailable["organization.manage"] == "unsupported"
    assert "project.read" in member.capabilities


def test_unlink_confirmation_carries_only_the_server_plan() -> None:
    request = ProjectUnlinkRequest(
        plan_id="unlink_plan_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        plan_digest="sha256:" + "a" * 64,
        authorization_revision="corporate:organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z:1",
        idempotency_key="unlink-confirm-01",
    )
    assert request.plan_id.startswith("unlink_plan_")
    with pytest.raises(ValidationError):
        ProjectUnlinkRequest.model_validate({**request.model_dump(), "expected_link_revision": 1})

    planned = ProjectUnlinkPlanRequest(
        link_id="project_link_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        expected_link_revision=1,
        authorization_revision=request.authorization_revision,
        idempotency_key="unlink-plan-00000001",
    )
    assert planned.expected_link_revision == 1


def _revision_push(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "event_id": "revision-event-01",
        "revision_id": "sha256:" + "a" * 64,
        "parent_revision_ids": [],
        "operation": "upsert",
        "content_digest": "sha256:" + "b" * 64,
        "projection": {
            "schema_version": 1,
            "kind": "project",
            "remote_project_id": "remote_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            "index_digest": "sha256:" + "c" * 64,
            "languages": ["Python"],
            "file_count": 1,
        },
        "authorization_revision": "corporate:organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z:1:1",
        "idempotency_key": "revision-push-0001",
    }
    value.update(overrides)
    return value


def test_project_revision_projection_rejects_private_or_unbounded_metadata() -> None:
    with pytest.raises(ValidationError):
        ProjectRevisionPushRequest.model_validate(
            _revision_push(projection={"languages": {"path": "C:\\private\\project"}})
        )
    with pytest.raises(ValidationError):
        ProjectRevisionPushRequest.model_validate(
            _revision_push(
                projection={
                    "configuration_digest": "not-a-digest",
                }
            )
        )
    with pytest.raises(ValidationError):
        ProjectRevisionPushRequest.model_validate(
            _revision_push(
                projection={
                    "remote_project_id": "remote_project_foreign",
                }
            )
        )
    with pytest.raises(ValueError):
        validate_public_project_data(
            {"organization_id": "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z"},
            reject_identifiers=True,
        )
