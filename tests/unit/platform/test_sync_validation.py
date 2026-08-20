"""Unit tests for sync allowlist, seal and payload policy (REQ-2501)."""

from __future__ import annotations

import pytest

from ai_stp_api.slices.sync.validation import (
    SyncValidationError,
    expected_content_digest,
    expected_revision_id,
    seal_revision_document,
    validate_entity_identity,
    validate_event_document,
    validate_parents,
)
from ai_stp_foundation.ids import new_id

pytestmark = pytest.mark.platform


def _ids() -> tuple[str, str, str]:
    return new_id("developer"), new_id("device"), new_id("account")


def test_seal_is_deterministic_and_content_addressed() -> None:
    entity_id, device_id, actor_id = _ids()
    payload = {"preference": "dark"}
    doc = seal_revision_document(
        entity_id=entity_id,
        entity_kind="developer_passport",
        parent_revision_ids=[],
        operation="upsert",
        payload=payload,
        device_id=device_id,
        actor_id=actor_id,
        created_at="2026-08-07T00:00:00.000Z",
    )
    first = expected_revision_id(doc)
    second = expected_revision_id(doc)
    assert first == second
    assert first.startswith("revision_")
    assert expected_content_digest(payload).startswith("sha256:")


def test_validate_accepts_sealed_developer_passport() -> None:
    entity_id, device_id, actor_id = _ids()
    payload = {"preference": "dark"}
    doc = seal_revision_document(
        entity_id=entity_id,
        entity_kind="developer_passport",
        parent_revision_ids=[],
        operation="upsert",
        payload=payload,
        device_id=device_id,
        actor_id=actor_id,
        created_at="2026-08-07T00:00:00.000Z",
    )
    rid = expected_revision_id(doc)
    digest = expected_content_digest(payload)
    sealed = validate_event_document(
        entity_id=entity_id,
        entity_kind="developer_passport",
        revision_id_value=rid,
        parent_revision_ids=[],
        operation="upsert",
        content_digest=digest,
        payload=payload,
        device_id=device_id,
        actor_id=actor_id,
        created_at="2026-08-07T00:00:00.000Z",
    )
    assert sealed["entity_id"] == entity_id


@pytest.mark.parametrize(
    "payload",
    [
        {"secret": "x"},
        {"api_key": "k"},
        {"kind": "ProjectPassport"},
        {"path": "C:\\Users\\secret"},
        {"home": "/home/user/.ssh/id_rsa"},
    ],
)
def test_validate_rejects_forbidden_payload(payload: dict[str, object]) -> None:
    entity_id, device_id, actor_id = _ids()
    doc = seal_revision_document(
        entity_id=entity_id,
        entity_kind="developer_passport",
        parent_revision_ids=[],
        operation="upsert",
        payload=payload,
        device_id=device_id,
        actor_id=actor_id,
        created_at="2026-08-07T00:00:00.000Z",
    )
    with pytest.raises(SyncValidationError):
        validate_event_document(
            entity_id=entity_id,
            entity_kind="developer_passport",
            revision_id_value=expected_revision_id(doc),
            parent_revision_ids=[],
            operation="upsert",
            content_digest=expected_content_digest(payload),
            payload=payload,
            device_id=device_id,
            actor_id=actor_id,
            created_at="2026-08-07T00:00:00.000Z",
        )


def test_validate_rejects_mismatched_revision_id() -> None:
    entity_id, device_id, actor_id = _ids()
    payload = {"preference": "dark"}
    with pytest.raises(SyncValidationError, match="revision_id"):
        validate_event_document(
            entity_id=entity_id,
            entity_kind="developer_passport",
            revision_id_value="revision_" + ("0" * 64),
            parent_revision_ids=[],
            operation="upsert",
            content_digest=expected_content_digest(payload),
            payload=payload,
            device_id=device_id,
            actor_id=actor_id,
            created_at="2026-08-07T00:00:00.000Z",
        )


def test_device_summary_must_match_session_device() -> None:
    device_id = new_id("device")
    other = new_id("device")
    actor_id = new_id("account")
    payload = {"display_name": "desk"}
    doc = seal_revision_document(
        entity_id=other,
        entity_kind="device_summary",
        parent_revision_ids=[],
        operation="upsert",
        payload=payload,
        device_id=device_id,
        actor_id=actor_id,
        created_at="2026-08-07T00:00:00.000Z",
    )
    with pytest.raises(SyncValidationError, match="device_summary"):
        validate_event_document(
            entity_id=other,
            entity_kind="device_summary",
            revision_id_value=expected_revision_id(doc),
            parent_revision_ids=[],
            operation="upsert",
            content_digest=expected_content_digest(payload),
            payload=payload,
            device_id=device_id,
            actor_id=actor_id,
            created_at="2026-08-07T00:00:00.000Z",
        )


def test_tombstone_requires_parent() -> None:
    entity_id, device_id, actor_id = _ids()
    payload: dict[str, object] = {}
    with pytest.raises(SyncValidationError, match="tombstone"):
        validate_event_document(
            entity_id=entity_id,
            entity_kind="developer_passport",
            revision_id_value="revision_" + ("a" * 64),
            parent_revision_ids=[],
            operation="tombstone",
            content_digest=expected_content_digest(payload),
            payload=payload,
            device_id=device_id,
            actor_id=actor_id,
            created_at="2026-08-07T00:00:00.000Z",
        )


@pytest.mark.parametrize(
    ("entity_kind", "entity_id", "message"),
    [
        ("unknown", "unknown_1", "entity_kind"),
        ("unverified_consent", "invalid", "unverified_consent"),
        ("developer_passport", "invalid", "developer"),
    ],
)
def test_entity_identity_rejects_unknown_kinds_and_invalid_ids(
    entity_kind: str, entity_id: str, message: str
) -> None:
    with pytest.raises(SyncValidationError, match=message):
        validate_entity_identity(
            entity_kind=entity_kind,
            entity_id=entity_id,
            device_id=new_id("device"),
        )


def test_consent_identity_accepts_account_and_opaque_consent_ids() -> None:
    device_id = new_id("device")
    validate_entity_identity(
        entity_kind="unverified_consent", entity_id=new_id("account"), device_id=device_id
    )
    validate_entity_identity(
        entity_kind="unverified_consent", entity_id="consent_owned", device_id=device_id
    )


@pytest.mark.parametrize(
    ("parents", "operation", "message"),
    [
        (["revision_invalid"], "upsert", "invalid revision"),
        (["revision_" + "a" * 64] * 2, "upsert", "unique"),
        (["revision_" + char * 64 for char in "abc"], "upsert", "two parents"),
    ],
)
def test_parent_validation_rejects_invalid_duplicate_and_oversized_graphs(
    parents: list[str], operation: str, message: str
) -> None:
    with pytest.raises(SyncValidationError, match=message):
        validate_parents(parents, operation=operation)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"nested": [{"password_hint": "secret"}]}, "forbidden field"),
        ({"binary": b"bytes"}, "binary bytes"),
        ({"home": "/home/someone/project"}, "absolute path"),
    ],
)
def test_nested_payload_scan_rejects_secrets_and_binary_data(
    payload: dict[str, object], message: str
) -> None:
    entity_id, device_id, actor_id = _ids()
    with pytest.raises(SyncValidationError, match=message):
        validate_event_document(
            entity_id=entity_id,
            entity_kind="developer_passport",
            revision_id_value="revision_" + "a" * 64,
            parent_revision_ids=[],
            operation="upsert",
            content_digest="sha256:" + "a" * 64,
            payload=payload,
            device_id=device_id,
            actor_id=actor_id,
            created_at="2026-08-07T00:00:00.000Z",
        )


@pytest.mark.parametrize(("device_id", "actor_id"), [("invalid", None), (None, "invalid")])
def test_event_validation_rejects_invalid_actor_and_device_ids(
    device_id: str | None, actor_id: str | None
) -> None:
    valid_device = device_id or new_id("device")
    valid_actor = actor_id or new_id("account")
    with pytest.raises(SyncValidationError):
        validate_event_document(
            entity_id=new_id("developer"),
            entity_kind="developer_passport",
            revision_id_value="revision_" + "a" * 64,
            parent_revision_ids=[],
            operation="upsert",
            content_digest="sha256:" + "a" * 64,
            payload={"preference": "dark"},
            device_id=valid_device,
            actor_id=valid_actor,
            created_at="2026-08-07T00:00:00.000Z",
        )


def test_event_validation_rejects_content_digest_mismatch() -> None:
    entity_id, device_id, actor_id = _ids()
    payload = {"preference": "dark"}
    document = seal_revision_document(
        entity_id=entity_id,
        entity_kind="developer_passport",
        parent_revision_ids=[],
        operation="upsert",
        payload=payload,
        device_id=device_id,
        actor_id=actor_id,
        created_at="2026-08-07T00:00:00.000Z",
    )
    with pytest.raises(SyncValidationError, match="content_digest"):
        validate_event_document(
            entity_id=entity_id,
            entity_kind="developer_passport",
            revision_id_value=expected_revision_id(document),
            parent_revision_ids=[],
            operation="upsert",
            content_digest="sha256:" + "0" * 64,
            payload=payload,
            device_id=device_id,
            actor_id=actor_id,
            created_at="2026-08-07T00:00:00.000Z",
        )
